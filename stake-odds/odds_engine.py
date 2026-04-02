"""
Poker odds calculation engine.
Uses Monte Carlo simulation with a fast 7-card evaluator (no combinations).
"""

import random
from collections import Counter

RANKS = '23456789TJQKA'
SUITS = 'shdc'
FULL_DECK = [r + s for r in RANKS for s in SUITS]

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
    HIGH_CARD: 'High Card', ONE_PAIR: 'Pair', TWO_PAIR: 'Two Pair',
    THREE_OF_A_KIND: 'Three of a Kind', STRAIGHT: 'Straight',
    FLUSH: 'Flush', FULL_HOUSE: 'Full House',
    FOUR_OF_A_KIND: 'Four of a Kind', STRAIGHT_FLUSH: 'Straight Flush',
    ROYAL_FLUSH: 'Royal Flush',
}

RANK_VALUES = {r: i for i, r in enumerate(RANKS)}
_RV = RANK_VALUES

# Pre-built bitmask straight patterns (bit per rank, ace can be high or low)
_STRAIGHT_MASKS = []
for _lo in range(9):  # 0(2-6) through 8(T-A)
    _STRAIGHT_MASKS.append((0x1F << _lo, _lo + 4))
_STRAIGHT_MASKS.append((0x100F, 3))  # A-2-3-4-5 (ace low, high card = 5)
_STRAIGHT_MASKS.reverse()  # check highest first


def card_rank(card):
    return _RV[card[0]]


def card_suit(card):
    return card[1]


def _eval7(cards):
    """
    Evaluate the best 5-card hand from exactly 7 cards.
    Returns a comparable tuple (category, *tiebreakers). Higher is better.
    No itertools.combinations — direct bit-math approach.
    """
    ranks = [0] * 7
    suits = [0] * 7
    rcnt = [0] * 13  # count per rank
    scnt = [0] * 4   # count per suit
    suit_idx = {'s': 0, 'h': 1, 'd': 2, 'c': 3}

    for i, c in enumerate(cards):
        r = _RV[c[0]]
        s = suit_idx[c[1]]
        ranks[i] = r
        suits[i] = s
        rcnt[r] += 1
        scnt[s] += 1

    # ── flush detection ──────────────────────────────────────────────
    flush_suit = -1
    for si in range(4):
        if scnt[si] >= 5:
            flush_suit = si
            break

    if flush_suit >= 0:
        flush_ranks = sorted(
            (ranks[i] for i in range(7) if suits[i] == flush_suit), reverse=True)
        fbits = 0
        for fr in flush_ranks:
            fbits |= (1 << fr)
        for mask, high in _STRAIGHT_MASKS:
            if fbits & mask == mask:
                if high == 12:
                    return (ROYAL_FLUSH, high)
                return (STRAIGHT_FLUSH, high)
        return (FLUSH, flush_ranks[0], flush_ranks[1], flush_ranks[2],
                flush_ranks[3], flush_ranks[4])

    # ── group ranks by count ─────────────────────────────────────────
    quads = []
    trips = []
    pairs = []
    singles = []
    for r in range(12, -1, -1):
        c = rcnt[r]
        if c == 4:
            quads.append(r)
        elif c == 3:
            trips.append(r)
        elif c == 2:
            pairs.append(r)
        elif c == 1:
            singles.append(r)

    if quads:
        kicker = trips[0] if trips else (pairs[0] if pairs else singles[0])
        return (FOUR_OF_A_KIND, quads[0], kicker)

    if trips:
        if len(trips) >= 2:
            return (FULL_HOUSE, trips[0], trips[1])
        if pairs:
            return (FULL_HOUSE, trips[0], pairs[0])

    # ── straight detection (non-flush) ───────────────────────────────
    rbits = 0
    for r in range(13):
        if rcnt[r]:
            rbits |= (1 << r)
    for mask, high in _STRAIGHT_MASKS:
        if rbits & mask == mask:
            return (STRAIGHT, high)

    if trips:
        k = singles[:2] if len(singles) >= 2 else singles + pairs[:1]
        return (THREE_OF_A_KIND, trips[0], k[0] if k else 0, k[1] if len(k) > 1 else 0)

    if len(pairs) >= 2:
        kickers = singles + pairs[2:]
        kicker = kickers[0] if kickers else 0
        return (TWO_PAIR, pairs[0], pairs[1], kicker)

    if pairs:
        k = singles[:3]
        return (ONE_PAIR, pairs[0], k[0] if k else 0, k[1] if len(k) > 1 else 0,
                k[2] if len(k) > 2 else 0)

    return (HIGH_CARD, singles[0], singles[1], singles[2], singles[3], singles[4])


