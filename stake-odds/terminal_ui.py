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


def build_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents, pot=None, street='preflop'):
    """Build the full terminal display."""

    title = f"STAKE POKER ODDS  [AUTO-DETECT]  |  Opponents: {num_opponents}"

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
    cards_table.add_row(
        Text("STREET:", style="bold cyan"),
        Text(street.upper(), style="bold white")
    )
    if pot is not None:
        cards_table.add_row(
            Text("POT:", style="bold cyan"),
            Text(f"${pot:,.2f}", style="bold yellow")
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

    # Bet recommendation section
    if bet_rec:
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
            Text(bet_rec['action'], style=action_style)
        )
        bet_table.add_row(
            Text("CONFIDENCE:", style="bold"),
            Text(bet_rec['confidence'].upper(), style=action_style)
        )

        # Sizing options with highlighting
        sizings = [
            ('FOLD', 'fold'),
            ('CHECK', 'check'),
            ('25% POT', '25%'),
            ('50% POT', '50%'),
            ('75% POT', '75%'),
            ('ALL-IN', 'all-in'),
        ]

        bet_table.add_row(Text(""), Text(""))
        for label, key in sizings:
            if key == bet_rec.get('sizing', ''):
                bet_table.add_row(
                    Text(""),
                    Text(f"  >>> {label} <<<", style=f"bold {action_style}")
                )
            else:
                bet_table.add_row(
                    Text(""),
                    Text(f"      {label}", style="dim")
                )
    else:
        bet_table = Text("  Waiting for odds...", style="dim italic")

    bet_panel = Panel(bet_table, title="[bold white]Recommendation[/]", border_style="yellow")

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


def print_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents, pot=None, street='preflop'):
    """Print the full display to terminal."""
    clear_screen()
    display = build_display(hole_cards, community_cards, odds_result, bet_rec, num_opponents, pot, street)
    console.print(display)
