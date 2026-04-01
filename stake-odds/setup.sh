#!/bin/bash
# One-command setup for stake-odds on your laptop
set -e

echo "=== Stake Poker Odds Calculator Setup ==="

# Check OS and install tesseract
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Installing tesseract-ocr..."
    sudo apt-get update -qq && sudo apt-get install -y tesseract-ocr
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Installing tesseract via Homebrew..."
    brew install tesseract
else
    echo "Please install tesseract-ocr manually for your OS"
fi

# Create venv and install deps
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run:"
echo "  source venv/bin/activate"
echo "  python main.py manual      # Type cards yourself"
echo "  python main.py auto        # Auto screen capture"
echo "  python main.py calibrate   # Set up screen regions first"
echo ""