def evaluate_hand(cards):
    """Evaluate best hand from 5-7 cards."""
    n = len(cards)
    if n < 5:
        return (HIGH_CARD, 0)
    if n == 7:
        return _eval7(cards)
    if n == 6:
        best = None
        for skip in range(6):
            hand = cards[:skip] + cards[skip+1:]
            s = _eval7_or_5(hand)
            if best is None or s > best:
                best = s
        return best
    return _eval5(cards)


def _eval7_or_5(cards):
    if len(cards) >= 7:
        return _eval7(cards)
    return _eval5(cards)


def _eval5(cards):
    """Fast 5-card evaluator."""
    r = sorted((_RV[c[0]] for c in cards), reverse=True)
    suit_idx = {'s': 0, 'h': 1, 'd': 2, 'c': 3}
    is_flush = len(set(suit_idx[c[1]] for c in cards)) == 1

    rbits = 0
    for rv in r:
        rbits |= (1 << rv)
    is_straight = False
    straight_high = 0
    for mask, high in _STRAIGHT_MASKS:
        if rbits & mask == mask:
            is_straight = True
            straight_high = high
            break

    if is_straight and is_flush:
        return (ROYAL_FLUSH if straight_high == 12 else STRAIGHT_FLUSH, straight_high)

    cnt = [0] * 13
    for rv in r:
        cnt[rv] += 1

    quads = []; trips = []; pairs = []; singles = []
    for rv in range(12, -1, -1):
        c = cnt[rv]
        if c == 4: quads.append(rv)
        elif c == 3: trips.append(rv)
        elif c == 2: pairs.append(rv)
        elif c == 1: singles.append(rv)

    if quads:
        return (FOUR_OF_A_KIND, quads[0], singles[0] if singles else (trips[0] if trips else 0))
    if trips and pairs:
        return (FULL_HOUSE, trips[0], pairs[0])
    if is_flush:
        return (FLUSH, r[0], r[1], r[2], r[3], r[4])
    if is_straight:
        return (STRAIGHT, straight_high)
    if trips:
        return (THREE_OF_A_KIND, trips[0], singles[0], singles[1] if len(singles)>1 else 0)
    if len(pairs) >= 2:
        return (TWO_PAIR, pairs[0], pairs[1], singles[0] if singles else 0)
    if pairs:
        return (ONE_PAIR, pairs[0], singles[0], singles[1] if len(singles)>1 else 0,
                singles[2] if len(singles)>2 else 0)
    return (HIGH_CARD, r[0], r[1], r[2], r[3], r[4])


def get_hand_name(cards):
    if len(cards) < 5:
        return "Waiting for board..." if len(cards) >= 2 else "Waiting..."
    return HAND_NAMES.get(evaluate_hand(cards)[0], 'Unknown')


def monte_carlo_equity(hole_cards, community_cards, num_opponents=1,
                       num_simulations=10000, seed=None):
    """Fast Monte Carlo equity with direct 7-card evaluation."""
    if len(hole_cards) < 2:
        return {
            'equity': 0.0, 'win_pct': 0.0, 'tie_pct': 0.0,
            'lose_pct': 100.0, 'hand_name': 'No cards', 'simulations': 0
        }

    if seed is not None:
        random.seed(seed)

    known = set(hole_cards + community_cards)
    deck = [c for c in FULL_DECK if c not in known]
    need = 5 - len(community_cards)
    comm = list(community_cards)
    h0, h1 = hole_cards[0], hole_cards[1]

    wins = ties = losses = 0
    _shuffle = random.shuffle
    _e7 = _eval7

    for _ in range(num_simulations):
        _shuffle(deck)
        idx = 0

        if need > 0:
            board = comm + deck[0:need]
            idx = need
        else:
            board = comm

        our = _e7([h0, h1] + board)

        best_opp = None
        for _ in range(num_opponents):
            opp = _e7([deck[idx], deck[idx+1]] + board)
            idx += 2
            if best_opp is None or opp > best_opp:
                best_opp = opp

        if our > best_opp:
            wins += 1
        elif our == best_opp:
            ties += 1
        else:
            losses += 1

    total = wins + ties + losses
    equity = (wins + ties * 0.5) / total if total > 0 else 0

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


def _multiway_factor(num_opponents):
    """Equity requirement multiplier for multi-way pots."""
    if num_opponents <= 1:
        return 1.0
    if num_opponents == 2:
        return 1.2
    return 1.4


