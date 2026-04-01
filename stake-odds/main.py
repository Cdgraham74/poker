#!/usr/bin/env python3
"""
Stake Poker Live Odds Calculator
Main entry point - ties together screen capture, odds engine, and terminal UI.

Usage:
    python main.py                  # Auto-detect mode (screen capture)
    python main.py manual           # Manual card entry mode
    python main.py calibrate        # Calibrate screen regions
    python main.py test             # Test card detection
"""

import sys
import time
import threading
import signal

from odds_engine import monte_carlo_equity, get_bet_recommendation, validate_card
from terminal_ui import print_display, console


def get_street(community_cards):
    """Determine the current street based on community cards."""
    n = len(community_cards)
    if n == 0:
        return 'preflop'
    elif n == 3:
        return 'flop'
    elif n == 4:
        return 'turn'
    elif n == 5:
        return 'river'
    return 'preflop'


def parse_cards(text):
    """Parse a space-separated string of card abbreviations."""
    cards = []
    tokens = text.strip().upper().split()
    for t in tokens:
        # Normalize: allow 10 -> T
        t = t.replace('10', 'T')
        if len(t) == 2:
            rank = t[0]
            suit = t[1].lower()
            card = rank + suit
            if validate_card(card):
                cards.append(card)
    return cards


def manual_mode():
    """
    Manual card entry mode. User types in their cards and community cards.
    Great for testing or when OCR isn't working well.
    """
    hole_cards = []
    community_cards = []
    num_opponents = 1
    pot = None

    print_help_manual()

    while True:
        # Calculate odds if we have hole cards
        odds_result = None
        bet_rec = None
        street = get_street(community_cards)

        if len(hole_cards) == 2:
            odds_result = monte_carlo_equity(
                hole_cards, community_cards,
                num_opponents=num_opponents,
                num_simulations=20000
            )
            bet_rec = get_bet_recommendation(odds_result['equity'], street)

        print_display(
            hole_cards, community_cards, odds_result, bet_rec,
            num_opponents, pot, street, manual_mode=True
        )

        try:
            cmd = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not cmd:
            continue

        parts = cmd.lower().split(maxsplit=1)
        command = parts[0]

        if command in ('q', 'quit', 'exit'):
            print("Goodbye!")
            break

        elif command == 'reset':
            hole_cards = []
            community_cards = []
            pot = None

        elif command == 'board' and len(parts) > 1:
            new_cards = parse_cards(parts[1])
            if new_cards:
                community_cards = new_cards[:5]

        elif command == 'flop' and len(parts) > 1:
            new_cards = parse_cards(parts[1])
            if len(new_cards) >= 3:
                community_cards = new_cards[:3]

        elif command == 'turn' and len(parts) > 1:
            new_cards = parse_cards(parts[1])
            if new_cards:
                if len(community_cards) >= 3:
                    community_cards = community_cards[:3] + [new_cards[0]]
                else:
                    community_cards.append(new_cards[0])

        elif command == 'river' and len(parts) > 1:
            new_cards = parse_cards(parts[1])
            if new_cards:
                if len(community_cards) >= 4:
                    community_cards = community_cards[:4] + [new_cards[0]]
                else:
                    community_cards.append(new_cards[0])

        elif command == 'opp' and len(parts) > 1:
            try:
                num_opponents = max(1, min(9, int(parts[1])))
            except ValueError:
                pass

        elif command == 'pot' and len(parts) > 1:
            try:
                pot = float(parts[1].replace(',', '').replace('$', ''))
            except ValueError:
                pass

        elif command == 'hand' and len(parts) > 1:
            new_cards = parse_cards(parts[1])
            if len(new_cards) >= 2:
                hole_cards = new_cards[:2]

        elif command == 'help':
            print_help_manual()
            input("Press Enter to continue...")

        else:
            # Try to parse as hole cards directly
            new_cards = parse_cards(cmd)
            if len(new_cards) >= 2:
                hole_cards = new_cards[:2]
            elif len(new_cards) == 1:
                console.print("[red]Need 2 cards for your hand.[/]")
                time.sleep(1)


