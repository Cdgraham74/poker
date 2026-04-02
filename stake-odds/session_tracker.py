"""
Session tracking for live poker sessions.
Tracks stack changes, hands played, win/loss per hand, and running P&L.
Saves session history to JSON for later review.
"""

import json
import os
import time
from datetime import datetime

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")


class SessionTracker:
    def __init__(self):
        self.start_time = time.time()
        self.start_stack = None
        self.hands = []
        self._prev_game_id = 0
        self._hand_start_stack = None

    def update(self, game_id, stack):
        """Call every poll with current game_id and stack."""
        if self.start_stack is None and stack > 0:
            self.start_stack = stack
            self._hand_start_stack = stack

        if game_id and game_id != self._prev_game_id and self._prev_game_id != 0:
            if self._hand_start_stack is not None and stack > 0:
                delta = stack - self._hand_start_stack
                self.hands.append({
                    "game_id": self._prev_game_id,
                    "start_stack": round(self._hand_start_stack, 2),
                    "end_stack": round(stack, 2),
                    "delta": round(delta, 2),
                    "time": time.time(),
                })
            self._hand_start_stack = stack

        self._prev_game_id = game_id

    @property
    def hands_played(self):
        return len(self.hands)

    @property
    def session_pnl(self):
        return sum(h["delta"] for h in self.hands)

    @property
    def wins(self):
        return sum(1 for h in self.hands if h["delta"] > 0)

    @property
    def losses(self):
        return sum(1 for h in self.hands if h["delta"] < 0)

    @property
    def breakeven(self):
        return sum(1 for h in self.hands if h["delta"] == 0)

    @property
    def win_rate(self):
        if not self.hands:
            return 0.0
        return self.wins / len(self.hands) * 100

    @property
    def biggest_win(self):
        if not self.hands:
            return 0.0
        return max(h["delta"] for h in self.hands)

    @property
    def biggest_loss(self):
        if not self.hands:
            return 0.0
        return min(h["delta"] for h in self.hands)

    @property
    def elapsed_minutes(self):
        return (time.time() - self.start_time) / 60

    @property
    def bb_per_hour(self):
        """Win rate in BB/hour (requires big_blind to be set externally)."""
        if self.elapsed_minutes < 1:
            return 0.0
        return self.session_pnl / (self.elapsed_minutes / 60)

    def summary(self, big_blind=0.0):
        """Return a dict with all session stats."""
        elapsed = self.elapsed_minutes
        pnl = self.session_pnl
        bb_won = pnl / big_blind if big_blind > 0 else 0
        bb_hr = bb_won / (elapsed / 60) if elapsed > 1 else 0

        return {
            "hands_played": self.hands_played,
            "pnl": round(pnl, 2),
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": round(self.win_rate, 1),
            "biggest_win": round(self.biggest_win, 2),
            "biggest_loss": round(self.biggest_loss, 2),
            "elapsed_min": round(elapsed, 1),
            "bb_won": round(bb_won, 1),
            "bb_per_hour": round(bb_hr, 1),
            "current_stack": round(self.hands[-1]["end_stack"], 2) if self.hands else 0,
            "start_stack": round(self.start_stack, 2) if self.start_stack else 0,
        }

    def save(self):
        """Save session to a JSON file in the sessions/ directory."""
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = os.path.join(SESSIONS_DIR, f"session_{ts}.json")

        data = {
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.now().isoformat(),
            "start_stack": self.start_stack,
            "summary": self.summary(),
            "hands": self.hands,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return path
