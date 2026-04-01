#!/usr/bin/env python3
"""
Stake Poker Live Odds Calculator.

Extracts game state directly from the Stake.us poker client via Chrome
DevTools Protocol — no OCR, no screen capture, 100% accurate.

Usage:
    python main.py              # Launch and start (auto-opens Chrome if needed)
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

from odds_engine import monte_carlo_equity, get_bet_recommendation
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


def run():
    """Main loop: connect to Chrome, extract cards, calculate odds, display."""
    from dom_scraper import StakePokerScraper

    if not _ensure_chrome_debug():
        sys.exit(1)

    console.print("[bold cyan]Connecting to Stake.us poker table...[/]")
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
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    prev_hole = []
    prev_community = []
    prev_game_id = 0
    last_hint = 0.0

    running = True

    def on_sigint(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_sigint)

    while running:
        try:
            detected = scraper.detect()
            hole_cards = detected["hole_cards"]
            community_cards = detected["community_cards"]
            pot = detected["pot"]
            num_opponents = detected.get("num_opponents", 1)
            game_id = detected.get("game_id", 0)
            raw_actions = detected.get("actions", [])

            if game_id and game_id != prev_game_id and prev_game_id != 0:
                prev_hole = []
                prev_community = []
            prev_game_id = game_id

            cards_changed = (
                hole_cards != prev_hole or community_cards != prev_community
            )

            if len(hole_cards) == 2 and cards_changed:
                street = get_street(community_cards)
                odds = monte_carlo_equity(
                    hole_cards,
                    community_cards,
                    num_opponents=num_opponents,
                    num_simulations=3000,
                    seed=_equity_seed(hole_cards, community_cards),
                )
                rec = get_bet_recommendation(
                    odds["equity"], street, pot=pot, actions=raw_actions,
                )
                print_display(
                    hole_cards, community_cards, odds, rec,
                    num_opponents, pot, street,
                )
                prev_hole = hole_cards[:]
                prev_community = community_cards[:]

                # Refine with more sims in background, redisplay
                odds2 = monte_carlo_equity(
                    hole_cards,
                    community_cards,
                    num_opponents=num_opponents,
                    num_simulations=12000,
                    seed=_equity_seed(hole_cards, community_cards) + 1,
                )
                merged_equity = (
                    odds["equity"] * 3000 + odds2["equity"] * 12000
                ) / 15000
                merged_win = (
                    odds["win_pct"] * 3000 + odds2["win_pct"] * 12000
                ) / 15000
                merged_tie = (
                    odds["tie_pct"] * 3000 + odds2["tie_pct"] * 12000
                ) / 15000
                merged_lose = (
                    odds["lose_pct"] * 3000 + odds2["lose_pct"] * 12000
                ) / 15000
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
                )
                print_display(
                    hole_cards, community_cards, odds_final, rec2,
                    num_opponents, pot, street,
                )

            elif len(hole_cards) < 2:
                if prev_hole:
                    prev_hole = []
                    prev_community = []
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
            console.print(f"[red]Error: {e}[/]")
            time.sleep(2)

    scraper.close()
    console.print("\n[bold]Stopped. Goodbye![/]")


def main():
    args = sys.argv[1:]
    if not args:
        run()
        return

    mode = args[0].lower()
    if mode in ("run", "start", "dom"):
        run()
    elif mode == "selftest":
        import runpy
        runpy.run_path(
            os.path.join(os.path.dirname(__file__), "odds_engine.py"),
            run_name="__main__",
        )
    else:
        console.print(f"[red]Unknown command: {mode}[/]")
        console.print(
            "  python main.py            # Start live odds\n"
            "  python main.py selftest   # Test odds engine"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
