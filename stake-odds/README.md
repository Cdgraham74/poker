# Stake Poker Live Odds

Real-time poker odds calculator for Stake.us. Extracts game state directly from the poker client via Chrome DevTools Protocol — 100% accurate, no OCR or screen capture.

## Quick Start

```
cd stake-odds
python main.py
```

That's it. The script will:

1. Launch Chrome with a dedicated debug profile (kills existing Chrome if needed)
2. Connect to the Stake.us poker iframe via CDP
3. Extract your hole cards, community cards, pot, and available actions
4. Calculate Monte Carlo equity and display live odds with actionable recommendations

On first run you'll need to log into Stake.us in the Chrome window that opens. Your session persists in `.chrome-profile/` for future runs.

## What You See

```
╔═══════════════════════════════════════════════╗
║  STAKE POKER ODDS  [AUTO-DETECT]  |  Opponents: 3  ║
╚═══════════════════════════════════════════════╝
  YOUR HAND:    [K♣] [4♣]
  COMMUNITY:    [K♥] [9♠] [7♣] [9♦] [8♥]
  STREET:       RIVER
  POT:          $62.00
  EQUITY:       ████████████░░░░░░░░░░░░ 42.1%
  ACTION:       CALL
  CONFIDENCE:   GOOD
```

## How It Works

### Data Extraction (`dom_scraper.py`)

Connects to Chrome via the DevTools Protocol WebSocket. Injects JavaScript into the Stake.us poker iframe that reads React component internal state:

- **Hole cards** — `gameManagerModel.prevGameState.seats[you].cards` (numeric encoding: `card // 4` = rank, `card % 4` = suit)
- **Community cards** — `gameManagerModel.prevGameState.desk.cards`
- **Pot** — `chipsModel.pot`
- **Available actions** — `tableActionsModel.actions` (fold/check/call/raise with amounts)
- **Player ID** — auto-detected from `clientModel.playerId`

DOM element references are cached in `window._psc` after first scan for sub-5ms subsequent polls.

### Odds Engine (`odds_engine.py`)

Monte Carlo simulation: deals random remaining cards thousands of times and counts wins/ties/losses against N opponents.

- **Fast pass**: 3,000 sims displayed instantly (~50ms)
- **Refined pass**: 12,000 more sims merged in for 15,000 total accuracy

### Recommendations

Context-aware advice using your actual available actions from the game state:

- **Never says FOLD when CHECK is available** — reads `tableActionsModel`
- **Pot odds** — when facing a bet, compares equity to `call / (pot + call)` to determine if calling is profitable
- **Sizing** — suggests bet sizes proportional to confidence level

## Files

```
main.py           Entry point — run this
dom_scraper.py    Chrome CDP connection + React state extraction
odds_engine.py    Monte Carlo equity + recommendation engine
terminal_ui.py    Rich terminal display
requirements.txt  Dependencies: rich, websocket-client
```

## Requirements

- Python 3.10+
- Google Chrome
- `pip install -r requirements.txt`

## Commands

| Command | Description |
|---|---|
| `python main.py` | Start live odds (default) |
| `python main.py selftest` | Run odds engine self-test |
