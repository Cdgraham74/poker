"""
Rich terminal UI for live poker odds display.
"""

import os
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich import box

# force_terminal: Cursor / some Windows hosts report non-TTY and hide Rich output
console = Console(force_terminal=True, legacy_windows=False)

SUIT_SYMBOLS = {'s': '\u2660', 'h': '\u2665', 'd': '\u2666', 'c': '\u2663'}
SUIT_COLORS = {'s': 'white', 'h': 'red', 'd': 'cyan', 'c': 'green'}


def format_card(card_str):
    """Format a card string with color and suit symbol."""
    if not card_str or len(card_str) != 2:
        return Text("[ ]", style="dim")
    rank = card_str[0]
    suit = card_str[1]
    symbol = SUIT_SYMBOLS.get(suit, '?')
    color = SUIT_COLORS.get(suit, 'white')
    return Text(f"[{rank}{symbol}]", style=f"bold {color}")


def format_cards_row(cards, max_count=5):
    """Format a row of cards."""
    parts = []
    for i in range(max_count):
        if i < len(cards):
            parts.append(format_card(cards[i]))
        else:
            parts.append(Text("[ ]", style="dim"))
        if i < max_count - 1:
            parts.append(Text(" "))

    result = Text()
    for part in parts:
        result.append(part)
    return result


def equity_bar(pct, width=30):
    """Create a visual equity bar."""
    filled = int(pct / 100 * width)
    empty = width - filled

    if pct >= 70:
        color = "green"
    elif pct >= 50:
        color = "yellow"
    elif pct >= 35:
        color = "red"
    else:
        color = "bold red"

    bar = Text()
    bar.append("\u2588" * filled, style=color)
    bar.append("\u2591" * empty, style="dim")
    bar.append(f" {pct:.1f}%", style=f"bold {color}")
    return bar


def _build_opponents_panel(opponents, opponent_stats=None, active_seat=-1):
    """Build the Villains panel showing opponent stacks, bets, and HUD profile."""
    active = [o for o in opponents if o.get("active") or o.get("has_cards")]
    if not active:
        return None

    has_stats = opponent_stats and len(opponent_stats) > 0

    tbl = Table(show_header=True, box=None, padding=(0, 1), expand=True)
    tbl.add_column("", width=4, style="dim")
    tbl.add_column("NAME", width=12)
    tbl.add_column("STACK", width=9, justify="right")
    tbl.add_column("BET", width=8, justify="right")
    if has_stats:
        tbl.add_column("TYPE", width=10)
        tbl.add_column("V/P", width=6, justify="right")
        tbl.add_column("AF", width=4, justify="right")
        tbl.add_column("BLF", width=4, justify="right")
        tbl.add_column("NET", width=8, justify="right")
        tbl.add_column("vsMe", width=7, justify="right")
        tbl.add_column("N", width=4, justify="right")

    for o in active:
        is_acting = o.get("seat_idx") == active_seat
        status_style = "bold bright_white" if is_acting else ("white" if o.get("active") else "dim strikethrough")
        name = (o.get("name") or "???")[:12]
        marker = ">" if is_acting else f"S{o['seat_idx']}"
        bet_str = f"${o['bet']:.2f}" if o.get("bet", 0) > 0 else ""
        bet_style = "bold yellow" if o.get("bet", 0) > 0 else "dim"

        row = [
            Text(marker, style="bold bright_yellow" if is_acting else "dim"),
            Text(name, style=status_style),
            Text(f"${o['stack']:.2f}", style=status_style),
            Text(bet_str, style=bet_style),
        ]

        if has_stats:
            pid = o.get("name", "")
            stats = opponent_stats.get(pid)
            if stats and stats.get("hands", 0) >= 1:
                vpip = stats.get("vpip", 0)
                pfr = stats.get("pfr", 0)
                af = stats.get("af", 0)
                n = stats.get("hands", 0)
                label = stats.get("label", "")
                bluff = stats.get("bluff_score", 0)
                net = stats.get("net", 0)
                vs_us = stats.get("vs_us", 0)

                label_colors = {
                    "WHALE": "bold red", "MANIAC": "bold red",
                    "FISH": "red", "PASSIVE FISH": "red",
                    "CALLING STATION": "red", "LAG MANIAC": "bold red",
                    "LAG": "yellow", "LOOSE": "yellow",
                    "TAG": "green", "REG": "green",
                    "TIGHT PASSIVE": "cyan", "NIT": "cyan", "NIT-AG": "cyan",
                    "NEW": "dim",
                }
                l_style = label_colors.get(label, "white")
                v_style = "bold red" if vpip > 50 else ("yellow" if vpip > 35 else "green")
                bluff_style = "bold red" if bluff > 50 else ("yellow" if bluff > 25 else "green")
                net_style = "green" if net > 0 else ("red" if net < 0 else "dim")
                net_str = f"${net:+.0f}" if abs(net) >= 1 else ""

                vs_style = "red" if vs_us > 0 else ("green" if vs_us < 0 else "dim")
                vs_str = f"${vs_us:+.0f}" if abs(vs_us) >= 1 else ""

                row.extend([
                    Text(label, style=l_style),
                    Text(f"{vpip:.0f}/{pfr:.0f}", style=v_style),
                    Text(f"{af:.1f}", style="white"),
                    Text(f"{bluff}" if bluff > 0 else "", style=bluff_style),
                    Text(net_str, style=net_style),
                    Text(vs_str, style=vs_style),
                    Text(str(n), style="dim"),
                ])
            else:
                row.extend([Text("--", style="dim")] * 7)

        tbl.add_row(*row)

    return Panel(tbl, title="[bold white]Villains[/]", border_style="red")