def _classify_bet_size(bet_amount, pot):
    """Classify a bet relative to the pot for display."""
    if pot <= 0 or bet_amount <= 0:
        return ""
    ratio = bet_amount / pot
    if ratio <= 0.25:
        return "small (1/4 pot)"
    if ratio <= 0.4:
        return "1/3 pot"
    if ratio <= 0.55:
        return "1/2 pot"
    if ratio <= 0.72:
        return "2/3 pot"
    if ratio <= 0.85:
        return "3/4 pot"
    if ratio <= 1.1:
        return "pot-sized"
    return f"overbet ({ratio:.1f}x pot)"


def get_bet_recommendation(equity, street='preflop', pot=0.0, actions=None,
                            stack=0.0, big_blind=0.0,
                            hole_cards=None, community_cards=None,
                            num_opponents=1, villain_stats=None):
    """
    Pot-odds-driven bet recommendation.

    Returns dict with action, confidence, sizing, bet_amount, notes,
    plus pot_odds, required_equity, call_amount, bet_to_pot keys.
    villain_stats: dict from OpponentTracker.get_stats() for primary villain.
    """
    act = parse_actions(actions)
    can_check = act["can_check"]
    call_amt = act["call_amount"]
    facing_bet = act["can_call"] and call_amt > 0

    pot_odds = 0.0
    required_equity = 0.0
    bet_to_pot = 0.0
    villain_range = None
    is_polarized = False
    if facing_bet and pot > 0:
        pot_odds = call_amt / (pot + call_amt)
        required_equity = pot_odds * _multiway_factor(num_opponents)
        bet_to_pot = call_amt / pot
        villain_range, is_polarized = estimate_range_from_bet_size(
            call_amt, pot, street, villain_stats)

    spr = calc_spr(stack, pot) if stack > 0 and pot > 0 else 20.0
    bet_sizes = compute_bet_sizes(pot, stack, big_blind)
    notes = []

    draw_info = {"outs": 0, "draws": [], "implied_mult": 1.0}
    board_info = {"texture": "N/A", "notes": []}
    if street != "preflop" and hole_cards and community_cards:
        board_info = analyze_board(community_cards)
        draw_info = count_draw_outs(hole_cards, community_cards)
        if draw_info["draws"]:
            notes.extend(draw_info["draws"])
        notes.extend(board_info.get("notes", []))

    effective_equity = equity * draw_info["implied_mult"]

    if villain_range is not None and facing_bet:
        effective_equity = range_equity_adjustment(effective_equity, villain_range)
        if is_polarized:
            notes.append(f"Polarized bet — villain range ~{villain_range:.0%}")
        elif villain_range < 0.30:
            notes.append(f"Tight range ~{villain_range:.0%}")

    if villain_stats and villain_stats.get("hands", 0) >= 5:
        label = villain_stats.get("label", "")
        bluff = villain_stats.get("bluff_score", 0)
        if bluff > 50:
            notes.append(f"Villain is {label} — HIGH bluff freq ({bluff})")
        elif bluff > 25:
            notes.append(f"Villain is {label} — moderate bluff freq ({bluff})")
        elif label:
            notes.append(f"Villain is {label}")

    eff_pct = effective_equity * 100

    mw = _multiway_factor(num_opponents)
    if num_opponents >= 2:
        notes.append(f"Multi-way ({num_opponents} opp) — tighter ranges")

    def _result(action, confidence, sizing_key, extra_notes=None):
        amt = bet_sizes.get(sizing_key, 0.0)
        return {
            "action": action,
            "confidence": confidence,
            "sizing": sizing_key,
            "bet_amount": amt,
            "notes": notes + (extra_notes or []),
            "spr": round(spr, 1),
            "board_texture": board_info.get("texture", "N/A"),
            "draw_outs": draw_info["outs"],
            "draw_info": draw_info["draws"],
            "pot_odds": round(pot_odds, 3),
            "required_equity": round(required_equity, 3),
            "call_amount": call_amt,
            "bet_to_pot": round(bet_to_pot, 2),
            "bet_description": _classify_bet_size(call_amt, pot) if facing_bet else "",
        }

    # --- FACING A BET (pot-odds-driven) ---
    if facing_bet:
        margin = effective_equity - required_equity

        if eff_pct >= 80 * (1 / mw):
            return _result("RAISE / ALL-IN", "monster", "all_in",
                           [f"Monster — {eff_pct:.0f}% equity crushes the {required_equity:.0%} needed"])
        if margin > 0.20:
            return _result("RAISE", "very strong", "75_pot",
                           [f"Equity {eff_pct:.0f}% far exceeds {required_equity:.0%} needed — raise for value"])
        if margin > 0.10:
            sizing = "50_pot"
            if spr < 4:
                sizing = "all_in"
                notes_extra = ["Low SPR — raise/jam for value"]
            else:
                notes_extra = [f"Equity {eff_pct:.0f}% beats {required_equity:.0%} — value raise"]
            return _result("RAISE", "strong", sizing, notes_extra)
        if effective_equity > required_equity:
            if spr < 4:
                return _result("CALL (commit)", "good", "all_in",
                               [f"Low SPR {spr:.1f} — calling commits you",
                                f"Need {required_equity:.0%}, you have {eff_pct:.0f}%"])
            return _result("CALL", "good", "min_bet",
                           [f"Need {required_equity:.0%} to call, you have {eff_pct:.0f}%"])
        if effective_equity > required_equity * 0.7:
            if draw_info["outs"] >= 8:
                return _result("CALL (drawing)", "marginal", "min_bet",
                               [f"{draw_info['outs']} outs — implied odds justify the call",
                                f"Need {required_equity:.0%}, you have {eff_pct:.0f}%"])
            return _result("FOLD (borderline)", "marginal", "min_bet",
                           [f"Need {required_equity:.0%}, you only have {eff_pct:.0f}%"])
        return _result("FOLD", "weak", "min_bet",
                       [f"Need {required_equity:.0%}, you only have {eff_pct:.0f}%"])

    # --- NOT FACING A BET ---
    if can_check:
        adj = eff_pct / mw
        if spr < 3 and adj >= 50:
            return _result("BET / JAM", "strong", "all_in",
                           [f"SPR {spr:.1f} — shove for max value"])
        if adj >= 75:
            return _result("BET", "monster", "75_pot")
        if adj >= 65:
            return _result("BET", "very strong", "67_pot")
        if adj >= 55:
            return _result("BET", "strong", "50_pot")
        if adj >= 45:
            return _result("BET", "good", "33_pot")
        if draw_info["outs"] >= 9 and board_info.get("texture") == "WET":
            return _result("BET (semi-bluff)", "good", "50_pot",
                           ["Semi-bluff with strong draw on wet board"])
        return _result("CHECK", "marginal", "min_bet")

    # --- PREFLOP / NO ACTION DATA ---
    if street == "preflop":
        adj = eff_pct / mw
        if adj >= 75:
            return _result("RAISE / ALL-IN", "very strong", "all_in")
        if adj >= 60:
            return _result("RAISE", "strong", "75_pot")
        if adj >= 50:
            return _result("RAISE", "good", "50_pot")
        if adj >= 35:
            return _result("CALL / CHECK", "marginal", "min_bet")
        return _result("FOLD", "weak", "min_bet")

    # Post-flop fallback
    adj = eff_pct / mw
    if adj >= 80:
        return _result("ALL-IN", "monster", "all_in")
    if adj >= 70:
        return _result("BET", "very strong", "75_pot")
    if adj >= 60:
        return _result("BET", "strong", "50_pot")
    if adj >= 50:
        return _result("BET", "good", "33_pot")
    if adj >= 35:
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


