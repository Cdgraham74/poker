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


def build_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents,
                   pot=None, street='preflop', position=None, preflop=None,
                   stack=0.0, big_blind=0.0, session=None):
    """Build the full terminal display."""

    pos_str = f"  |  {position}" if position else ""
    stack_str = f"  |  Stack: ${stack:.2f}" if stack > 0 else ""
    title = f"STAKE POKER ODDS{pos_str}  |  Opp: {num_opponents}{stack_str}"

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

    cards_panel = Panel(cards_table, title="[bold white]Cards[/]", border_style="blue")

    # Odds section
    if odds_result and odds_result.get('simulations', 0) > 0:
        odds_table = Table(show_header=False, box=None, padding=(0, 1))
        odds_table.add_column(width=18)
        odds_table.add_column()

        odds_table.add_row(
            Text("EQUITY:", style="bold"),
            equity_bar(odds_result['equity'] * 100)
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

    # Preflop GTO section (replaces generic recommendation preflop)
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
            Text("POSITION:", style="bold"),
            Text(preflop["position"], style="bold white")
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

        spr_val = bet_rec.get("spr", 0)
        texture = bet_rec.get("board_texture", "N/A")
        draw_outs = bet_rec.get("draw_outs", 0)

        meta_parts = []
        if spr_val > 0:
            meta_parts.append(f"SPR {spr_val}")
        if texture != "N/A":
            tex_style = {"WET": "red", "SEMI-WET": "yellow", "DRY": "green"}.get(texture, "white")
            meta_parts.append(f"Board: {texture}")
        if draw_outs > 0:
            meta_parts.append(f"{draw_outs} outs")
        if meta_parts:
            bet_table.add_row(
                Text("CONTEXT:", style="dim"),
                Text("  |  ".join(meta_parts), style="white")
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
    output.add_row(
        Panel(
            Text(title, style="bold white", justify="center"),
            border_style="bright_blue",
            box=box.DOUBLE,
        )
    )
    output.add_row(cards_panel)
    output.add_row(odds_panel)
    output.add_row(bet_panel)

    if session and session.get("hands_played", 0) > 0:
        pnl = session["pnl"]
        pnl_color = "green" if pnl >= 0 else "red"
        sess_table = Table(show_header=False, box=None, padding=(0, 1))
        sess_table.add_column(width=18)
        sess_table.add_column()

        sess_table.add_row(
            Text("P&L:", style="bold"),
            Text(f"${pnl:+.2f}", style=f"bold {pnl_color}")
        )
        sess_table.add_row(
            Text("HANDS:", style="bold"),
            Text(
                f"{session['hands_played']}  "
                f"({session['wins']}W / {session['losses']}L / {session['breakeven']}B)",
                style="white"
            )
        )
        bb_hr = session.get("bb_per_hour", 0)
        bb_color = "green" if bb_hr >= 0 else "red"
        sess_table.add_row(
            Text("BB/HR:", style="bold"),
            Text(f"{bb_hr:+.1f}", style=f"bold {bb_color}")
        )
        sess_table.add_row(
            Text("TIME:", style="dim"),
            Text(f"{session['elapsed_min']:.0f} min", style="dim")
        )

        output.add_row(
            Panel(sess_table, title="[bold white]Session[/]", border_style="cyan")
        )

    output.add_row(
        Text(
            "Auto-scanning screen... Press Ctrl+C to stop",
            style="dim"
        )
    )

    return output


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents,
                   pot=None, street='preflop', position=None, preflop=None,
                   stack=0.0, big_blind=0.0, session=None):
    """Print the full display to terminal."""
    clear_screen()
    display = build_display(
        hole_cards, community_cards, odds_result, bet_rec, num_opponents,
        pot, street, position, preflop, stack, big_blind, session,
    )
    console.print(display)