def print_help_manual():
    """Print manual mode help."""
    console.print("""
[bold cyan]MANUAL MODE COMMANDS:[/]
  [bold]Ah Kd[/]           - Set your hole cards (any two cards)
  [bold]hand Ah Kd[/]      - Same as above
  [bold]board Qh Jh 2c[/]  - Set community cards
  [bold]flop Qh Jh 2c[/]   - Set flop (3 cards)
  [bold]turn 9s[/]          - Add turn card
  [bold]river 3d[/]         - Add river card
  [bold]opp 3[/]            - Set number of opponents (1-9)
  [bold]pot 150[/]          - Set pot size
  [bold]reset[/]            - Clear all cards
  [bold]q[/]                - Quit

[dim]Card format: Rank + Suit (e.g., Ah = Ace of hearts)
  Ranks: 2 3 4 5 6 7 8 9 T J Q K A
  Suits: s(spades) h(hearts) d(diamonds) c(clubs)[/]
""")


def auto_mode(monitor_num=0):
    """
    Automatic screen capture mode. Continuously monitors the screen
    for card changes and recalculates odds.
    """
    try:
        from card_detector import detect_all_cards, load_regions
    except ImportError as e:
        console.print(f"[red]Error importing card_detector: {e}[/]")
        console.print("[yellow]Make sure pytesseract and mss are installed:[/]")
        console.print("  pip install pytesseract mss pillow")
        console.print("\n[yellow]Falling back to manual mode...[/]")
        manual_mode()
        return

    num_opponents = 1
    prev_hole = []
    prev_community = []

    console.print("[bold cyan]Starting auto-detect mode...[/]")
    console.print("[dim]Scanning screen for poker cards. Press Ctrl+C to stop.[/]")
    console.print(f"[dim]Monitor: {monitor_num}[/]")
    time.sleep(1)

    # Signal handler for clean exit
    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    while running:
        try:
            # Detect cards on screen
            detected = detect_all_cards(monitor_num=monitor_num)
            hole_cards = detected['hole_cards']
            community_cards = detected['community_cards']
            pot = detected['pot']

            # Only recalculate if cards changed
            cards_changed = (hole_cards != prev_hole or community_cards != prev_community)

            if cards_changed and len(hole_cards) == 2:
                street = get_street(community_cards)
                odds_result = monte_carlo_equity(
                    hole_cards, community_cards,
                    num_opponents=num_opponents,
                    num_simulations=15000
                )
                bet_rec = get_bet_recommendation(odds_result['equity'], street)

                print_display(
                    hole_cards, community_cards, odds_result, bet_rec,
                    num_opponents, pot, street, manual_mode=False
                )

                prev_hole = hole_cards[:]
                prev_community = community_cards[:]

            elif not cards_changed and len(hole_cards) == 2:
                # No change, just update display with cached values
                pass
            elif len(hole_cards) < 2:
                # No cards detected - show waiting state
                if prev_hole:  # Only update if state changed
                    print_display(
                        hole_cards, community_cards, None, None,
                        num_opponents, pot, 'preflop', manual_mode=False
                    )
                    prev_hole = []
                    prev_community = []

            # Poll interval - balance between responsiveness and CPU usage
            time.sleep(0.5)

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            time.sleep(2)

    console.print("\n[bold]Stopped. Goodbye![/]")


def calibrate_mode(monitor_num=0):
    """Run calibration for screen regions."""
    try:
        from card_detector import calibrate_interactive
        calibrate_interactive(monitor_num)
    except ImportError as e:
        console.print(f"[red]Error: {e}[/]")
        console.print("[yellow]Install dependencies: pip install pytesseract mss pillow[/]")


def test_mode(monitor_num=0):
    """Test card detection."""
    try:
        from card_detector import quick_test
        quick_test(monitor_num)
    except ImportError as e:
        console.print(f"[red]Error: {e}[/]")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else 'manual'
    monitor = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0

    if mode == 'manual':
        manual_mode()
    elif mode == 'auto':
        auto_mode(monitor)
    elif mode == 'calibrate':
        calibrate_mode(monitor)
    elif mode == 'test':
        test_mode(monitor)
    elif mode == 'selftest':
        # Run odds engine self-test
        import odds_engine
        odds_engine.__name__ = '__main__'
        exec(open('odds_engine.py').read())
    else:
        console.print(f"[red]Unknown mode: {mode}[/]")
        console.print("Usage: python main.py [manual|auto|calibrate|test]")
        sys.exit(1)


if __name__ == '__main__':
    main()
