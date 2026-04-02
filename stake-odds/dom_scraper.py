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
if(!window._psc)window._psc={};
var C=window._psc;

var need=['gameManagerModel','gameModel','chipsModel','deskScreenModel','clientModel','tableActionsModel'];
var F={};
var nf=need.length;

var ce=C._el;
if(ce&&document.contains(ce)){
  var fk=C._fk;
  if(fk){try{var cur=ce[fk];
    for(var d=0;d<60&&cur;d++){
      try{if(cur.stateNode&&cur.stateNode.state){
        var st=cur.stateNode.state;
        for(var ni=0;ni<need.length;ni++){
          var k=need[ni];
          if(!F[k]&&st[k]!==undefined){F[k]=st[k];nf--;}
        }
        if(nf<=0)break;
      }}catch(e){}
      cur=cur['return'];
    }
  }catch(e){}}
  if(nf<=0){C._hit=(C._hit||0)+1;}
  else{delete C._el;delete C._fk;}
}

if(nf>0){
  var els=document.querySelectorAll('[class]');
  for(var i=0;i<els.length&&nf>0;i++){
    var el=els[i],ks=Object.keys(el),fk=null;
    for(var j=0;j<ks.length;j++){if(ks[j].indexOf('__reactFiber')===0){fk=ks[j];break;}}
    if(!fk)continue;
    var cur=el[fk];
    for(var d=0;d<60&&cur;d++){
      try{if(cur.stateNode&&cur.stateNode.state){
        var st=cur.stateNode.state;
        for(var ni=0;ni<need.length;ni++){
          var k=need[ni];
          if(!F[k]&&st[k]!==undefined){F[k]=st[k];nf--;
            if(!C._el){C._el=el;C._fk=fk;}
          }
        }
        if(nf<=0)break;
      }}catch(e){}
      cur=cur['return'];
    }
    if(nf<=0)break;
  }
}