def _build_facing_section(bet_rec, equity_pct):
    """Build pot odds / facing-bet display when villain has bet."""
    if not bet_rec:
        return None
    call_amt = bet_rec.get("call_amount", 0)
    if call_amt <= 0:
        return None

    pot_odds = bet_rec.get("pot_odds", 0)
    req_eq = bet_rec.get("required_equity", 0)
    desc = bet_rec.get("bet_description", "")

    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(width=18)
    tbl.add_column()

    facing_str = f"${call_amt:.2f}"
    if desc:
        facing_str += f"  ({desc})"
    tbl.add_row(Text("FACING:", style="bold yellow"), Text(facing_str, style="bold yellow"))

    tbl.add_row(
        Text("POT ODDS:", style="bold"),
        Text(f"{pot_odds:.0%}  →  need {req_eq:.0%} equity to call", style="white"),
    )

    if equity_pct > 0:
        have_style = "bold green" if equity_pct / 100 >= req_eq else "bold red"
        verdict = "PROFITABLE" if equity_pct / 100 >= req_eq else "UNPROFITABLE"
        verdict_style = "bold green" if equity_pct / 100 >= req_eq else "bold red"
        tbl.add_row(
            Text("YOU HAVE:", style="bold"),
            Text(f"{equity_pct:.1f}%  →  ", style=have_style) + Text(verdict, style=verdict_style),
        )

    return Panel(tbl, title="[bold white]Pot Odds[/]", border_style="yellow")


