"""
Poker odds calculation engine.
Uses Monte Carlo simulation for fast, accurate equity calculations.
Supports 1 player vs N unknown opponents.
"""

import random
from itertools import combinations
from collections import Counter

# All 52 cards
RANKS = '23456789TJQKA'
SUITS = 'shdc'
FULL_DECK = [r + s for r in RANKS for s in SUITS]

# Hand ranking constants
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8
ROYAL_FLUSH = 9

HAND_NAMES = {
    HIGH_CARD: 'High Card',
    ONE_PAIR: 'Pair',
    TWO_PAIR: 'Two Pair',
    THREE_OF_A_KIND: 'Three of a Kind',
    STRAIGHT: 'Straight',
    FLUSH: 'Flush',
    FULL_HOUSE: 'Full House',
    FOUR_OF_A_KIND: 'Four of a Kind',
    STRAIGHT_FLUSH: 'Straight Flush',
    ROYAL_FLUSH: 'Royal Flush',
}

RANK_VALUES = {r: i for i, r in enumerate(RANKS)}


def card_rank(card):
    return RANK_VALUES[card[0]]


def card_suit(card):
    return card[1]


def evaluate_hand(cards):
    """
    Evaluate the best 5-card poker hand from a set of cards (5-7 cards).
    Returns (hand_rank, tiebreakers) tuple for comparison.
    Higher is better.
    """
    if len(cards) < 5:
        return (HIGH_CARD, [0])

    best = None
    card_combos = combinations(cards, 5) if len(cards) > 5 else [cards]

    for combo in card_combos:
        score = _evaluate_five(list(combo))
        if best is None or score > best:
            best = score

    return best


def _evaluate_five(cards):
    """Evaluate exactly 5 cards. Returns (category, tiebreakers)."""
    ranks = sorted([card_rank(c) for c in cards], reverse=True)
    suits = [card_suit(c) for c in cards]

    rank_counts = Counter(ranks)
    is_flush = len(set(suits)) == 1

    # Check for straight
    unique_ranks = sorted(set(ranks), reverse=True)
    is_straight = False
    straight_high = 0

    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
            straight_high = unique_ranks[0]
        # Ace-low straight (A-2-3-4-5)
        elif unique_ranks == [12, 3, 2, 1, 0]:
            is_straight = True
            straight_high = 3  # 5-high straight

    if is_straight and is_flush:
        if straight_high == 12:  # Ace-high straight flush = Royal
            return (ROYAL_FLUSH, [straight_high])
        return (STRAIGHT_FLUSH, [straight_high])

    # Group by count for pair/trips/quads detection
    groups = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if groups[0][1] == 4:
        kicker = [g[0] for g in groups if g[1] != 4][0]
        return (FOUR_OF_A_KIND, [groups[0][0], kicker])

    if groups[0][1] == 3 and groups[1][1] == 2:
        return (FULL_HOUSE, [groups[0][0], groups[1][0]])

    if is_flush:
        return (FLUSH, ranks)

    if is_straight:
        return (STRAIGHT, [straight_high])

    if groups[0][1] == 3:
        kickers = sorted([g[0] for g in groups if g[1] != 3], reverse=True)
        return (THREE_OF_A_KIND, [groups[0][0]] + kickers)

    if groups[0][1] == 2 and groups[1][1] == 2:
        pairs = sorted([g[0] for g in groups if g[1] == 2], reverse=True)
        kicker = [g[0] for g in groups if g[1] == 1][0]
        return (TWO_PAIR, pairs + [kicker])

    if groups[0][1] == 2:
        kickers = sorted([g[0] for g in groups if g[1] != 2], reverse=True)
        return (ONE_PAIR, [groups[0][0]] + kickers)

    return (HIGH_CARD, ranks)


def get_hand_name(cards):
    """Get the name of the best hand from a set of cards."""
    if len(cards) < 5:
        if len(cards) < 2:
            return "Waiting..."
        return "Waiting for board..."
    score = evaluate_hand(cards)
    return HAND_NAMES.get(score[0], 'Unknown')


def monte_carlo_equity(hole_cards, community_cards, num_opponents=1, num_simulations=10000):
    """
    Calculate equity using Monte Carlo simulation.

    Args:
        hole_cards: list of 2 card strings, e.g. ['Ah', 'Kd']
        community_cards: list of 0-5 card strings
        num_opponents: number of opponents (default 1)
        num_simulations: number of random simulations to run

    Returns:
        dict with:
            'equity': float (0.0-1.0, your win probability)
            'win_pct': float (0-100)
            'tie_pct': float (0-100)
            'lose_pct': float (0-100)
            'hand_name': str (current best hand name)
            'simulations': int
    """
    if len(hole_cards) < 2:
        return {
            'equity': 0.0, 'win_pct': 0.0, 'tie_pct': 0.0,
            'lose_pct': 100.0, 'hand_name': 'No cards', 'simulations': 0
        }

    known_cards = set(hole_cards + community_cards)
    remaining_deck = [c for c in FULL_DECK if c not in known_cards]
    cards_needed_for_board = 5 - len(community_cards)

    wins = 0
    ties = 0
    losses = 0

    for _ in range(num_simulations):
        # Shuffle remaining deck
        random.shuffle(remaining_deck)

        idx = 0

        # Deal remaining community cards
        sim_board = list(community_cards)
        for _ in range(cards_needed_for_board):
            sim_board.append(remaining_deck[idx])
            idx += 1

        # Evaluate our hand
        our_hand = evaluate_hand(hole_cards + sim_board)

        # Deal and evaluate opponent hands
        best_opp = None
        for _ in range(num_opponents):
            opp_cards = [remaining_deck[idx], remaining_deck[idx + 1]]
            idx += 2
            opp_hand = evaluate_hand(opp_cards + sim_board)
            if best_opp is None or opp_hand > best_opp:
                best_opp = opp_hand

        if our_hand > best_opp:
            wins += 1
        elif our_hand == best_opp:
            ties += 1
        else:
            losses += 1

    total = wins + ties + losses
    equity = (wins + ties * 0.5) / total if total > 0 else 0

    # Current hand name
    all_known = hole_cards + community_cards
    hand_name = get_hand_name(all_known) if len(all_known) >= 5 else _preflop_hand_name(hole_cards)

    return {
        'equity': equity,
        'win_pct': round(wins / total * 100, 1) if total > 0 else 0,
        'tie_pct': round(ties / total * 100, 1) if total > 0 else 0,
        'lose_pct': round(losses / total * 100, 1) if total > 0 else 0,
        'hand_name': hand_name,
        'simulations': total,
    }


