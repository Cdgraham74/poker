"""
Persistent opponent profiler backed by SQLite.

Tracks per-player stats across ALL sessions forever, indexed by name
for instant lookups even with thousands of players. Hot cache in memory
for zero-overhead polling; writes batched to DB every few seconds.
"""

import os
import sqlite3
import time

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_data")
DB_PATH = os.path.join(DB_DIR, "players.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    name            TEXT PRIMARY KEY,
    hands           INTEGER DEFAULT 0,
    vpip            INTEGER DEFAULT 0,
    pfr             INTEGER DEFAULT 0,
    bets_raises     INTEGER DEFAULT 0,
    calls           INTEGER DEFAULT 0,
    folds           INTEGER DEFAULT 0,
    went_to_sd      INTEGER DEFAULT 0,
    won_at_sd       INTEGER DEFAULT 0,
    total_won       REAL    DEFAULT 0,
    total_lost      REAL    DEFAULT 0,
    vs_us_won       REAL    DEFAULT 0,
    vs_us_lost      REAL    DEFAULT 0,
    big_bets_won    INTEGER DEFAULT 0,
    big_bets_lost   INTEGER DEFAULT 0,
    first_seen      REAL    DEFAULT 0,
    last_seen       REAL    DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_players_last_seen ON players(last_seen);
CREATE INDEX IF NOT EXISTS idx_players_hands ON players(hands);
"""


class OpponentTracker:
    """Track per-opponent stats across sessions with SQLite persistence."""

    def __init__(self):
        self._cache = {}
        self._dirty = set()
        self._prev_bets = {}
        self._prev_game_id = 0
        self._prev_stacks = {}
        self._hand_start_stacks = {}
        self._hand_participants = set()
        self._hands_counted = set()
        self._vpip_counted = set()
        self._pfr_counted = set()
        self._last_flush = time.time()
        self._our_hand_start_stack = 0.0
        self._db = self._open_db()
        self._migrate_json()
        self._load_recent()

    def _migrate_json(self):
        """One-time migration from old profiles.json into SQLite."""
        import json
        old = os.path.join(DB_DIR, "profiles.json")
        if not os.path.isfile(old):
            return
        try:
            with open(old, "r") as f:
                data = json.load(f)
            if not data:
                return
            with self._db:
                for name, d in data.items():
                    self._db.execute("""
                        INSERT OR IGNORE INTO players (
                            name, hands, vpip, pfr, bets_raises, calls, folds,
                            went_to_sd, won_at_sd, total_won, total_lost,
                            vs_us_won, vs_us_lost, big_bets_won, big_bets_lost,
                            first_seen, last_seen
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        name,
                        d.get("hands", 0), d.get("vpip", 0), d.get("pfr", 0),
                        d.get("bets_raises", 0), d.get("calls", 0), d.get("folds", 0),
                        d.get("went_to_sd", 0), d.get("won_at_sd", 0),
                        d.get("total_won", 0), d.get("total_lost", 0),
                        d.get("vs_us_won", 0), d.get("vs_us_lost", 0),
                        d.get("big_bets_won", 0), d.get("big_bets_lost", 0),
                        d.get("first_seen", 0), d.get("last_seen", 0),
                    ))
            os.rename(old, old + ".migrated")
        except Exception:
            pass

    def _open_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        return conn

    def _load_recent(self):
        """Pre-warm cache with players seen in the last 7 days."""
        cutoff = time.time() - 7 * 86400
        try:
            rows = self._db.execute(
                "SELECT * FROM players WHERE last_seen > ? ORDER BY last_seen DESC",
                (cutoff,),
            ).fetchall()
            cols = [d[0] for d in self._db.execute("SELECT * FROM players LIMIT 0").description]
            for row in rows:
                d = dict(zip(cols, row))
                name = d.pop("name")
                self._cache[name] = d
        except sqlite3.Error:
            pass

    def _ensure(self, name):
        if name in self._cache:
            self._cache[name]["last_seen"] = time.time()
            return self._cache[name]

        row = None
        try:
            row = self._db.execute(
                "SELECT * FROM players WHERE name = ?", (name,)
            ).fetchone()
        except sqlite3.Error:
            pass

        if row:
            cols = [d[0] for d in self._db.execute("SELECT * FROM players LIMIT 0").description]
            d = dict(zip(cols, row))
            d.pop("name", None)
            d["last_seen"] = time.time()
            self._cache[name] = d
        else:
            self._cache[name] = {
                "hands": 0, "vpip": 0, "pfr": 0,
                "bets_raises": 0, "calls": 0, "folds": 0,
                "went_to_sd": 0, "won_at_sd": 0,
                "total_won": 0.0, "total_lost": 0.0,
                "vs_us_won": 0.0, "vs_us_lost": 0.0,
                "big_bets_won": 0, "big_bets_lost": 0,
                "first_seen": time.time(), "last_seen": time.time(),
            }
        self._dirty.add(name)
        return self._cache[name]

    def _flush(self):
        if not self._dirty:
            return
        try:
            with self._db:
                for name in self._dirty:
                    d = self._cache.get(name)
                    if not d:
                        continue
                    self._db.execute("""
                        INSERT INTO players (
                            name, hands, vpip, pfr, bets_raises, calls, folds,
                            went_to_sd, won_at_sd, total_won, total_lost,
                            vs_us_won, vs_us_lost, big_bets_won, big_bets_lost,
                            first_seen, last_seen
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET
                            hands=excluded.hands, vpip=excluded.vpip, pfr=excluded.pfr,
                            bets_raises=excluded.bets_raises, calls=excluded.calls,
                            folds=excluded.folds, went_to_sd=excluded.went_to_sd,
                            won_at_sd=excluded.won_at_sd, total_won=excluded.total_won,
                            total_lost=excluded.total_lost, vs_us_won=excluded.vs_us_won,
                            vs_us_lost=excluded.vs_us_lost, big_bets_won=excluded.big_bets_won,
                            big_bets_lost=excluded.big_bets_lost,
                            first_seen=MIN(players.first_seen, excluded.first_seen),
                            last_seen=excluded.last_seen
                    """, (
                        name,
                        d["hands"], d["vpip"], d["pfr"],
                        d["bets_raises"], d["calls"], d["folds"],
                        d["went_to_sd"], d["won_at_sd"],
                        round(d["total_won"], 2), round(d["total_lost"], 2),
                        round(d["vs_us_won"], 2), round(d["vs_us_lost"], 2),
                        d["big_bets_won"], d["big_bets_lost"],
                        d["first_seen"], d["last_seen"],
                    ))
            self._dirty.clear()
        except sqlite3.Error:
            pass
        self._last_flush = time.time()

    def _flush_if_needed(self):
        if time.time() - self._last_flush > 5:
            self._flush()

    # ── recording ─────────────────────────────────────────────────────

    def record_hand(self, game_id, opponents, big_blind=0.0, our_stack=0.0):
        """Called every poll. Detects new hands, bet changes, and folds."""
        if not game_id or not opponents:
            return

        new_hand = game_id != self._prev_game_id

        if new_hand:
            self._process_hand_end(opponents, big_blind, our_stack)
            self._prev_bets.clear()
            self._hand_start_stacks.clear()
            self._hand_participants.clear()
            self._hands_counted.clear()
            self._vpip_counted.clear()
            self._pfr_counted.clear()
            self._our_hand_start_stack = our_stack
            self._prev_game_id = game_id

        for opp in opponents:
            name = opp.get("name")
            if not name:
                continue

            in_hand = opp.get("has_cards") or opp.get("active")
            if in_hand and name not in self._hands_counted:
                entry = self._ensure(name)
                entry["hands"] += 1
                self._hands_counted.add(name)
                self._hand_participants.add(name)
                self._hand_start_stacks.setdefault(name, opp.get("stack", 0))
                self._dirty.add(name)

            cur_bet = opp.get("bet", 0)
            prev_bet = self._prev_bets.get(name, 0)

            if big_blind > 0 and name in self._hand_participants:
                if name not in self._vpip_counted and cur_bet > big_blind * 1.0:
                    entry = self._ensure(name)
                    entry["vpip"] += 1
                    self._vpip_counted.add(name)
                    self._dirty.add(name)
                if name not in self._pfr_counted and cur_bet > big_blind * 2.2:
                    entry = self._ensure(name)
                    entry["pfr"] += 1
                    self._pfr_counted.add(name)
                    self._dirty.add(name)

            if cur_bet > prev_bet and prev_bet >= 0:
                delta = cur_bet - prev_bet
                entry = self._ensure(name)
                if big_blind > 0 and delta > big_blind * 1.5:
                    entry["bets_raises"] += 1
                    self._dirty.add(name)
                elif delta > 0:
                    entry["calls"] += 1
                    self._dirty.add(name)

            if prev_bet > 0 and not opp.get("has_cards") and not opp.get("active"):
                entry = self._ensure(name)
                entry["folds"] += 1
                self._dirty.add(name)
                self._prev_bets[name] = -1
            else:
                self._prev_bets[name] = cur_bet

            self._prev_stacks[name] = opp.get("stack", 0)

        self._flush_if_needed()

    def _process_hand_end(self, current_opponents, big_blind, our_current_stack):
        """When a new hand starts, compute who won/lost in the previous hand."""
        if not self._hand_start_stacks:
            return

        for opp in current_opponents:
            name = opp.get("name")
            if not name or name not in self._hand_start_stacks:
                continue

            start = self._hand_start_stacks[name]
            end = opp.get("stack", 0)
            delta = end - start
            entry = self._ensure(name)

            if delta > 0:
                entry["total_won"] = round(entry["total_won"] + delta, 2)
                if big_blind > 0 and delta > big_blind * 5:
                    entry["big_bets_won"] += 1
            elif delta < 0:
                entry["total_lost"] = round(entry["total_lost"] + abs(delta), 2)
                if big_blind > 0 and abs(delta) > big_blind * 5:
                    entry["big_bets_lost"] += 1

            if name in self._hand_participants and abs(delta) > 0:
                entry["went_to_sd"] += 1
                if delta > 0:
                    entry["won_at_sd"] += 1

            self._dirty.add(name)

        our_delta = our_current_stack - self._our_hand_start_stack if self._our_hand_start_stack > 0 else 0
        if our_delta < 0:
            our_loss = abs(our_delta)
            gainers = []
            total_gain = 0.0
            for opp in current_opponents:
                name = opp.get("name")
                if not name or name not in self._hand_start_stacks:
                    continue
                gain = opp.get("stack", 0) - self._hand_start_stacks[name]
                if gain > 0:
                    gainers.append((name, gain))
                    total_gain += gain
            if total_gain > 0:
                for name, gain in gainers:
                    share = round(our_loss * (gain / total_gain), 2)
                    entry = self._ensure(name)
                    entry["vs_us_won"] = round(entry["vs_us_won"] + share, 2)
                    self._dirty.add(name)
        elif our_delta > 0:
            our_gain = our_delta
            losers = []
            total_loss = 0.0
            for opp in current_opponents:
                name = opp.get("name")
                if not name or name not in self._hand_start_stacks:
                    continue
                loss = self._hand_start_stacks[name] - opp.get("stack", 0)
                if loss > 0:
                    losers.append((name, loss))
                    total_loss += loss
            if total_loss > 0:
                for name, loss in losers:
                    share = round(our_gain * (loss / total_loss), 2)
                    entry = self._ensure(name)
                    entry["vs_us_lost"] = round(entry["vs_us_lost"] + share, 2)
                    self._dirty.add(name)

    # ── stats ─────────────────────────────────────────────────────────

    def get_stats(self, name):
        """Computed HUD stats with play-style profile."""
        entry = self._cache.get(name)
        if not entry:
            row = None
            try:
                row = self._db.execute(
                    "SELECT * FROM players WHERE name = ?", (name,)
                ).fetchone()
            except sqlite3.Error:
                pass
            if not row:
                return None
            cols = [d[0] for d in self._db.execute("SELECT * FROM players LIMIT 0").description]
            entry = dict(zip(cols, row))
            entry.pop("name", None)

        if entry["hands"] < 1:
            return None

        h = entry["hands"]
        vpip = (entry["vpip"] / h * 100) if h > 0 else 0
        pfr = (entry["pfr"] / h * 100) if h > 0 else 0
        af = (entry["bets_raises"] / entry["calls"]) if entry["calls"] > 0 else float(entry["bets_raises"])

        wtsd = (entry["went_to_sd"] / h * 100) if h > 0 else 0
        wsd = (entry["won_at_sd"] / entry["went_to_sd"] * 100) if entry["went_to_sd"] > 0 else 0

        net = round(entry["total_won"] - entry["total_lost"], 2)
        vs_us_net = round(entry["vs_us_won"] - entry["vs_us_lost"], 2)

        label = _classify_player(vpip, pfr, af, wtsd, wsd, h)
        bluff_score = _estimate_bluff_freq(vpip, pfr, af, wtsd, wsd)

        return {
            "vpip": round(vpip, 1),
            "pfr": round(pfr, 1),
            "af": round(af, 1),
            "hands": h,
            "label": label,
            "wtsd": round(wtsd, 1),
            "wsd": round(wsd, 1),
            "net": net,
            "vs_us": vs_us_net,
            "bluff_score": bluff_score,
            "total_won": entry["total_won"],
            "total_lost": entry["total_lost"],
        }

    def all_stats(self):
        out = {}
        for name in self._cache:
            s = self.get_stats(name)
            if s:
                out[name] = s
        return out

    def lookup(self, name):
        """Instant lookup for any player ever seen, even from past sessions."""
        return self.get_stats(name)

    def top_players(self, order_by="hands", limit=50):
        """Query the all-time leaderboard. Good for reviewing history."""
        valid = {"hands", "total_won", "total_lost", "last_seen", "vs_us_won"}
        col = order_by if order_by in valid else "hands"
        try:
            rows = self._db.execute(
                f"SELECT name FROM players ORDER BY {col} DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self.get_stats(r[0]) | {"name": r[0]} for r in rows if r[0]]
        except sqlite3.Error:
            return []

    def player_count(self):
        try:
            return self._db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        except sqlite3.Error:
            return len(self._cache)

    def save_now(self):
        self._flush()

    def close(self):
        self._flush()
        try:
            self._db.close()
        except Exception:
            pass


def _classify_player(vpip, pfr, af, wtsd, wsd, hands):
    """Assign a play-style label based on observed stats."""
    if hands < 2:
        return "NEW"

    if vpip > 60:
        if af < 1.5:
            return "WHALE"
        return "MANIAC"
    if vpip > 45:
        if pfr < 12:
            return "CALLING STATION"
        if af > 3:
            return "LAG MANIAC"
        return "FISH"
    if vpip > 30:
        if pfr > 20 and af > 2.5:
            return "LAG"
        if pfr < 10:
            return "PASSIVE FISH"
        return "LOOSE"
    if vpip > 20:
        if pfr > 16 and af > 2:
            return "TAG"
        if pfr > 16:
            return "REG"
        return "TIGHT PASSIVE"
    if vpip <= 20:
        if pfr > 15:
            return "NIT-AG"
        return "NIT"

    return ""


def _estimate_bluff_freq(vpip, pfr, af, wtsd, wsd):
    """
    Estimate bluff frequency 0-100.
    High AF + low WTSD + high VPIP = likely bluffs a lot.
    """
    score = 0.0

    if af > 4:
        score += 30
    elif af > 3:
        score += 20
    elif af > 2:
        score += 10

    if vpip > 40 and pfr > 20:
        score += 20
    elif vpip > 30 and pfr > 15:
        score += 10

    if wtsd > 0 and wtsd < 25:
        score += 15
    elif wtsd > 40:
        score -= 10

    if wsd > 0 and wsd < 40:
        score += 10
    elif wsd > 60:
        score -= 10

    gap = vpip - pfr
    if gap > 20:
        score -= 10
    elif gap < 5 and pfr > 15:
        score += 10

    return max(0, min(100, round(score)))