# ── Range estimation ──────────────────────────────────────────────────
# Approximate percentile for each canonical hand (0.0 = best, 1.0 = worst).
# Derived from solver preflop equity rankings.

_GROUP_CUTOFFS = {1: 0.03, 2: 0.06, 3: 0.14, 4: 0.21, 5: 0.30, 6: 0.50, 7: 1.0}


def hand_percentile(hole_cards):
    """Return approximate percentile (0-1) for a 2-card hand. Lower = stronger."""
    if len(hole_cards) < 2:
        return 1.0
    r1, r2 = RANK_VALUES[hole_cards[0][0]], RANK_VALUES[hole_cards[1][0]]
    s1, s2 = hole_cards[0][1], hole_cards[1][1]
    hi, lo = max(r1, r2), min(r1, r2)
    if hi == lo:
        notation = RANKS[hi] + RANKS[lo]
    else:
        notation = RANKS[hi] + RANKS[lo] + ('s' if s1 == s2 else 'o')
    from preflop_advisor import HAND_GROUP
    grp = HAND_GROUP.get(notation, 7)
    return _GROUP_CUTOFFS.get(grp, 1.0)


POSITION_OPEN_PCT = {
    "UTG": 0.14, "MP": 0.21, "CO": 0.30, "BTN": 0.50,
    "SB": 0.35, "BB": 0.50,
}