def _preflop_hand_name(hole_cards):
    """Describe a preflop hand like 'AKs' or 'QJo'."""
    if len(hole_cards) < 2:
        return "..."
    r1, r2 = card_rank(hole_cards[0]), card_rank(hole_cards[1])
    s1, s2 = card_suit(hole_cards[0]), card_suit(hole_cards[1])

    high = max(r1, r2)
    low = min(r1, r2)
    suited = 's' if s1 == s2 else 'o'

    high_char = RANKS[high]
    low_char = RANKS[low]

    if high == low:
        return f"Pocket {high_char}{low_char}"
    return f"{high_char}{low_char}{suited}"


def get_bet_recommendation(equity, street='preflop'):
    """
    Get bet sizing recommendation based on equity.

    Args:
        equity: float 0.0-1.0
        street: 'preflop', 'flop', 'turn', 'river'

    Returns:
        dict with 'action', 'confidence', 'sizing' keys
    """
    pct = equity * 100

    if street == 'preflop':
        if pct >= 75:
            return {'action': 'RAISE / ALL-IN', 'confidence': 'very strong', 'sizing': 'all-in'}
        elif pct >= 60:
            return {'action': 'RAISE 75% POT', 'confidence': 'strong', 'sizing': '75%'}
        elif pct >= 50:
            return {'action': 'RAISE 50% POT', 'confidence': 'good', 'sizing': '50%'}
        elif pct >= 40:
            return {'action': 'CALL / CHECK', 'confidence': 'marginal', 'sizing': 'check'}
        else:
            return {'action': 'FOLD', 'confidence': 'weak', 'sizing': 'fold'}
    else:
        # Post-flop recommendations
        if pct >= 80:
            return {'action': 'ALL-IN', 'confidence': 'monster', 'sizing': 'all-in'}
        elif pct >= 70:
            return {'action': 'BET 75% POT', 'confidence': 'very strong', 'sizing': '75%'}
        elif pct >= 60:
            return {'action': 'BET 50% POT', 'confidence': 'strong', 'sizing': '50%'}
        elif pct >= 50:
            return {'action': 'BET 25% POT', 'confidence': 'good', 'sizing': '25%'}
        elif pct >= 40:
            return {'action': 'CHECK / CALL', 'confidence': 'marginal', 'sizing': 'check'}
        elif pct >= 25:
            return {'action': 'CHECK / FOLD', 'confidence': 'weak', 'sizing': 'check'}
        else:
            return {'action': 'FOLD', 'confidence': 'very weak', 'sizing': 'fold'}


def validate_card(card_str):
    """Validate a card string like 'Ah' or '2c'."""
    if not card_str or len(card_str) != 2:
        return False
    return card_str[0] in RANKS and card_str[1] in SUITS


# Quick self-test
if __name__ == '__main__':
    print("=== Odds Engine Self-Test ===\n")

    # Test 1: AA vs random (should be ~85%)
    result = monte_carlo_equity(['As', 'Ah'], [], num_opponents=1, num_simulations=20000)
    print(f"AA preflop vs 1 opponent: {result['win_pct']}% win, {result['tie_pct']}% tie")
    print(f"  Hand: {result['hand_name']}, Equity: {result['equity']:.3f}")

    # Test 2: AKs with a flop
    result = monte_carlo_equity(['Ah', 'Kh'], ['Qh', 'Jh', '2c'], num_opponents=1, num_simulations=20000)
    print(f"\nAKh on Qh Jh 2c flop: {result['win_pct']}% win, {result['tie_pct']}% tie")
    print(f"  Hand: {result['hand_name']}, Equity: {result['equity']:.3f}")

    # Test 3: Bet recommendation
    rec = get_bet_recommendation(result['equity'], 'flop')
    print(f"  Recommendation: {rec['action']} ({rec['confidence']})")

    # Test 4: 72o vs random (should be ~35%)
    result = monte_carlo_equity(['7h', '2c'], [], num_opponents=1, num_simulations=20000)
    print(f"\n72o preflop vs 1 opponent: {result['win_pct']}% win")
    print(f"  Recommendation: {get_bet_recommendation(result['equity'], 'preflop')['action']}")
