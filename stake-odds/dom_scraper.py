"""
Stake.us poker data extractor via Chrome DevTools Protocol (CDP).

Connects to Chrome (launched with --remote-debugging-port=9222), finds the
poker iframe, and extracts game state from React component internals.

Card encoding: num // 4 → rank (0=2..12=A), num % 4 → suit (0=c,1=d,2=h,3=s)
"""

import json
import time
import urllib.request

try:
    import websocket
except ImportError:
    raise ImportError(
        "websocket-client is required.  Install with:  pip install websocket-client"
    )

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def decode_card(num_str):
    """Stake.us numeric card → standard notation (e.g. 44 → 'Kc')."""
    try:
        n = int(num_str)
    except (ValueError, TypeError):
        return None
    if n < 0 or n > 51:
        return None
    return RANKS[n // 4] + SUITS[n % 4]


EXTRACT_JS = """(function(){
if(!window._psc){window._psc={};}
var C=window._psc;
function fs(key){
  // Fast path: check cached element first
  var ce=C[key];
  if(ce){try{
    var fk=C[key+'_fk'];
    var cur=ce[fk];
    for(var d=0;d<50&&cur;d++){
      try{if(cur.stateNode&&cur.stateNode.state&&cur.stateNode.state[key]!==undefined)
        return cur.stateNode.state[key];}catch(e){}
      cur=cur['return'];
    }
  }catch(e){}}
  // Slow path: scan DOM and cache the hit
  var els=document.querySelectorAll('*');
  for(var i=0;i<els.length;i++){
    var el=els[i],ks=Object.keys(el),fk=null;
    for(var j=0;j<ks.length;j++){if(ks[j].indexOf('__reactFiber')===0){fk=ks[j];break;}}
    if(!fk)continue;
    var cur=el[fk];
    for(var d=0;d<50&&cur;d++){
      try{if(cur.stateNode&&cur.stateNode.state&&cur.stateNode.state[key]!==undefined){
        C[key]=el;C[key+'_fk']=fk;
        return cur.stateNode.state[key];
      }}catch(e){}
      cur=cur['return'];
    }
  }
  return null;
}
var r={};
var gm=fs('gameManagerModel');
if(gm&&gm.prevGameState){
  var g=gm.prevGameState;
  r.gameId=g.gameId||0;
  r.tableState=g.tableState;
  r.round=g.moves?g.moves.round:-1;
  r.seats=[];
  if(g.seats)for(var si=0;si<g.seats.length;si++){
    var s=g.seats[si];
    r.seats.push({id:s.id,cards:s.cards||'',bet:s.bet,cash:s.cash,flags:s.flags,name:s.displayName});
  }
  r.boardCards=(g.desk&&g.desk.cards)?g.desk.cards:'';
  r.deskPot=g.desk?(g.desk.pot||0):0;
  r.pots=g.pots||[];
  r.seatState=g.seatState||null;
}
var cm=fs('chipsModel');r.pot=cm?(cm.pot||0):0;
var dsm=fs('deskScreenModel');r.combination=dsm?(dsm.highCombination||''):'';
var clm=fs('clientModel');r.playerId=clm?clm.playerId:0;
return JSON.stringify(r);
})()"""


class StakePokerScraper:
    """Extract poker game state from Stake.us via Chrome DevTools Protocol."""

    def __init__(self, cdp_port=9222):
        self.cdp_port = cdp_port
        self._ws = None
        self._msg_id = 0
        self._session_id = None
        self._context_id = None
        self._player_id = None

    def connect(self):
        """Find the poker target in Chrome and attach via CDP."""
        base = f"http://localhost:{self.cdp_port}"

        try:
            with urllib.request.urlopen(f"{base}/json/version", timeout=3) as r:
                browser_ws = json.loads(r.read())["webSocketDebuggerUrl"]
        except Exception as exc:
            raise ConnectionError(
                f"Chrome DevTools not reachable on port {self.cdp_port}.\n"
                f"Launch Chrome with:  --remote-debugging-port={self.cdp_port}"
            ) from exc

        with urllib.request.urlopen(f"{base}/json", timeout=3) as r:
            targets = json.loads(r.read())

        poker_tid = None
        page_tid = None
        for t in targets:
            url = (t.get("url") or "").lower()
            tid = t.get("id", "")
            if "poker-server" in url or "evenbet" in url:
                poker_tid = tid
                break
            if t.get("type") == "page" and ("stake" in url or "poker" in url):
                page_tid = page_tid or tid

        target_id = poker_tid or page_tid
        if not target_id:
            avail = "\n".join(
                f"  {t.get('type','?')}: {(t.get('url') or '?')[:90]}"
                for t in targets
            )
            raise ConnectionError(
                f"No poker target found in Chrome.  Is Stake.us open?\nTargets:\n{avail}"
            )

        self._ws = websocket.create_connection(browser_ws, timeout=10)
        resp = self._cdp(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        if "error" in resp:
            raise ConnectionError(f"CDP attach failed: {resp['error']}")
        self._session_id = resp.get("result", {}).get("sessionId")

        if not poker_tid and page_tid:
            self._discover_iframe_context()

    def _discover_iframe_context(self):
        """Enable Runtime and locate the poker iframe execution context."""
        self._cdp("Runtime.enable")
        deadline = time.time() + 4
        self._ws.settimeout(0.5)
        try:
            while time.time() < deadline:
                try:
                    msg = json.loads(self._ws.recv())
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    continue
                if msg.get("method") == "Runtime.executionContextCreated":
                    ctx = msg["params"]["context"]
                    origin = (ctx.get("origin") or "").lower()
                    if any(
                        kw in origin
                        for kw in ("poker", "sk-play", "evenbet")
                    ):
                        self._context_id = ctx["id"]
                        return
        finally:
            self._ws.settimeout(10)

    def _cdp(self, method, params=None):
        """Send a CDP command and wait for the matching response."""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        if self._session_id:
            msg["sessionId"] = self._session_id
        self._ws.send(json.dumps(msg))

        deadline = time.time() + 10
        while time.time() < deadline:
            raw = self._ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == self._msg_id:
                return resp
        raise TimeoutError(f"CDP timeout waiting for response to {method}")

    def _evaluate(self, js):
        """Execute JavaScript in the poker context and return the result value."""
        params = {"expression": js, "returnByValue": True}
        if self._context_id:
            params["contextId"] = self._context_id
        resp = self._cdp("Runtime.evaluate", params)
        r = resp.get("result", {}).get("result", {})
        return r.get("value")

    def extract_raw(self):
        """Run the extraction JS and return the parsed dict, or None."""
        raw = self._evaluate(EXTRACT_JS)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def detect(self):
        """
        High-level detection returning a dict compatible with the odds pipeline:

            hole_cards:      ['Kc', '4c']
            community_cards: ['Kh', '9s', '7c', '9d', '8h']
            pot:             float
            combination:     str   ('Two Pair: Ks & 9s')
            num_opponents:   int
            game_id:         int   (changes each hand)
        """
        data = self.extract_raw()
        empty = {
            "hole_cards": [],
            "community_cards": [],
            "pot": 0.0,
            "combination": "",
            "num_opponents": 1,
            "game_id": 0,
        }
        if not data:
            return empty

        if not self._player_id and data.get("playerId"):
            self._player_id = data["playerId"]
        pid = self._player_id

        out = dict(empty)
        out["pot"] = float(data.get("pot", 0))
        out["combination"] = (data.get("combination") or "").strip()
        out["game_id"] = data.get("gameId", 0)

        for seat in data.get("seats", []):
            if seat.get("id") == pid:
                raw_cards = seat.get("cards", "")
                if raw_cards and "-1" not in raw_cards:
                    decoded = [decode_card(p) for p in raw_cards.split(";") if p]
                    out["hole_cards"] = [c for c in decoded if c]
                break

        board_str = data.get("boardCards", "")
        if board_str:
            decoded = [decode_card(p) for p in board_str.split(";") if p]
            out["community_cards"] = [c for c in decoded if c]

        active = sum(
            1
            for s in data.get("seats", [])
            if s.get("id") != pid and s.get("cards") not in ("", None)
        )
        out["num_opponents"] = max(active, 1)

        return out

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
