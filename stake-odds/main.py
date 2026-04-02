#!/usr/bin/env python3
"""
Stake Poker Live Odds Calculator.

Extracts game state directly from the Stake.us poker client via Chrome
DevTools Protocol — no OCR, no screen capture, 100% accurate.

Usage:
    python main.py              # Launch manual advisory mode
    python main.py auto         # Launch fully autonomous bot mode
    python main.py selftest     # Odds engine self-test (no browser needed)
"""

import hashlib
import os
import signal
import subprocess
import sys
import time
import urllib.request
import json

from odds_engine import monte_carlo_equity, get_bet_recommendation, parse_actions
from preflop_advisor import preflop_advice, get_position
from session_tracker import SessionTracker
from terminal_ui import print_display, console


CDP_PORT = 9222
CHROME_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chrome-profile")
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def _equity_seed(hole_cards, community_cards):
    """Deterministic seed so equity doesn't flicker on the same cards."""
    s = "".join(hole_cards) + "/" + "".join(community_cards)
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def get_street(community_cards):
    n = len(community_cards)
    if n == 0:
        return "preflop"
    if n == 3:
        return "flop"
    if n == 4:
        return "turn"
    if n == 5:
        return "river"
    return "dealing"


def _cdp_reachable():
    """Check if Chrome DevTools is responding on the CDP port."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{CDP_PORT}/json/version", timeout=2
        ) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def _find_chrome():
    """Return the path to chrome.exe, or None."""
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _kill_chrome():
    """Force-kill all Chrome processes and wait for them to die."""
    subprocess.call(
        ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        time.sleep(0.5)
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                stderr=subprocess.DEVNULL, text=True,
            )
            if "chrome.exe" not in out.lower():
                return
        except Exception:
            return
    # Last resort
    subprocess.call(
        ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)


def _ensure_chrome_debug():
    """
    Make sure Chrome is running with --remote-debugging-port.
    Kills and relaunches Chrome if necessary.
    """
    if _cdp_reachable():
        return True

    chrome = _find_chrome()
    if not chrome:
        console.print(
            "[red]Could not find Chrome. Please install Google Chrome.[/]"
        )
        return False

    console.print(
        "[yellow]Chrome DevTools not available. "
        "Restarting Chrome with debug port...[/]"
    )
    _kill_chrome()

    subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            f"--user-data-dir={CHROME_PROFILE}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for attempt in range(25):
        time.sleep(1)
        if _cdp_reachable():
            console.print(
                f"[green]Chrome ready with DevTools on port {CDP_PORT}.[/]"
            )
            return True
        if attempt % 5 == 4:
            console.print(f"[dim]Waiting for Chrome... ({attempt + 1}s)[/]")

    console.print("[red]Chrome did not start properly. Try again.[/]")
    return False


def _compute_decision(hole_cards, community_cards, street, position_name,
                      raw_actions, pot, big_blind, stack, num_opponents):
    """
    Run the GTO decision engine (preflop advisor or postflop Monte Carlo).

    Returns (odds, recommendation, preflop_info, effective_opp).
    recommendation is None for preflop (use preflop_info instead).
    """
    if street == "preflop":
        act = parse_actions(raw_actions)
        facing = act["can_call"] and act["call_amount"] > 0
        pf = preflop_advice(
            hole_cards,
            position_name or "UTG",
            facing_raise=facing,
            call_amount=act["call_amount"],
            pot=pot,
            big_blind=big_blind,
            stack=stack,
        )
        effective_opp = min(num_opponents, 2)
        odds = monte_carlo_equity(
            hole_cards, community_cards,
            num_opponents=effective_opp,
            num_simulations=15000,
            seed=_equity_seed(hole_cards, community_cards),
        )
        return odds, None, pf, effective_opp

    odds = monte_carlo_equity(
        hole_cards, community_cards,
        num_opponents=num_opponents,
        num_simulations=3000,
        seed=_equity_seed(hole_cards, community_cards),
    )
    rec = get_bet_recommendation(
        odds["equity"], street, pot=pot, actions=raw_actions,
        stack=stack, big_blind=big_blind,
        hole_cards=hole_cards,
        community_cards=community_cards,
    )
    return odds, rec, None, num_opponents


def _refine_postflop(hole_cards, community_cards, odds, num_opponents,
                     street, raw_actions, pot, stack, big_blind):
    """Run extra simulations and merge for a refined postflop result."""
    odds2 = monte_carlo_equity(
        hole_cards, community_cards,
        num_opponents=num_opponents,
        num_simulations=12000,
        seed=_equity_seed(hole_cards, community_cards) + 1,
    )
    merged_equity = (odds["equity"] * 3000 + odds2["equity"] * 12000) / 15000
    merged_win = (odds["win_pct"] * 3000 + odds2["win_pct"] * 12000) / 15000
    merged_tie = (odds["tie_pct"] * 3000 + odds2["tie_pct"] * 12000) / 15000
    merged_lose = (odds["lose_pct"] * 3000 + odds2["lose_pct"] * 12000) / 15000
    odds_final = {
        "equity": merged_equity,
        "win_pct": round(merged_win, 1),
        "tie_pct": round(merged_tie, 1),
        "lose_pct": round(merged_lose, 1),
        "hand_name": odds["hand_name"],
        "simulations": 15000,
    }
    rec2 = get_bet_recommendation(
        odds_final["equity"], street, pot=pot, actions=raw_actions,
        stack=stack, big_blind=big_blind,
        hole_cards=hole_cards,
        community_cards=community_cards,
    )
    return odds_final, rec2


def run(auto_mode=False):
    """Main loop: connect to Chrome, extract cards, calculate odds, display."""
    from dom_scraper import StakePokerScraper

    if auto_mode:
        from auto_player import execute_auto_action

    if not _ensure_chrome_debug():
        sys.exit(1)

    mode_label = "[bold red]AUTO-PLAY[/]" if auto_mode else "[bold green]ADVISORY[/]"
    console.print(f"[bold cyan]Connecting to Stake.us poker table...[/]  Mode: {mode_label}")
    scraper = StakePokerScraper(cdp_port=CDP_PORT)

    try:
        scraper.connect()
    except ConnectionError as e:
        console.print(f"[red]{e}[/]")
        console.print(
            "\n[yellow]In the Chrome window that opened, go to stake.us, "
            "log in, and open a poker table.\n"
            "Then run this script again.[/]"
        )
        sys.exit(1)

    console.print("[bold green]Connected! Live odds running.[/]")
    if auto_mode:
        console.print("[bold yellow]AUTO MODE ACTIVE -- bot will play hands automatically.[/]")
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    prev_hole = []
    prev_community = []
    prev_game_id = 0
    prev_acted_key = ""
    last_hint = 0.0
    error_count = 0
    session = SessionTracker()

    running = True

    def on_sigint(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_sigint)

    while running:
        try:
            detected = scraper.detect()
            error_count = 0
            hole_cards = detected["hole_cards"]
            community_cards = detected["community_cards"]
            pot = detected["pot"]
            num_opponents = detected.get("num_opponents", 1)
            game_id = detected.get("game_id", 0)
            raw_actions = detected.get("actions", [])
            stack = detected.get("stack", 0.0)
            big_blind = detected.get("big_blind", 0.0)

            session.update(game_id, stack)
            session_stats = session.summary(big_blind)

            if game_id and game_id != prev_game_id and prev_game_id != 0:
                prev_hole = []
                prev_community = []
                prev_acted_key = ""
            prev_game_id = game_id

            cards_changed = (
                hole_cards != prev_hole or community_cards != prev_community
            )

            has_actions = len(raw_actions) > 0

            if len(hole_cards) == 2 and (cards_changed or (auto_mode and has_actions)):
                street = get_street(community_cards)
                pos_data = detected.get("position")

                position_name = None
                if pos_data:
                    position_name = get_position(
                        pos_data["dealer_idx"],
                        pos_data["our_seat_idx"],
                        pos_data["occupied_seats"],
                    )

                odds, rec, pf, effective_opp = _compute_decision(
                    hole_cards, community_cards, street, position_name,
                    raw_actions, pot, big_blind, stack, num_opponents,
                )

                if street == "preflop":
                    print_display(
                        hole_cards, community_cards, odds, None,
                        effective_opp, pot, street,
                        position=position_name,
                        preflop=pf,
                        stack=stack,
                        big_blind=big_blind,
                        session=session_stats,
                    )
                else:
                    print_display(
                        hole_cards, community_cards, odds, rec,
                        effective_opp, pot, street,
                        position=position_name,
                        stack=stack,
                        big_blind=big_blind,
                        session=session_stats,
                    )

                # -- AUTO MODE: execute the decision --
                if auto_mode and has_actions:
                    action_key = f"{game_id}:{street}:{','.join(hole_cards)}"
                    if action_key != prev_acted_key:
                        decision = pf if street == "preflop" else rec
                        if decision:
                            execute_auto_action(
                                scraper, decision, raw_actions, console,
                            )
                            prev_acted_key = action_key

                # Refinement pass (postflop only, manual display update)
                if street != "preflop" and cards_changed:
                    odds_final, rec2 = _refine_postflop(
                        hole_cards, community_cards, odds, num_opponents,
                        street, raw_actions, pot, stack, big_blind,
                    )
                    print_display(
                        hole_cards, community_cards, odds_final, rec2,
                        num_opponents, pot, street,
                        position=position_name,
                        stack=stack,
                        big_blind=big_blind,
                        session=session_stats,
                    )

                if cards_changed:
                    prev_hole = hole_cards[:]
                    prev_community = community_cards[:]

            elif len(hole_cards) < 2:
                if prev_hole:
                    prev_hole = []
                    prev_community = []
                    prev_acted_key = ""
                else:
                    now = time.monotonic()
                    if now - last_hint > 8.0:
                        last_hint = now
                        console.print(
                            "[dim]Waiting for cards... "
                            "(play a hand or check that a table is open)[/]"
                        )

            time.sleep(0.05)

        except KeyboardInterrupt:
            break
        except Exception as e:
            error_count += 1
            if error_count >= 3:
                console.print("[yellow]Connection lost — reconnecting...[/]")
                try:
                    scraper.close()
                    scraper = StakePokerScraper(cdp_port=CDP_PORT)
                    scraper.connect()
                    error_count = 0
                    console.print("[green]Reconnected.[/]")
                except Exception:
                    console.print("[red]Reconnect failed, retrying...[/]")
                    time.sleep(3)
            else:
                console.print(f"[red]Error: {e}[/]")
                time.sleep(1)

    scraper.close()

    if session.hands_played > 0:
        path = session.save()
        s = session.summary(big_blind)
        pnl = s["pnl"]
        pnl_style = "green" if pnl >= 0 else "red"
        console.print(f"\n[bold]Session Summary:[/]")
        console.print(f"  Hands: {s['hands_played']}  |  "
                       f"W/L/B: {s['wins']}/{s['losses']}/{s['breakeven']}  |  "
                       f"Win rate: {s['win_rate']}%")
        console.print(f"  P&L: [{pnl_style}]${pnl:+.2f}[/]  |  "
                       f"BB won: {s['bb_won']:+.1f}  |  "
                       f"BB/hr: {s['bb_per_hour']:+.1f}")
        console.print(f"  Saved to: {path}")
    console.print("\n[bold]Goodbye![/]")


def run_discover():
    """Connect and dump full DOM / React model diagnostics."""
    from dom_scraper import StakePokerScraper

    if not _ensure_chrome_debug():
        sys.exit(1)

    console.print("[bold cyan]Connecting for button discovery...[/]")
    scraper = StakePokerScraper(cdp_port=CDP_PORT)
    try:
        scraper.connect()
    except ConnectionError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)

    console.print("[green]Connected. Running full DOM + model discovery...[/]\n")
    info = scraper.discover_full()
    scraper.close()

    if not info:
        console.print("[red]Discovery returned nothing. Is a poker table open?[/]")
        sys.exit(1)

    console.print(f"[bold]URL:[/] {info.get('url', '?')}\n")

    canvases = info.get("canvases", [])
    console.print(f"[bold cyan]Canvases ({len(canvases)}):[/]")
    for c in canvases:
        console.print(f"  {c['w']}x{c['h']}  cls={c.get('cls','')}")

    inputs = info.get("inputs", [])
    console.print(f"\n[bold cyan]Inputs ({len(inputs)}):[/]")
    for inp in inputs:
        console.print(
            f"  <{inp['tag']}> type={inp.get('type','')} "
            f"vis={inp.get('vis')} {inp['w']}w "
            f"val={inp.get('val','')!r} ph={inp.get('ph','')!r}"
        )

    btns = info.get("clickable", [])
    console.print(f"\n[bold cyan]Clickable Elements ({len(btns)}):[/]")
    for b in btns:
        text_preview = b.get("text", "")[:50]
        console.print(
            f"  <{b['tag']}> {b['w']}x{b['h']} @ ({b['x']},{b['y']})  "
            f"evts=[{b.get('evts','')}]  "
            f"text={text_preview!r}"
        )
        if b.get("cls"):
            console.print(f"    cls={b['cls'][:90]}")
        if b.get("da"):
            console.print(f"    data-action={b['da']}")
        if b.get("dt"):
            console.print(f"    data-testid={b['dt']}")

    models = info.get("models", {})
    console.print(f"\n[bold cyan]React Models ({len(models)}):[/]")
    for name, data in models.items():
        console.print(f"\n  [bold]{name}[/]")
        console.print(f"    keys: {data.get('keys', [])}")
        console.print(f"    methods: {data.get('methods', [])}")
        if data.get("compMethods"):
            console.print(f"    componentMethods: {data['compMethods']}")

    console.print("\n[bold green]Discovery complete.[/]")
    console.print(
        "[dim]Run this while you have action buttons visible "
        "(it's your turn to act) for best results.[/]"
    )


def main():
    args = sys.argv[1:]
    if not args:
        run(auto_mode=False)
        return

    mode = args[0].lower()
    if mode in ("run", "start", "dom"):
        run(auto_mode=False)
    elif mode == "auto":
        console.print(
            "\n[bold red]WARNING: Auto mode will play hands automatically.[/]"
            "\n[yellow]This may violate Stake.us Terms of Service.[/]"
            "\n[yellow]Use at your own risk. Press Ctrl+C at any time to stop.[/]\n"
        )
        time.sleep(2)
        run(auto_mode=True)
    elif mode == "discover":
        run_discover()
    elif mode == "selftest":
        import runpy
        runpy.run_path(
            os.path.join(os.path.dirname(__file__), "odds_engine.py"),
            run_name="__main__",
        )
    else:
        console.print(f"[red]Unknown command: {mode}[/]")
        console.print(
            "  python main.py            # Start manual advisory mode\n"
            "  python main.py auto       # Start auto-play bot mode\n"
            "  python main.py discover   # Dump DOM buttons + React models\n"
            "  python main.py selftest   # Test odds engine"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