var r={};
var gm=F['gameManagerModel'];
if(gm){
  var gs=gm.gameState;var pg=gm.prevGameState;
  var g=gs||pg;
  if(g){
    r.gameId=g.gameId||0;
    r.tableState=g.tableState;
    r.round=g.moves?g.moves.round:-1;
    if(g.moves){r.dealerIdx=g.moves.dealerIndex;r.sbIdx=g.moves.smallBlindIndex;r.bbIdx=g.moves.bigBlindIndex;
      r.activeIdx=g.moves.activeIndex;r.clientIdx=g.moves.clientIndex;r.movesRound=g.moves.round;
    }
    r.secondsFromGameStart=g.secondsFromGameStart||0;
    r.seats=[];
    if(g.seats)for(var si=0;si<g.seats.length;si++){
      var s=g.seats[si];
      r.seats.push({idx:si,id:s.id,cards:s.cards||'',bet:s.bet,cash:s.cash,flags:s.flags,flags2:s.flags2||0,name:s.displayName,wc:s.winChance||0,elapsed:s.elapsedTurnSeconds||0});
    }
    r.boardCards=(g.desk&&g.desk.cards)?g.desk.cards:'';
    r.deskPot=g.desk?(g.desk.pot||0):0;
    r.pots=g.pots||[];
    r.seatState=g.seatState||null;
    if(gs&&pg&&pg.gameId===r.gameId&&pg.seats){
      r._altSeats=[];for(var ai=0;ai<pg.seats.length;ai++){var st=pg.seats[ai];r._altSeats.push({idx:ai,id:st.id,cards:st.cards||''});}
    }
    if(pg&&pg.gameId&&pg.gameId!==r.gameId){
      r.prevGameId=pg.gameId;
      r.prevSeats=[];
      if(pg.seats)for(var pi=0;pi<pg.seats.length;pi++){
        var ps=pg.seats[pi];
        r.prevSeats.push({idx:pi,id:ps.id,bet:ps.bet,cash:ps.cash,flags:ps.flags,name:ps.displayName,cards:ps.cards||''});
      }
      r.prevPot=pg.desk?(pg.desk.pot||0):0;
    }
  }
}
var gmod=F['gameModel'];
if(gmod&&gmod.tableInfo){r.bigBlind=gmod.tableInfo.bigBlind||0;r.smallBlind=gmod.tableInfo.smallBlind||0;}
var cm=F['chipsModel'];r.pot=cm?(cm.pot||0):0;
var dsm=F['deskScreenModel'];r.combination=dsm?(dsm.highCombination||''):'';
var clm=F['clientModel'];r.playerId=clm?clm.playerId:0;
var tam=F['tableActionsModel'];
if(tam&&tam.actions){r.actions=tam.actions;}else{r.actions=[];}
return JSON.stringify(r);
})()"""


DISCOVER_FULL_JS = """(function(){
var r={url:location.href,clickable:[],inputs:[],models:{},canvases:[]};
var cs=document.querySelectorAll('canvas');
for(var c=0;c<cs.length;c++){var cv=cs[c];r.canvases.push({w:cv.width,h:cv.height,cls:(cv.className||'').substring(0,60)});}
var all=document.querySelectorAll('*');
for(var i=0;i<all.length;i++){
  var el=all[i];
  if(el.offsetWidth<8||el.offsetHeight<8)continue;
  var hasClick=false,rProps=null,evts=[];
  var ks=Object.keys(el);
  for(var j=0;j<ks.length;j++){
    if(ks[j].indexOf('__reactProps')===0){
      var p=el[ks[j]];
      if(p){rProps=Object.keys(p).join(',');
        if(p.onClick)evts.push('onClick');
        if(p.onPointerDown)evts.push('onPointerDown');
        if(p.onMouseDown)evts.push('onMouseDown');
        if(p.onTouchStart)evts.push('onTouchStart');
        if(evts.length)hasClick=true;}
    }
  }
  var cst=window.getComputedStyle(el);
  if(cst.cursor==='pointer')hasClick=true;
  if(el.tagName==='BUTTON'||el.getAttribute('role')==='button')hasClick=true;
  if(el.getAttribute('data-action')||el.getAttribute('data-testid'))hasClick=true;
  if(!hasClick)continue;
  var ft=(el.textContent||'').trim();if(ft.length>100)ft=ft.substring(0,100);
  var rect=el.getBoundingClientRect();
  r.clickable.push({tag:el.tagName,id:el.id||'',cls:(el.className||'').toString().substring(0,120),
    text:ft,w:el.offsetWidth,h:el.offsetHeight,x:rect.left|0,y:rect.top|0,
    evts:evts.join(','),rp:rProps?rProps.substring(0,80):null,
    da:el.getAttribute('data-action')||'',dt:el.getAttribute('data-testid')||''});
}
var inps=document.querySelectorAll('input,textarea,[contenteditable]');
for(var i=0;i<inps.length;i++){var inp=inps[i];
  r.inputs.push({tag:inp.tagName,type:inp.type||'',cls:(inp.className||'').substring(0,60),
    vis:inp.offsetWidth>0,w:inp.offsetWidth,h:inp.offsetHeight,val:inp.value||'',ph:inp.placeholder||''});}
if(!window._psc)window._psc={};var C=window._psc;
function fs2(key){
  var ce=C[key];if(ce){try{var fk=C[key+'_fk'];var cur=ce[fk];
    for(var d=0;d<50&&cur;d++){try{if(cur.stateNode&&cur.stateNode.state&&cur.stateNode.state[key]!==undefined)return cur.stateNode;}catch(e){}cur=cur['return'];}}catch(e){}}
  var els2=document.querySelectorAll('*');for(var i2=0;i2<els2.length;i2++){var el2=els2[i2],ks2=Object.keys(el2),fk2=null;
    for(var j2=0;j2<ks2.length;j2++){if(ks2[j2].indexOf('__reactFiber')===0){fk2=ks2[j2];break;}}if(!fk2)continue;
    var cur2=el2[fk2];for(var d2=0;d2<50&&cur2;d2++){try{if(cur2.stateNode&&cur2.stateNode.state&&cur2.stateNode.state[key]!==undefined){
      C[key]=el2;C[key+'_fk']=fk2;return cur2.stateNode;}}catch(e){}cur2=cur2['return'];}}return null;}
var mNames=['tableActionsModel','gameManagerModel','gameModel','connectionModel',
  'socketModel','clientModel','chipsModel','deskScreenModel','tableModel',
  'seatModel','betModel','playerModel','lobbyModel','pokerModel','actionModel'];
for(var m=0;m<mNames.length;m++){
  var mn=mNames[m];var sn=fs2(mn);if(!sn)continue;
  var model=sn.state[mn];var mks=[];try{mks=Object.keys(model).slice(0,30);}catch(e){}
  var methods=[];var proto=Object.getPrototypeOf(model);
  while(proto&&proto!==Object.prototype){
    try{var pn=Object.getOwnPropertyNames(proto);
      for(var p=0;p<pn.length;p++){try{if(typeof model[pn[p]]==='function'&&pn[p]!=='constructor')methods.push(pn[p]);}catch(e){}}}catch(e){}
    proto=Object.getPrototypeOf(proto);}
  var cM=[];var cP=Object.getPrototypeOf(sn);
  if(cP){try{var cpn=Object.getOwnPropertyNames(cP);
    for(var p=0;p<cpn.length;p++){try{if(typeof sn[cpn[p]]==='function'&&cpn[p]!=='constructor'&&cpn[p]!=='render'&&cpn[p]!=='setState'&&cpn[p]!=='forceUpdate')cM.push(cpn[p]);}catch(e){}}}catch(e){}}
  r.models[mn]={keys:mks,methods:methods,compMethods:cM};}
return JSON.stringify(r);
})()"""

# Maps action type int -> action name for model-based dispatch
ACTION_TYPE_MAP = {1: "fold", 2: "check", 3: "call", 9: "raise", 15: "check"}

FIND_BUTTON_JS = """(function(){
var action='__ACTION__';
var pats={'fold':['fold'],'check':['check'],'call':['call'],'raise':['raise','bet'],'allin':['all-in','all in','allin']};
var match=pats[action]||[action];
var found=[];
var all=document.querySelectorAll('*');
for(var i=0;i<all.length;i++){
  var el=all[i];
  if(el.offsetWidth<8||el.offsetHeight<8)continue;
  var hasClick=false;
  var ks=Object.keys(el);
  for(var j=0;j<ks.length;j++){
    if(ks[j].indexOf('__reactProps')===0){var p=el[ks[j]];if(p&&(p.onClick||p.onPointerDown||p.onMouseDown))hasClick=true;}
  }
  var cst=window.getComputedStyle(el);
  if(cst.cursor==='pointer')hasClick=true;
  if(el.tagName==='BUTTON'||el.getAttribute('role')==='button')hasClick=true;
  if(!hasClick)continue;
  var ft=(el.textContent||'').toLowerCase().trim();
  if(ft.length>40)continue;
  var clean=ft.replace(/[\\s$,.\\d]/g,'');
  for(var p=0;p<match.length;p++){
    if(clean.indexOf(match[p])!==-1||clean===match[p]){
      var rect=el.getBoundingClientRect();
      found.push({tag:el.tagName,cls:(el.className||'').toString().substring(0,80),
        text:ft.substring(0,40),x:rect.left,y:rect.top,w:rect.width,h:rect.height,
        cx:rect.left+rect.width/2,cy:rect.top+rect.height/2});
    }
  }
}
return JSON.stringify(found);
})()"""

CLICK_ACTION_JS = """(function(){
var action='__ACTION__';
var amount=__AMOUNT__;
var pats={'fold':['fold'],'check':['check'],'call':['call'],'raise':['raise','bet'],'allin':['all-in','all in','allin']};
var match=pats[action]||[action];

if((action==='raise'||action==='allin')&&amount>0){
  var inps=document.querySelectorAll('input,textarea,[contenteditable]');
  for(var i=0;i<inps.length;i++){
    var inp=inps[i];
    if(inp.offsetWidth>20&&inp.offsetParent!==null){
      try{
        var ns=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
        ns.call(inp,amount.toString());
        inp.dispatchEvent(new Event('input',{bubbles:true}));
        inp.dispatchEvent(new Event('change',{bubbles:true}));
        inp.dispatchEvent(new Event('blur',{bubbles:true}));
      }catch(e){inp.value=amount.toString();}
      break;
    }
  }
}

function clickEl(el,strat){
  try{
    el.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true}));
    el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}));
    el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true}));
    el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
    el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,cancelable:true}));
  }catch(e){try{el.click();}catch(e2){}}
  var rect=el.getBoundingClientRect();
  return JSON.stringify({ok:true,strategy:strat,tag:el.tagName,
    cls:(el.className||'').toString().substring(0,60),
    text:(el.textContent||'').trim().substring(0,40),
    cx:rect.left+rect.width/2,cy:rect.top+rect.height/2});
}