def _build_board_panel(bet_rec, street):
    """Build board texture and draws panel for postflop streets."""
    if street == "preflop" or not bet_rec:
        return None

    texture = bet_rec.get("board_texture", "N/A")
    draw_outs = bet_rec.get("draw_outs", 0)
    draw_info = bet_rec.get("draw_info", [])
    spr_val = bet_rec.get("spr", 0)

    if texture == "N/A" and draw_outs == 0:
        return None

    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column(width=18)
    tbl.add_column()

    tex_style = {"WET": "bold red", "SEMI-WET": "yellow", "DRY": "bold green"}.get(texture, "white")
    tbl.add_row(Text("TEXTURE:", style="bold"), Text(texture, style=tex_style))

    if spr_val > 0:
        spr_label = "LOW" if spr_val < 4 else ("MEDIUM" if spr_val < 8 else "DEEP")
        tbl.add_row(Text("SPR:", style="bold"), Text(f"{spr_val:.1f}  ({spr_label})", style="white"))

    if draw_outs > 0:
        tbl.add_row(Text("OUTS:", style="bold"), Text(f"{draw_outs} total", style="bold cyan"))
        for d in draw_info[:3]:
            tbl.add_row(Text(""), Text(f"  {d}", style="cyan"))

    return Panel(tbl, title="[bold white]Board Analysis[/]", border_style="cyan")


