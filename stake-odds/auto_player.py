"""
Autonomous poker player -- translates GTO decisions into browser clicks.

Maps preflop/postflop recommendations to action types and executes them
through the DOM scraper's CDP connection with human-like timing.
"""

import random
import time


ACTION_MAP = {
    "FOLD": "fold",
    "CHECK": "check",
    "CALL": "call",
    "CALL (drawing)": "call",
    "CALL (borderline)": "call",
    "CALL (low SPR - consider jam)": "call",
    "RAISE": "raise",
    "BET": "raise",
    "BET (semi-bluff)": "raise",
    "BET / JAM": "allin",
    "RAISE / ALL-IN": "allin",
    "3-BET": "raise",
    "3-BET / CALL": "raise",
}


def human_delay(action, confidence=None):
    """
    Sleep a random duration to mimic human decision-making.
    Bigger decisions get longer pauses.
    """
    base_min, base_max = 1.0, 3.0

    if action in ("allin", "raise"):
        base_min, base_max = 2.0, 5.0
    elif action == "fold":
        base_min, base_max = 0.8, 2.5

    if confidence in ("monster", "very strong"):
        base_min += 0.5
        base_max += 1.0

    if random.random() < 0.08:
        base_max += random.uniform(2, 6)

    delay = random.uniform(base_min, base_max)
    time.sleep(delay)
    return delay


def resolve_action(recommendation, available_actions=None):
    """
    Convert a recommendation dict (from preflop_advice or get_bet_recommendation)
    into a (action_name, amount) tuple suitable for execute_action().

    Returns:
        (action_str, amount_float) -- e.g. ('raise', 0.06) or ('fold', 0)
    """
    raw = recommendation.get("action", "FOLD")
    amount = recommendation.get("bet_amount", 0.0) or 0.0

    mapped = ACTION_MAP.get(raw)
    if not mapped:
        upper = raw.upper().strip()
        for key, val in ACTION_MAP.items():
            if key in upper:
                mapped = val
                break
    if not mapped:
        mapped = "fold"

    if available_actions:
        has = set()
        for a in available_actions:
            t = a.get("type", 0)
            if t == 1:
                has.add("fold")
            elif t in (2, 15):
                has.add("check")
            elif t == 3:
                has.add("call")
            elif t == 9:
                has.add("raise")

        if mapped not in has:
            if mapped == "raise" and "call" in has:
                mapped = "call"
            elif mapped == "raise" and "check" in has:
                mapped = "check"
            elif mapped == "call" and "check" in has:
                mapped = "check"
            elif mapped == "allin" and "raise" in has:
                mapped = "raise"
            elif mapped == "allin" and "call" in has:
                mapped = "call"
            elif "check" in has:
                mapped = "check"
            elif "fold" in has:
                mapped = "fold"

    if mapped in ("fold", "check"):
        amount = 0.0

    return mapped, round(amount, 2)


def execute_auto_action(scraper, recommendation, available_actions=None,
                        console=None):
    """
    Full auto-play pipeline: resolve action, wait, click.

    Args:
        scraper: StakePokerScraper instance
        recommendation: dict from preflop_advice() or get_bet_recommendation()
        available_actions: raw actions list from detected['actions']
        console: Rich Console for logging (optional)

    Returns:
        dict with execution result
    """
    action, amount = resolve_action(recommendation, available_actions)
    confidence = recommendation.get("confidence")

    delay = human_delay(action, confidence)

    if console:
        amt_str = f" ${amount:.2f}" if amount > 0 else ""
        console.print(
            f"  [bold cyan]AUTO:[/] {action.upper()}{amt_str}  "
            f"[dim](waited {delay:.1f}s)[/]"
        )

    result = scraper.execute_action(action, amount if amount > 0 else None)

    if result and not result.get("ok"):
        if console:
            console.print(
                f"  [red]Click failed: {result.get('error', 'unknown')}[/]"
            )

    return result or {"ok": False, "error": "No result"}