var all=document.querySelectorAll('*');
var candidates=[];
for(var i=0;i<all.length;i++){
  var el=all[i];
  if(el.offsetWidth<8||el.offsetHeight<8)continue;
  var hasClick=false,hasReactClick=false,reactPropsKey=null;
  var ks=Object.keys(el);
  for(var j=0;j<ks.length;j++){
    if(ks[j].indexOf('__reactProps')===0){
      reactPropsKey=ks[j];
      var p=el[ks[j]];
      if(p&&(p.onClick||p.onPointerDown||p.onMouseDown)){hasClick=true;hasReactClick=true;}
    }
  }
  var cst=window.getComputedStyle(el);
  if(cst.cursor==='pointer')hasClick=true;
  if(el.tagName==='BUTTON'||el.getAttribute('role')==='button')hasClick=true;
  if(!hasClick)continue;

  var ft=(el.textContent||'').toLowerCase().trim();
  if(ft.length>40)continue;
  var clean=ft.replace(/[\\s$,.\\d]/g,'');
  var matched=false;
  for(var p=0;p<match.length;p++){
    if(clean.indexOf(match[p])!==-1){matched=true;break;}
  }
  if(matched)candidates.push({el:el,text:ft,clean:clean,hasReact:hasReactClick,rpKey:reactPropsKey});
}