def estimate_villain_range(action_type, position=None, villain_stats=None):
    """
    Estimate a villain's hand range as a percentile based on their action
    and optionally adjust using observed HUD stats.
    Returns a float 0-1 representing what % of hands they'd play this way.
    """
    base = 0.50
    if action_type == "3bet":
        base = 0.06
    elif action_type == "raise":
        base = POSITION_OPEN_PCT.get(position or "CO", 0.30)
    elif action_type == "call":
        pos_base = POSITION_OPEN_PCT.get(position or "CO", 0.30)
        base = min(pos_base * 1.5, 0.60)
    elif action_type == "limp":
        base = 0.45

    if villain_stats and villain_stats.get("hands", 0) >= 5:
        vpip = villain_stats.get("vpip", 30)
        vpip_range = vpip / 100.0
        base = base * 0.5 + vpip_range * 0.5

    return max(0.03, min(base, 0.80))


def estimate_range_from_bet_size(bet_amount, pot, street, villain_stats=None):
    """
    Narrow villain range based on their bet sizing relative to pot.
    Bigger bets = more polarized range (very strong or bluff).
    Returns (range_pct, is_polarized).
    """
    if pot <= 0 or bet_amount <= 0:
        return 0.50, False

    ratio = bet_amount / pot

    if ratio >= 1.5:
        range_pct = 0.08
        polarized = True
    elif ratio >= 1.0:
        range_pct = 0.12
        polarized = True
    elif ratio >= 0.66:
        range_pct = 0.20
        polarized = False
    elif ratio >= 0.5:
        range_pct = 0.28
        polarized = False
    elif ratio >= 0.33:
        range_pct = 0.35
        polarized = False
    else:
        range_pct = 0.45
        polarized = False

    if street == "river":
        range_pct *= 0.75
    elif street == "turn":
        range_pct *= 0.85

    if villain_stats and villain_stats.get("hands", 0) >= 5:
        af = villain_stats.get("af", 2.0)
        bluff_score = villain_stats.get("bluff_score", 25)
        if af > 3 and bluff_score > 40:
            range_pct = min(range_pct * 1.5, 0.60)
            polarized = True
        elif af < 1.5 and bluff_score < 15:
            range_pct *= 0.7

    return max(0.03, min(range_pct, 0.80)), polarized


def range_equity_adjustment(raw_equity, villain_range_pct):
    """
    Adjust raw equity (vs random) based on villain's estimated range.
    Tighter range = villain is stronger = our equity drops.
    """
    if villain_range_pct >= 0.50:
        return raw_equity
    if villain_range_pct <= 0.05:
        return raw_equity * 0.65
    scale = 0.65 + (villain_range_pct - 0.05) * (0.35 / 0.45)
    return raw_equity * min(scale, 1.0)


def monte_carlo_equity_vs_range(hole_cards, community_cards, villain_range_pct,
                                 num_opponents=1, num_simulations=10000, seed=None):
    """
    Monte Carlo equity where opponent hands are filtered to a range.
    Uses rejection sampling — deals random opponent hands but only accepts
    those within the given percentile range.
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

    wins = ties = losses = 0
    max_rejects = 15

    for _ in range(num_simulations):
        random.shuffle(remaining_deck)
        idx = 0

        sim_board = list(community_cards)
        for _ in range(cards_needed_for_board):
            sim_board.append(remaining_deck[idx])
            idx += 1

        our_hand = evaluate_hand(hole_cards + sim_board)

        best_opp = None
        for _ in range(num_opponents):
            accepted = False
            for _attempt in range(max_rejects):
                opp_cards = [remaining_deck[idx], remaining_deck[idx + 1]]
                idx += 2
                if hand_percentile(opp_cards) <= villain_range_pct:
                    accepted = True
                    break
                if idx + 2 > len(remaining_deck):
                    break
            if not accepted:
                idx -= 2
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
    eq = (wins + ties * 0.5) / total if total > 0 else 0
    all_known = hole_cards + community_cards
    hname = get_hand_name(all_known) if len(all_known) >= 5 else _preflop_hand_name(hole_cards)

    return {
        'equity': eq,
        'win_pct': round(wins / total * 100, 1) if total > 0 else 0,
        'tie_pct': round(ties / total * 100, 1) if total > 0 else 0,
        'lose_pct': round(losses / total * 100, 1) if total > 0 else 0,
        'hand_name': hname,
        'simulations': total,
    }


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