def build_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents,
                   pot=None, street='preflop', position=None, preflop=None,
                   stack=0.0, big_blind=0.0, session=None,
                   opponents=None, opponent_stats=None,
                   is_our_turn=False, seat_state=None, active_seat=-1):
    """Build the full terminal display."""

    pos_str = f"  |  {position}" if position else ""
    stack_str = f"  |  Stack: ${stack:.2f}" if stack > 0 else ""
    turn_str = "  |  [bold blink bright_yellow]>>> YOUR TURN <<<[/]" if is_our_turn else ""
    title = f"STAKE POKER ODDS{pos_str}  |  Opp: {num_opponents}{stack_str}{turn_str}"

    # Cards section
    cards_table = Table(show_header=False, box=None, padding=(0, 1))
    cards_table.add_column(width=18)
    cards_table.add_column()

    cards_table.add_row(
        Text("YOUR HAND:", style="bold cyan"),
        format_cards_row(hole_cards, 2)
    )
    cards_table.add_row(
        Text("COMMUNITY:", style="bold cyan"),
        format_cards_row(community_cards, 5)
    )

    info_parts = [street.upper()]
    if pot is not None and pot > 0:
        info_parts.append(f"POT ${pot:.2f}")
    if big_blind > 0 and stack > 0:
        info_parts.append(f"{stack/big_blind:.0f} BB deep")
    cards_table.add_row(
        Text("INFO:", style="bold cyan"),
        Text("  |  ".join(info_parts), style="bold white")
    )

    if seat_state:
        combo = seat_state.get("combination", "")
        is_losing = seat_state.get("is_losing", False)
        if combo:
            losing_tag = "  [BEHIND]" if is_losing else "  [AHEAD]"
            losing_style = "bold red" if is_losing else "bold green"
            cards_table.add_row(
                Text("MADE HAND:", style="bold cyan"),
                Text(combo.strip(), style="white") + Text(losing_tag, style=losing_style),
            )

    cards_panel = Panel(cards_table, title="[bold white]Cards[/]", border_style="blue")

    # Odds section
    equity_pct = 0.0
    if odds_result and odds_result.get('simulations', 0) > 0:
        equity_pct = odds_result['equity'] * 100
        odds_table = Table(show_header=False, box=None, padding=(0, 1))
        odds_table.add_column(width=18)
        odds_table.add_column()

        odds_table.add_row(
            Text("EQUITY:", style="bold"),
            equity_bar(equity_pct)
        )
        odds_table.add_row(
            Text("WIN:", style="bold green"),
            Text(f"{odds_result['win_pct']}%", style="bold green")
        )
        odds_table.add_row(
            Text("TIE:", style="bold yellow"),
            Text(f"{odds_result['tie_pct']}%", style="yellow")
        )
        odds_table.add_row(
            Text("LOSE:", style="bold red"),
            Text(f"{odds_result['lose_pct']}%", style="red")
        )
        odds_table.add_row(
            Text("BEST HAND:", style="bold"),
            Text(odds_result.get('hand_name', '...'), style="bold white")
        )
        odds_table.add_row(
            Text("SIMULATIONS:", style="dim"),
            Text(f"{odds_result['simulations']:,}", style="dim")
        )
    else:
        odds_table = Text("  Waiting for cards...", style="dim italic")

    odds_panel = Panel(odds_table, title="[bold white]Odds[/]", border_style="green")

    # Preflop GTO section
    if preflop:
        tier_style = {
            "PREMIUM": "bold green",
            "VERY STRONG": "bold green",
            "STRONG": "green",
            "GOOD": "yellow",
            "DECENT": "yellow",
            "SPECULATIVE": "red",
            "TRASH": "bold red",
        }.get(preflop.get("hand_tier", ""), "white")

        action = preflop["action"]
        action_style = "bold green" if action in ("RAISE", "3-BET", "3-BET / CALL") else (
            "yellow" if action in ("CALL", "CHECK") else "bold red"
        )

        pf_table = Table(show_header=False, box=None, padding=(0, 1))
        pf_table.add_column(width=18)
        pf_table.add_column()

        pf_table.add_row(
            Text("HAND:", style="bold"),
            Text(preflop["hand_notation"], style=tier_style)
        )
        pf_table.add_row(
            Text("TIER:", style="bold"),
            Text(preflop["hand_tier"], style=tier_style)
        )
        pf_table.add_row(
            Text("IN RANGE:", style="bold"),
            Text(
                "YES" if preflop["in_range"] else "NO",
                style="bold green" if preflop["in_range"] else "bold red"
            )
        )
        stack_bb = preflop.get("stack_bb", 0)
        if stack_bb > 0:
            pf_table.add_row(
                Text("STACK:", style="bold"),
                Text(f"{stack_bb:.0f} BB", style="white")
            )
        num_limpers = preflop.get("num_limpers", 0)
        if num_limpers > 0:
            pf_table.add_row(
                Text("LIMPERS:", style="bold"),
                Text(f"{num_limpers}", style="yellow")
            )
        pf_table.add_row(Text(""), Text(""))
        pf_table.add_row(
            Text("ACTION:", style="bold"),
            Text(f">>> {action} <<<", style=action_style)
        )
        pf_table.add_row(
            Text("SIZING:", style="bold"),
            Text(preflop["sizing"], style=action_style)
        )
        bet_amt = preflop.get("bet_amount", 0)
        if bet_amt > 0:
            pf_table.add_row(
                Text("BET AMOUNT:", style="bold"),
                Text(f"${bet_amt:.2f}", style=f"bold {action_style}")
            )
        pf_table.add_row(Text(""), Text(""))
        pf_table.add_row(
            Text("REASON:", style="dim"),
            Text(preflop["reason"], style="white")
        )

        bet_panel = Panel(pf_table, title="[bold white]GTO Preflop Advisor[/]", border_style="magenta")

    elif bet_rec:
        action_style = {
            'monster': 'bold green',
            'very strong': 'bold green',
            'strong': 'green',
            'good': 'yellow',
            'marginal': 'red',
            'weak': 'bold red',
            'very weak': 'bold red',
        }.get(bet_rec.get('confidence', ''), 'white')

        bet_table = Table(show_header=False, box=None, padding=(0, 1))
        bet_table.add_column(width=18)
        bet_table.add_column()

        bet_table.add_row(
            Text("ACTION:", style="bold"),
            Text(f">>> {bet_rec['action']} <<<", style=action_style)
        )

        amt = bet_rec.get("bet_amount", 0)
        if amt > 0:
            bet_table.add_row(
                Text("BET SIZE:", style="bold"),
                Text(f"${amt:.2f}", style=f"bold {action_style}")
            )

        rec_notes = bet_rec.get("notes", [])
        if rec_notes:
            bet_table.add_row(Text(""), Text(""))
            for note in rec_notes[:4]:
                bet_table.add_row(
                    Text(""),
                    Text(f"  {note}", style="dim italic")
                )

        bet_panel = Panel(bet_table, title="[bold white]Recommendation[/]", border_style="yellow")
    else:
        bet_panel = Panel(
            Text("  Waiting for odds...", style="dim italic"),
            title="[bold white]Recommendation[/]", border_style="yellow",
        )

    # Combine everything
    output = Table.grid(padding=1)
    output.add_column()
    if is_our_turn:
        title_text = Text.from_markup(title, justify="center")
    else:
        title_text = Text(title, style="bold white", justify="center")
    output.add_row(
        Panel(
            title_text,
            border_style="bright_blue",
            box=box.DOUBLE,
        )
    )
    output.add_row(cards_panel)
    output.add_row(odds_panel)

    facing_panel = _build_facing_section(bet_rec, equity_pct)
    if facing_panel:
        output.add_row(facing_panel)

    board_panel = _build_board_panel(bet_rec, street)
    if board_panel:
        output.add_row(board_panel)

    output.add_row(bet_panel)

    if opponents:
        opp_panel = _build_opponents_panel(opponents, opponent_stats, active_seat)
        if opp_panel:
            output.add_row(opp_panel)

    if session:
        pnl = session.get("pnl", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        hands = session.get("hands_played", 0)
        elapsed = session.get("elapsed_min", 0)
        bb_hr = session.get("bb_per_hour", 0)
        bb_color = "green" if bb_hr >= 0 else "red"

        sess_table = Table(show_header=False, box=None, padding=(0, 1))
        sess_table.add_column(width=18)
        sess_table.add_column()

        sess_table.add_row(
            Text("P&L:", style="bold"),
            Text(f"${pnl:+.2f}", style=f"bold {pnl_color}")
        )
        if hands > 0:
            sess_table.add_row(
                Text("HANDS:", style="bold"),
                Text(
                    f"{hands}  "
                    f"({session['wins']}W / {session['losses']}L / {session['breakeven']}B)",
                    style="white"
                )
            )
            sess_table.add_row(
                Text("BB/HR:", style="bold"),
                Text(f"{bb_hr:+.1f}", style=f"bold {bb_color}")
            )
        else:
            sess_table.add_row(
                Text("HANDS:", style="bold"),
                Text("Playing first hand...", style="dim italic")
            )
        sess_table.add_row(
            Text("TIME:", style="dim"),
            Text(f"{elapsed:.0f} min", style="dim")
        )
        start = session.get("start_stack", 0)
        cur = session.get("current_stack", 0) or stack
        if start > 0 and cur > 0:
            sess_table.add_row(
                Text("BUY-IN:", style="dim"),
                Text(f"${start:.2f}  →  ${cur:.2f}", style="dim")
            )

        output.add_row(
            Panel(sess_table, title="[bold white]Session[/]", border_style="cyan")
        )

    legend = Text.from_markup(
        "[dim]V/P[/]=VPIP/PFR (% voluntarily played / % raised preflop)  "
        "[dim]AF[/]=Aggression (bets+raises / calls)  "
        "[dim]BLF[/]=Bluff Score (0-100)  "
        "[dim]NET[/]=their total $ won-lost at table  "
        "[dim]vsMe[/]=[red]$ they took from you[/] / [green]$ you took from them[/]  "
        "[dim]N[/]=Hands seen  "
        "[dim]SPR[/]=Stack-to-Pot  "
        "[dim]Ctrl+C to stop[/]"
    )
    output.add_row(legend)

    return output


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents,
                   pot=None, street='preflop', position=None, preflop=None,
                   stack=0.0, big_blind=0.0, session=None,
                   opponents=None, opponent_stats=None,
                   is_our_turn=False, seat_state=None, active_seat=-1):
    """Print the full display to terminal."""
    clear_screen()
    display = build_display(
        hole_cards, community_cards, odds_result, bet_rec, num_opponents,
        pot, street, position, preflop, stack, big_blind, session,
        opponents, opponent_stats,
        is_our_turn, seat_state, active_seat,
    )
    console.print(display)