for(var c=0;c<candidates.length;c++){
  var cd=candidates[c];
  if(cd.hasReact&&cd.rpKey){
    try{
      var rp=cd.el[cd.rpKey];
      if(rp.onClick){rp.onClick({preventDefault:function(){},stopPropagation:function(){},nativeEvent:{stopImmediatePropagation:function(){}}});
        return JSON.stringify({ok:true,strategy:'react-onClick',tag:cd.el.tagName,text:cd.text.substring(0,40)});}
    }catch(e){}
  }
}

for(var c=0;c<candidates.length;c++){
  return clickEl(candidates[c].el,'fullClick');
}

return JSON.stringify({ok:false,error:'No button found for: '+action,
  totalClickable:all.length,searched:candidates.length});
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
            try:
                self._cdp("Runtime.disable")
            except Exception:
                pass

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
        if "error" in resp and self._context_id:
            self._context_id = None
            self._discover_iframe_context()
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
        High-level detection returning a dict compatible with the odds pipeline.
        All monetary values (pot, action cash) are scaled to display units (dollars).

            hole_cards:      ['Kc', '4c']
            community_cards: ['Kh', '9s', '7c', '9d', '8h']
            pot:             float  (display dollars)
            combination:     str    ('Two Pair: Ks & 9s')
            num_opponents:   int    (only players still in the hand)
            game_id:         int    (changes each hand)
        """
        data = self.extract_raw()
        empty = {
            "hole_cards": [],
            "community_cards": [],
            "pot": 0.0,
            "combination": "",
            "num_opponents": 1,
            "game_id": 0,
            "actions": [],
            "position": None,
            "stack": 0.0,
            "big_blind": 0.0,
            "opponents": [],
            "num_limpers": 0,
            "is_our_turn": False,
            "active_seat": -1,
            "seat_state": None,
            "hand_time": 0,
        }
        if not data:
            return empty

        if not self._player_id and data.get("playerId"):
            self._player_id = data["playerId"]
        pid = self._player_id

        scale = 100.0

        out = dict(empty)
        out["pot"] = float(data.get("pot", 0)) / scale
        out["combination"] = (data.get("combination") or "").strip()
        out["game_id"] = data.get("gameId", 0)

        our_seat_idx = None
        occupied_seats = []
        for seat in data.get("seats", []):
            sid = seat.get("id")
            seat_idx = seat.get("idx", 0)
            if sid and sid != 0:
                occupied_seats.append(seat_idx)
            if sid == pid:
                our_seat_idx = seat_idx
                out["stack"] = float(seat.get("cash", 0)) / scale
                raw_cards = seat.get("cards", "")
                if raw_cards and "-1" not in raw_cards:
                    decoded = [decode_card(p) for p in raw_cards.split(";") if p]
                    out["hole_cards"] = [c for c in decoded if c]

        if not out["hole_cards"] and data.get("_altSeats") and pid:
            for alt_seat in data["_altSeats"]:
                if alt_seat.get("id") == pid:
                    raw_cards = alt_seat.get("cards", "")
                    if raw_cards and "-1" not in raw_cards:
                        decoded = [decode_card(p) for p in raw_cards.split(";") if p]
                        out["hole_cards"] = [c for c in decoded if c]
                    break

        bb_raw = data.get("bigBlind", 0) or 0
        sb_idx = data.get("sbIdx")
        bb_idx = data.get("bbIdx")

        FLAG_IN_HAND = 4
        opponents = []
        num_limpers = 0
        for seat in data.get("seats", []):
            sid = seat.get("id")
            if not sid or sid == 0 or sid == pid:
                continue
            seat_idx = seat.get("idx", 0)
            flags = seat.get("flags", 0)
            raw_opp_cards = seat.get("cards") or ""
            has_cards = raw_opp_cards != "" and raw_opp_cards != "0"
            active = bool(flags & FLAG_IN_HAND) or has_cards
            seat_bet = float(seat.get("bet", 0) or 0) / scale
            opponents.append({
                "name": seat.get("name", "") or "",
                "stack": float(seat.get("cash", 0) or 0) / scale,
                "bet": seat_bet,
                "active": active,
                "has_cards": has_cards,
                "seat_idx": seat_idx,
                "win_chance": seat.get("wc", 0) or 0,
                "think_time": seat.get("elapsed", 0) or 0,
            })
            if bb_raw > 0 and seat_idx != bb_idx and seat_idx != sb_idx:
                if seat.get("bet", 0) == bb_raw and has_cards:
                    num_limpers += 1

        out["opponents"] = opponents
        out["num_limpers"] = num_limpers
        out["big_blind"] = float(bb_raw) / scale

        client_idx = data.get("clientIdx")
        active_idx = data.get("activeIdx")
        out["is_our_turn"] = (client_idx is not None and active_idx is not None
                              and client_idx == active_idx)
        out["active_seat"] = active_idx if active_idx is not None else -1

        seat_state = data.get("seatState")
        if seat_state and isinstance(seat_state, dict):
            out["seat_state"] = {
                "is_losing": seat_state.get("isLosing", False),
                "combination": seat_state.get("highCombination", ""),
            }

        out["hand_time"] = data.get("secondsFromGameStart", 0) or 0

        prev_gid = data.get("prevGameId")
        if prev_gid and data.get("prevSeats"):
            prev_seats = []
            for ps in data["prevSeats"]:
                psid = ps.get("id")
                if psid and psid != 0:
                    prev_seats.append({
                        "id": psid,
                        "name": ps.get("name", ""),
                        "bet": float(ps.get("bet", 0) or 0) / scale,
                        "stack": float(ps.get("cash", 0) or 0) / scale,
                        "flags": ps.get("flags", 0),
                        "had_cards": ps.get("cards") not in ("", None),
                    })
            out["prev_hand"] = {
                "game_id": prev_gid,
                "seats": prev_seats,
                "pot": float(data.get("prevPot", 0) or 0) / scale,
            }

        dealer_idx = data.get("dealerIdx")
        if dealer_idx is not None and our_seat_idx is not None and occupied_seats:
            out["position"] = {
                "dealer_idx": dealer_idx,
                "our_seat_idx": our_seat_idx,
                "occupied_seats": occupied_seats,
            }
        else:
            out["position"] = None

        board_str = data.get("boardCards", "")
        if board_str:
            decoded = [decode_card(p) for p in board_str.split(";") if p]
            out["community_cards"] = [c for c in decoded if c]

        active_opp = sum(1 for o in opponents if o["active"])
        opp_with_cards = sum(1 for o in opponents if o["has_cards"])
        out["num_opponents"] = active_opp if active_opp > 0 else max(opp_with_cards, 1)

        raw_actions = data.get("actions", [])
        scaled_actions = []
        for a in raw_actions:
            sa = dict(a)
            if "cash" in sa and sa["cash"]:
                sa["cash"] = sa["cash"] / scale
            scaled_actions.append(sa)
        out["actions"] = scaled_actions

        return out

    def execute_action(self, action, amount=None):
        """
        Execute a poker action via multiple strategies:
          1. JS-level React onClick / full mouse event dispatch
          2. CDP Input.dispatchMouseEvent at button coordinates (most realistic)

        Args:
            action: 'fold', 'check', 'call', 'raise', 'allin'
            amount: bet amount in display dollars (will be scaled to cents)

        Returns:
            dict with 'ok' bool and details.
        """
        internal_amount = round(amount * 100, 0) if amount and amount > 0 else 0

        js = CLICK_ACTION_JS.replace("__ACTION__", action)
        js = js.replace("__AMOUNT__", str(int(internal_amount)))
        raw = self._evaluate(js)
        result = None
        if raw:
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                result = None

        if result and result.get("ok"):
            return result

        return self._click_via_cdp_mouse(action, internal_amount)

    def _click_via_cdp_mouse(self, action, internal_amount):
        """
        Fallback: find the button via JS, then click at its center coords
        using CDP Input.dispatchMouseEvent (simulates a real mouse click).
        """
        if (action in ("raise", "allin")) and internal_amount > 0:
            set_js = (
                "(function(){"
                "var inps=document.querySelectorAll('input,textarea,[contenteditable]');"
                "for(var i=0;i<inps.length;i++){"
                "var inp=inps[i];if(inp.offsetWidth>20&&inp.offsetParent!==null){"
                "try{var ns=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                f"ns.call(inp,'{int(internal_amount)}');"
                "inp.dispatchEvent(new Event('input',{bubbles:true}));"
                "inp.dispatchEvent(new Event('change',{bubbles:true}));"
                "}catch(e){}"
                "return JSON.stringify({ok:true});}}return JSON.stringify({ok:false});})()"
            )
            self._evaluate(set_js)

        js = FIND_BUTTON_JS.replace("__ACTION__", action)
        raw = self._evaluate(js)
        if not raw:
            return {"ok": False, "error": "FIND_BUTTON_JS returned nothing"}
        try:
            buttons = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"ok": False, "error": f"Bad FIND response: {raw}"}

        if not buttons:
            return {"ok": False, "error": f"No button found for '{action}' (CDP mouse)"}

        btn = buttons[0]
        cx, cy = btn["cx"], btn["cy"]

        try:
            self._cdp("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": cx, "y": cy,
                "button": "left", "clickCount": 1,
            })
            time.sleep(0.05)
            self._cdp("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": cx, "y": cy,
                "button": "left", "clickCount": 1,
            })
        except Exception as exc:
            return {"ok": False, "error": f"CDP mouse failed: {exc}"}

        return {"ok": True, "strategy": "cdp-mouse", "x": cx, "y": cy,
                "text": btn.get("text", "")}

    def discover_full(self):
        """
        Comprehensive diagnostic: dump all clickable elements, inputs,
        canvases, and React model methods.

        Returns parsed dict or empty dict.
        """
        raw = self._evaluate(DISCOVER_FULL_JS)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
