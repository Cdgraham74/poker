"""
GTO preflop advisor for 6-max No-Limit Hold'em cash games.

Based on solver-derived opening/defending ranges at 100BB effective stacks.
Hand groups, position-based ranges, and action-aware recommendations.
"""

RANKS = "23456789TJQKA"
RANK_VAL = {r: i for i, r in enumerate(RANKS)}


def classify_hand(hole_cards):
    """
    Convert hole cards like ['Kc','Jh'] to canonical notation.
    Returns (notation, is_suited, is_pair, high_rank, low_rank).
    """
    r1, r2 = RANK_VAL[hole_cards[0][0]], RANK_VAL[hole_cards[1][0]]
    s1, s2 = hole_cards[0][1], hole_cards[1][1]
    suited = s1 == s2
    hi, lo = max(r1, r2), min(r1, r2)
    hi_c, lo_c = RANKS[hi], RANKS[lo]

    if hi == lo:
        return hi_c + lo_c, False, True, hi, lo
    tag = "s" if suited else "o"
    return hi_c + lo_c + tag, suited, False, hi, lo


# ── Hand groups (solver-derived, 6-max 100BB) ───────────────────────
# Lower group = stronger. Group 1 is premium, group 7 is trash.

_RAW_GROUPS = {
    1: [  # Premium — always raise, always 3-bet
        "AA", "KK", "QQ", "AKs", "AKo",
    ],
    2: [  # Very strong — raise all positions, 3-bet frequently
        "JJ", "TT", "AQs", "AQo", "AJs",
    ],
    3: [  # Strong — raise from UTG+, defend vs 3-bet selectively
        "99", "88", "ATs", "A5s", "A4s", "A3s", "A2s",
        "KQs", "KJs", "QJs", "JTs", "T9s", "98s",
    ],
    4: [  # Good — raise from MP/HJ+
        "77", "66", "A9s", "A8s", "A7s", "A6s",
        "KTs", "QTs", "87s", "76s", "AJo", "KQo",
    ],
    5: [  # Decent — raise from CO+
        "55", "44", "33", "22",
        "K9s", "K8s", "Q9s", "J9s", "T8s",
        "97s", "86s", "75s", "65s", "54s",
        "ATo", "KJo", "QJo", "JTo",
    ],
    6: [  # Speculative — raise from BTN/SB only
        "K7s", "K6s", "K5s", "K4s", "K3s", "K2s",
        "Q8s", "Q7s", "Q6s", "Q5s", "Q4s", "Q3s", "Q2s",
        "J8s", "J7s", "J6s", "J5s", "J4s",
        "T7s", "T6s", "T5s",
        "96s", "85s", "74s", "64s", "53s", "43s",
        "A9o", "A8o", "A7o", "A6o", "A5o", "A4o", "A3o", "A2o",
        "KTo", "K9o", "QTo", "Q9o", "J9o", "T9o",
    ],
}

HAND_GROUP = {}
for grp, hands in _RAW_GROUPS.items():
    for h in hands:
        HAND_GROUP[h] = grp

GROUP_LABEL = {
    1: "PREMIUM",
    2: "VERY STRONG",
    3: "STRONG",
    4: "GOOD",
    5: "DECENT",
    6: "SPECULATIVE",
    7: "TRASH",
}

# ── Position-based playability ──────────────────────────────────────
# Maximum hand group that should be OPENED (RFI) from each position.

OPEN_RANGE = {
    "UTG": 3,
    "MP":  4,
    "CO":  5,
    "BTN": 6,
    "SB":  5,
    "BB":  6,   # BB defends wide but doesn't open
}

# Maximum hand group for CALLING / 3-BETTING when facing a single raise.
FACING_RAISE = {
    "UTG": 2,
    "MP":  2,
    "CO":  3,
    "BTN": 4,
    "SB":  3,
    "BB":  5,  # BB defends wide due to pot odds
}

# Maximum hand group for continuing vs a 3-bet.
FACING_3BET = {
    "UTG": 1,
    "MP":  1,
    "CO":  2,
    "BTN": 2,
    "SB":  2,
    "BB":  2,
}


def get_position(dealer_seat_idx, our_seat_idx, occupied_seat_indices):
    """
    Determine our table position (UTG/MP/CO/BTN/SB/BB).

    Args:
        dealer_seat_idx: seat index of the dealer button
        our_seat_idx: our seat index
        occupied_seat_indices: sorted list of occupied seat indices
    """
    seats = sorted(set(occupied_seat_indices))
    n = len(seats)
    if n < 2:
        return "BTN"

    if dealer_seat_idx not in seats:
        return "UTG"

    di = seats.index(dealer_seat_idx)

    order = []
    for offset in range(n):
        order.append(seats[(di + offset) % n])

    if our_seat_idx not in order:
        return "UTG"
    my_pos = order.index(our_seat_idx)

    if my_pos == 0:
        return "BTN"
    if n >= 3 and my_pos == 1:
        return "SB"
    if n >= 3 and my_pos == 2:
        return "BB"
    if n == 2 and my_pos == 1:
        return "BB"

    remaining = n - 3
    pos_from_utg = my_pos - 3

    if remaining <= 1:
        return "UTG"
    if remaining == 2:
        return "UTG" if pos_from_utg == 0 else "CO"
    if remaining == 3:
        if pos_from_utg == 0:
            return "UTG"
        if pos_from_utg == 1:
            return "MP"
        return "CO"

    third = remaining / 3.0
    if pos_from_utg < third:
        return "UTG"
    if pos_from_utg < 2 * third:
        return "MP"
    return "CO"


