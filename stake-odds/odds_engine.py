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


def monte_carlo_equity(hole_cards, community_cards, num_opponents=1, num_simulations=10000, seed=None):
    """
    Calculate equity using Monte Carlo simulation.

    Args:
        hole_cards: list of 2 card strings, e.g. ['Ah', 'Kd']
        community_cards: list of 0-5 card strings
        num_opponents: number of opponents (default 1)
        num_simulations: number of random simulations to run
        seed: optional; same cards -> same result (stable display when refreshing)

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

    if seed is not None:
        random.seed(seed)

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


def parse_actions(raw_actions):
    """
    Parse Stake.us tableActionsModel.actions into usable info.

    Known action types:  1=fold, 2=check, 3=call, 9=raise/bet, 15=check(alt)
    Returns dict with can_check, can_call, call_amount, min_raise, is_allin_raise.
    """
    can_check = False
    can_call = False
    call_amount = 0.0
    min_raise = 0.0
    is_allin_raise = False

    for a in (raw_actions or []):
        t = a.get("type", 0)
        cash = a.get("cash", 0) or 0
        if t in (2, 15):
            can_check = True
        elif t == 3:
            can_call = True
            call_amount = float(cash)
        elif t == 9:
            min_raise = float(cash)
            is_allin_raise = bool(a.get("isAllIn", False))

    return {
        "can_check": can_check,
        "can_call": can_call,
        "call_amount": call_amount,
        "min_raise": min_raise,
        "is_allin_raise": is_allin_raise,
    }


def get_bet_recommendation(equity, street='preflop', pot=0.0, actions=None,
                            stack=0.0, big_blind=0.0,
                            hole_cards=None, community_cards=None):
    """
    Context-aware bet recommendation using equity, pot odds, SPR, board texture,
    implied odds, and available actions.

    Returns dict with 'action', 'confidence', 'sizing', 'bet_amount', 'notes' keys.
    """
    pct = equity * 100
    act = parse_actions(actions)
    can_check = act["can_check"]
    call_amt = act["call_amount"]
    facing_bet = act["can_call"] and call_amt > 0

    pot_odds = 0.0
    if facing_bet and pot > 0:
        pot_odds = call_amt / (pot + call_amt)

    spr = calc_spr(stack, pot) if stack > 0 and pot > 0 else 20.0
    bet_sizes = compute_bet_sizes(pot, stack, big_blind)
    notes = []

    # Board and draw analysis for post-flop
    draw_info = {"outs": 0, "draws": [], "implied_mult": 1.0}
    board_info = {"texture": "N/A", "notes": []}
    if street != "preflop" and hole_cards and community_cards:
        board_info = analyze_board(community_cards)
        draw_info = count_draw_outs(hole_cards, community_cards)
        if draw_info["draws"]:
            notes.extend(draw_info["draws"])
        notes.extend(board_info.get("notes", []))

    effective_equity = equity * draw_info["implied_mult"]
    eff_pct = effective_equity * 100

    def _result(action, confidence, sizing_key, extra_notes=None):
        amt = bet_sizes.get(sizing_key, 0.0)
        r = {
            "action": action,
            "confidence": confidence,
            "sizing": sizing_key,
            "bet_amount": amt,
            "notes": notes + (extra_notes or []),
            "spr": round(spr, 1),
            "board_texture": board_info.get("texture", "N/A"),
            "draw_outs": draw_info["outs"],
        }
        return r

    # --- FACING A BET ---
    if facing_bet:
        if eff_pct >= 80:
            return _result("RAISE / ALL-IN", "monster", "all_in")
        if eff_pct >= 65:
            return _result("RAISE", "very strong", "75_pot")
        if effective_equity > pot_odds * 1.5:
            return _result("RAISE", "strong", "50_pot")
        if effective_equity > pot_odds:
            if spr < 4:
                return _result("CALL (low SPR - consider jam)", "good", "all_in",
                               ["Low SPR: calling commits you"])
            return _result("CALL", "good", "min_bet",
                           [f"Pot odds {pot_odds:.0%}, you have {eff_pct:.0f}%"])
        if effective_equity > pot_odds * 0.7:
            if draw_info["outs"] >= 8:
                return _result("CALL (drawing)", "marginal", "min_bet",
                               [f"{draw_info['outs']} outs with implied odds"])
            return _result("CALL (borderline)", "marginal", "min_bet")
        return _result("FOLD", "weak", "min_bet")

    # --- NOT FACING A BET ---
    if can_check:
        if spr < 3 and eff_pct >= 50:
            return _result("BET / JAM", "strong", "all_in",
                           ["Low SPR: shove for max value"])
        if eff_pct >= 80:
            return _result("BET", "monster", "75_pot")
        if eff_pct >= 70:
            return _result("BET", "very strong", "67_pot")
        if eff_pct >= 60:
            return _result("BET", "strong", "50_pot")
        if eff_pct >= 50:
            return _result("BET", "good", "33_pot")
        if draw_info["outs"] >= 9 and board_info.get("texture") == "WET":
            return _result("BET (semi-bluff)", "good", "50_pot",
                           ["Semi-bluff with strong draw"])
        return _result("CHECK", "marginal", "min_bet")

    # --- PREFLOP / NO ACTION DATA ---
    if street == "preflop":
        if pct >= 75:
            return _result("RAISE / ALL-IN", "very strong", "all_in")
        if pct >= 60:
            return _result("RAISE", "strong", "75_pot")
        if pct >= 50:
            return _result("RAISE", "good", "50_pot")
        if pct >= 35:
            return _result("CALL / CHECK", "marginal", "min_bet")
        return _result("FOLD", "weak", "min_bet")

    # Post-flop fallback
    if eff_pct >= 80:
        return _result("ALL-IN", "monster", "all_in")
    if eff_pct >= 70:
        return _result("BET", "very strong", "75_pot")
    if eff_pct >= 60:
        return _result("BET", "strong", "50_pot")
    if eff_pct >= 50:
        return _result("BET", "good", "33_pot")
    if eff_pct >= 35:
        return _result("CHECK / CALL", "marginal", "min_bet")
    return _result("CHECK / FOLD", "weak", "min_bet")


def validate_card(card_str):
    """Validate a card string like 'Ah' or '2c'."""
    if not card_str or len(card_str) != 2:
        return False
    return card_str[0] in RANKS and card_str[1] in SUITS


def calc_spr(stack, pot):
    """Stack-to-Pot Ratio. Drives post-flop commitment decisions."""
    if pot <= 0:
        return 999.0
    return stack / pot


def spr_advice(spr):
    """Strategic guidance based on SPR."""
    if spr < 4:
        return "LOW", "Commit with top pair+. Push/fold territory."
    if spr < 8:
        return "MEDIUM", "Two pair+ to commit. Top pair is a bluff-catcher."
    if spr < 13:
        return "HIGH", "Need strong hands to stack off. Sets/straights/flushes."
    return "DEEP", "Speculative hands gain value. Play for implied odds."


def analyze_board(community_cards):
    """
    Analyze board texture for strategic context.

    Returns dict with:
        texture:      'DRY' / 'SEMI-WET' / 'WET'
        flush_draw:   bool  (3 of same suit on board)
        flush_made:   bool  (4+ of same suit on board)
        paired:       bool  (board has a pair)
        trips_board:  bool  (board has three of a kind)
        straight_draw: bool (3+ connected cards)
        high_board:   bool  (2+ cards T or higher)
        notes:        list of str
    """
    if len(community_cards) < 3:
        return {"texture": "N/A", "notes": []}

    ranks = [card_rank(c) for c in community_cards]
    suits = [card_suit(c) for c in community_cards]

    suit_counts = Counter(suits)
    rank_counts = Counter(ranks)
    max_suit = max(suit_counts.values())
    max_rank = max(rank_counts.values())

    flush_draw = max_suit == 3
    flush_made = max_suit >= 4
    paired = max_rank >= 2
    trips_board = max_rank >= 3

    sorted_ranks = sorted(set(ranks))
    connected = 0
    for i in range(len(sorted_ranks) - 1):
        if sorted_ranks[i + 1] - sorted_ranks[i] <= 2:
            connected += 1
    straight_draw = connected >= 2

    high_board = sum(1 for r in ranks if r >= 8) >= 2  # T or higher

    wetness = 0
    notes = []
    if flush_made:
        wetness += 3
        notes.append("FLUSH on board")
    elif flush_draw:
        wetness += 2
        notes.append("Flush draw possible")
    if straight_draw:
        wetness += 2
        notes.append("Straight draw possible")
    if paired:
        wetness += 1
        notes.append("Paired board")
    if trips_board:
        notes.append("Trips on board")
    if not high_board:
        notes.append("Low board")

    if wetness >= 3:
        texture = "WET"
    elif wetness >= 1:
        texture = "SEMI-WET"
    else:
        texture = "DRY"

    return {
        "texture": texture,
        "flush_draw": flush_draw,
        "flush_made": flush_made,
        "paired": paired,
        "trips_board": trips_board,
        "straight_draw": straight_draw,
        "high_board": high_board,
        "notes": notes,
    }


def count_draw_outs(hole_cards, community_cards):
    """
    Count drawing outs for flush and straight draws.
    Returns dict with outs count, draw types, and implied odds multiplier.
    """
    if len(community_cards) < 3 or len(hole_cards) < 2:
        return {"outs": 0, "draws": [], "implied_mult": 1.0}

    all_cards = hole_cards + community_cards
    ranks = [card_rank(c) for c in all_cards]
    suits = [card_suit(c) for c in all_cards]
    board_suits = [card_suit(c) for c in community_cards]

    draws = []
    outs = 0

    # Flush draw: 4 of same suit among all cards, and at least 2 from board
    suit_counts = Counter(suits)
    board_suit_counts = Counter(board_suits)
    for s, cnt in suit_counts.items():
        if cnt == 4 and board_suit_counts.get(s, 0) >= 2:
            outs += 9
            draws.append("FLUSH DRAW (9 outs)")
            break

    # Open-ended straight draw: 4 consecutive ranks
    unique_ranks = sorted(set(ranks))
    has_oesd = False
    has_gutshot = False
    for i in range(len(unique_ranks)):
        consec = [unique_ranks[i]]
        for j in range(i + 1, len(unique_ranks)):
            if unique_ranks[j] - consec[-1] <= 2:
                consec.append(unique_ranks[j])
            else:
                break
        span = consec[-1] - consec[0]
        if len(consec) >= 4 and span == 3:
            has_oesd = True
        elif len(consec) >= 4 and span == 4:
            has_gutshot = True

    if has_oesd:
        outs += 8
        draws.append("OPEN-ENDED STRAIGHT (8 outs)")
    elif has_gutshot:
        outs += 4
        draws.append("GUTSHOT STRAIGHT (4 outs)")

    # Overcards (2 cards above the highest board card)
    if len(community_cards) >= 3:
        max_board = max(card_rank(c) for c in community_cards)
        overcards = sum(1 for c in hole_cards if card_rank(c) > max_board)
        if overcards == 2 and outs == 0:
            outs += 6
            draws.append(f"2 OVERCARDS (6 outs)")
        elif overcards == 1 and outs > 0:
            outs += 3
            draws.append(f"1 OVERCARD (+3 outs)")

    # Implied odds multiplier: more outs = more implied odds value
    if outs >= 12:
        implied_mult = 1.6
    elif outs >= 9:
        implied_mult = 1.4
    elif outs >= 6:
        implied_mult = 1.2
    else:
        implied_mult = 1.0

    return {"outs": outs, "draws": draws, "implied_mult": implied_mult}


def compute_bet_sizes(pot, stack, big_blind):
    """Compute exact dollar bet sizes for the current situation."""
    sizes = {}
    sizes["min_bet"] = big_blind if big_blind > 0 else 0.0
    sizes["25_pot"] = round(pot * 0.25, 2)
    sizes["33_pot"] = round(pot * 0.33, 2)
    sizes["50_pot"] = round(pot * 0.50, 2)
    sizes["67_pot"] = round(pot * 0.67, 2)
    sizes["75_pot"] = round(pot * 0.75, 2)
    sizes["pot"] = round(pot, 2)
    sizes["all_in"] = round(stack, 2)
    return sizes


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
