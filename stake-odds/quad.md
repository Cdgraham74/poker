# Stake Poker Live Odds Calculator (QUAD)

## Overview
Real-time poker odds calculator for Stake.us poker tables. Captures your screen, detects your hole cards and community cards via OCR, runs Monte Carlo equity simulations, and displays win percentages + bet recommendations in a live terminal dashboard.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Screen Capture  │────>│ Card Detector │────>│  Odds Engine  │────>│  Terminal UI  │
│  (mss)          │     │ (OCR/color)  │     │ (Monte Carlo) │     │  (rich)      │
└─────────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
        ^                                                                  │
        │                    main.py (event loop)                         │
        └─────────────────────────────────────────────────────────────────┘
```

### Components

| File               | Purpose                                                    |
|--------------------|------------------------------------------------------------|
| `main.py`          | Entry point. Ties everything together. Manual + auto modes |
| `card_detector.py` | Screen capture, OCR, color-based suit detection            |
| `odds_engine.py`   | Monte Carlo equity simulation, hand evaluation, bet recs   |
| `terminal_ui.py`   | Rich-based terminal dashboard with live odds display       |
| `regions.json`     | Calibrated screen coordinates for card positions           |
| `requirements.txt` | Python dependencies                                       |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Tesseract OCR (for auto-detect mode)
sudo apt install tesseract-ocr    # Ubuntu/Debian
# brew install tesseract           # macOS

# 3. Run in manual mode (type cards yourself)
python main.py manual

# 4. Or run in auto-detect mode (screen capture)
python main.py auto

# 5. Calibrate screen regions first if using auto mode
python main.py calibrate
```

## Modes

### Manual Mode (`python main.py manual`)
Type your cards directly. Best for getting started and testing.

**Commands:**
- `Ah Kd` — Set your hole cards
- `board Qh Jh 2c` — Set community cards
- `flop Qh Jh 2c` — Set the flop
- `turn 9s` — Add the turn card
- `river 3d` — Add the river card
- `opp 3` — Set number of opponents (1-9)
- `pot 500` — Set pot size
- `reset` — Clear all cards for new hand
- `q` — Quit

**Card format:** Rank + Suit
- Ranks: `2 3 4 5 6 7 8 9 T J Q K A`
- Suits: `s` (spades), `h` (hearts), `d` (diamonds), `c` (clubs)

### Auto-Detect Mode (`python main.py auto`)
Captures your screen and reads cards via OCR. Requires calibration first.

### Calibrate Mode (`python main.py calibrate`)
Takes a screenshot and lets you define pixel coordinates for each card region.

## Odds Engine

- **Method:** Monte Carlo simulation (15,000-20,000 iterations)
- **Accuracy:** ~0.5% margin at 15K sims, ~0.3% at 20K
- **Speed:** <0.5 seconds per calculation
- **Supports:** 1-9 opponents, all streets (preflop through river)
- **Hand evaluator:** Full 5-card poker hand ranking (Royal Flush down to High Card)

### Bet Recommendations

Based on equity thresholds:

| Equity   | Preflop        | Post-Flop      |
|----------|----------------|----------------|
| 80%+     | RAISE/ALL-IN   | ALL-IN         |
| 70-80%   | RAISE/ALL-IN   | BET 75% POT   |
| 60-70%   | RAISE 75% POT  | BET 50% POT   |
| 50-60%   | RAISE 50% POT  | BET 25% POT   |
| 40-50%   | CALL/CHECK     | CHECK/CALL     |
| 25-40%   | FOLD           | CHECK/FOLD     |
| <25%     | FOLD           | FOLD           |

## Reference: odds-calculator (b-inary)

The original `odds-calculator` repo (Rust/WASM + Vue.js) was studied for its approach. We use a pure Python Monte Carlo implementation instead for:
- Simpler integration with screen capture
- No WASM/Rust build toolchain needed
- Native Python threading for background calculations
- Easy to extend for multi-opponent scenarios

## TODO / Future Enhancements

- [ ] Improve OCR accuracy with template matching for Stake.us card designs
- [ ] Add hand history tracking across sessions
- [ ] Outs calculator (show draw probabilities)
- [ ] Position-aware recommendations (UTG vs BTN adjustments)
- [ ] Opponent modeling based on observed betting patterns