def preflop_raise_size(position, big_blind, num_limpers=0):
    """GTO-recommended open raise size by position."""
    if big_blind <= 0:
        return 0.0
    multiplier = {"UTG": 3.0, "MP": 2.75, "CO": 2.5, "BTN": 2.5, "SB": 3.0, "BB": 3.0}
    base = multiplier.get(position, 2.5) * big_blind
    return round(base + num_limpers * big_blind, 2)


def preflop_advice(hole_cards, position, facing_raise=False, call_amount=0.0,
                   pot=0.0, big_blind=0.0, stack=0.0):
    """
    GTO-based preflop recommendation.

    Returns dict with:
        hand_notation:  str   'KJo', 'AQs', 'TT'
        hand_group:     int   1-7
        hand_tier:      str   'PREMIUM', 'STRONG', etc.
        position:       str   'UTG', 'CO', 'BTN', etc.
        action:         str   'RAISE', 'CALL', 'FOLD', '3-BET'
        reason:         str   human-readable explanation
        in_range:       bool  whether this hand is in your opening range
        sizing:         str   sizing advice
    """
    notation, suited, is_pair, hi, lo = classify_hand(hole_cards)
    group = HAND_GROUP.get(notation, 7)
    tier = GROUP_LABEL.get(group, "TRASH")

    raise_amt = preflop_raise_size(position, big_blind)
    three_bet_amt = round(call_amount * 3, 2) if call_amount > 0 else round(raise_amt * 3, 2)
    stack_bb = stack / big_blind if big_blind > 0 else 0

    result = {
        "hand_notation": notation,
        "hand_group": group,
        "hand_tier": tier,
        "position": position,
        "action": "FOLD",
        "reason": "",
        "in_range": False,
        "sizing": "fold",
        "bet_amount": 0.0,
        "stack_bb": round(stack_bb, 1),
    }

    if facing_raise:
        max_group = FACING_RAISE.get(position, 3)
        if group <= max_group:
            result["in_range"] = True
            if group <= 1:
                result["action"] = "3-BET"
                result["bet_amount"] = three_bet_amt
                result["reason"] = f"{notation} is {tier} -- 3-bet for value"
                result["sizing"] = f"3-BET to ${three_bet_amt:.2f}"
            elif group <= 2 and position in ("BTN", "CO", "BB"):
                result["action"] = "3-BET / CALL"
                result["bet_amount"] = three_bet_amt
                result["reason"] = f"{notation} is {tier} from {position} -- 3-bet or call"
                result["sizing"] = f"3-BET ${three_bet_amt:.2f} or CALL ${call_amount:.2f}"
            else:
                if pot > 0 and call_amount > 0:
                    pot_odds = call_amount / (pot + call_amount)
                    result["reason"] = (
                        f"{notation} is {tier} -- call from {position} "
                        f"(pot odds {pot_odds:.0%})"
                    )
                else:
                    result["reason"] = f"{notation} is {tier} -- call from {position}"
                result["action"] = "CALL"
                result["bet_amount"] = call_amount
                result["sizing"] = f"CALL ${call_amount:.2f}"
        else:
            result["action"] = "FOLD"
            result["reason"] = (
                f"{notation} is {tier} -- too weak to call a raise from {position}"
            )
            result["sizing"] = "FOLD"
    else:
        max_group = OPEN_RANGE.get(position, 3)
        if group <= max_group:
            result["in_range"] = True
            result["action"] = "RAISE"
            result["bet_amount"] = raise_amt
            if group <= 1:
                result["reason"] = f"{notation} is {tier} -- always raise"
            elif group <= 2:
                result["reason"] = f"{notation} is {tier} -- raise from any position"
            else:
                result["reason"] = f"{notation} is {tier} -- in range from {position}"
            result["sizing"] = f"RAISE to ${raise_amt:.2f}"
        else:
            if position == "BB":
                result["action"] = "CHECK"
                result["reason"] = f"{notation} from BB -- check, not worth raising"
                result["sizing"] = "CHECK"
                result["in_range"] = True
            else:
                diff = group - max_group
                if diff == 1:
                    result["reason"] = (
                        f"{notation} is {tier} -- just outside {position} range, fold"
                    )
                else:
                    result["reason"] = (
                        f"{notation} is {tier} -- not in {position} opening range"
                    )
                result["action"] = "FOLD"
                result["sizing"] = "FOLD"

    return result


# ── Quick self-test ──────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        (["As", "Kh"], "UTG", False),
        (["As", "Kh"], "BTN", False),
        (["Kc", "Jh"], "UTG", False),
        (["Kc", "Jh"], "CO", False),
        (["Kc", "Jh"], "BTN", False),
        (["Kc", "Jh"], "BTN", True),
        (["7h", "2c"], "BTN", False),
        (["7h", "2c"], "BB", False),
        (["Ah", "Qh"], "UTG", False),
        (["Ah", "Qh"], "CO", True),
        (["5s", "5d"], "UTG", False),
        (["5s", "5d"], "CO", False),
        (["9h", "8h"], "MP", False),
        (["Ts", "9s"], "UTG", False),
    ]
    for cards, pos, facing in tests:
        r = preflop_advice(cards, pos, facing_raise=facing)
        tag = " (vs raise)" if facing else ""
        print(
            f"{r['hand_notation']:4s} @ {pos:3s}{tag:12s} -> "
            f"{r['action']:12s}  [{r['hand_tier']}]  {r['reason']}"
        )
