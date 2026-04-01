"""
Screen capture and card detection for Stake.us poker.
Uses screenshot capture + OCR to detect player hole cards and community cards.
"""

import mss
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageGrab
import re
import time
import json
import os

# Card rank mappings
RANK_MAP = {
    '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7',
    '8': '8', '9': '9', '10': 'T', 'T': 'T', 'J': 'J', 'Q': 'Q',
    'K': 'K', 'A': 'A',
    # OCR misreads
    'l': 'J', 'I': 'J', '1': 'A', 'O': 'Q', '0': 'Q',
}

SUIT_MAP = {
    '♠': 's', '♥': 'h', '♦': 'd', '♣': 'c',
    's': 's', 'h': 'h', 'd': 'd', 'c': 'c',
    'spade': 's', 'heart': 'h', 'diamond': 'd', 'club': 'c',
}

# Color-based suit detection (RGB ranges)
SUIT_COLORS = {
    's': {'min': (0, 0, 0), 'max': (80, 80, 80)},        # black = spades
    'c': {'min': (0, 80, 0), 'max': (80, 200, 80)},       # green = clubs
    'h': {'min': (180, 0, 0), 'max': (255, 80, 80)},      # red = hearts
    'd': {'min': (0, 0, 180), 'max': (80, 80, 255)},      # blue = diamonds
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'regions.json')

DEFAULT_REGIONS = {
    "screen_width": 1920,
    "screen_height": 1080,
    "hole_card_1": {"x": 870, "y": 680, "w": 50, "h": 70},
    "hole_card_2": {"x": 940, "y": 680, "w": 50, "h": 70},
    "community_1":  {"x": 720, "y": 380, "w": 50, "h": 70},
    "community_2":  {"x": 790, "y": 380, "w": 50, "h": 70},
    "community_3":  {"x": 860, "y": 380, "w": 50, "h": 70},
    "community_4":  {"x": 930, "y": 380, "w": 50, "h": 70},
    "community_5":  {"x": 1000, "y": 380, "w": 50, "h": 70},
    "pot_area":     {"x": 860, "y": 320, "w": 200, "h": 40},
}


def load_regions():
    """Load screen regions from config file, or return defaults."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_REGIONS.copy()


def save_regions(regions):
    """Save screen regions to config file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(regions, f, indent=2)


def capture_region(region, monitor_num=0):
    """Capture a specific screen region and return as PIL Image."""
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_num + 1 < len(monitors):
            mon = monitors[monitor_num + 1]  # mss uses 1-indexed for real monitors
        else:
            mon = monitors[1]

        bbox = {
            'left': mon['left'] + region['x'],
            'top': mon['top'] + region['y'],
            'width': region['w'],
            'height': region['h'],
        }
        screenshot = sct.grab(bbox)
        return Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')


def capture_full_screen(monitor_num=0):
    """Capture the full screen for calibration."""
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_num + 1 < len(monitors):
            mon = monitors[monitor_num + 1]
        else:
            mon = monitors[1]
        screenshot = sct.grab(mon)
        return Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')


def preprocess_card_image(img):
    """Enhance card image for better OCR results."""
    # Scale up for better OCR
    img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)

    # Convert to grayscale
    gray = img.convert('L')

    # Increase contrast
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(3.0)

    # Sharpen
    gray = gray.filter(ImageFilter.SHARPEN)

    # Threshold to black and white
    gray = gray.point(lambda x: 0 if x < 140 else 255, '1')

    return gray


def detect_suit_by_color(img):
    """Detect card suit by analyzing the dominant color in the card image."""
    pixels = list(img.getdata())
    if not pixels:
        return None

    # Count colored pixels (non-white, non-gray)
    color_counts = {'s': 0, 'c': 0, 'h': 0, 'd': 0}

    for r, g, b in pixels:
        # Skip white/near-white pixels (card background)
        if r > 200 and g > 200 and b > 200:
            continue
        # Skip very dark pixels that could be text
        if r < 30 and g < 30 and b < 30:
            color_counts['s'] += 1
            continue

        # Red detection (hearts/diamonds on most poker sites)
        if r > 150 and g < 100 and b < 100:
            color_counts['h'] += 1
        # Green detection (clubs on some sites)
        elif g > 100 and r < 100 and b < 100:
            color_counts['c'] += 1
        # Blue detection (diamonds on some sites)
        elif b > 150 and r < 100 and g < 100:
            color_counts['d'] += 1
        # Black detection (spades/clubs)
        elif r < 80 and g < 80 and b < 80:
            color_counts['s'] += 1

    if max(color_counts.values()) == 0:
        return None

    # On most poker sites: red = hearts/diamonds, black = spades/clubs
    # We'll refine this with suit symbol detection
    return max(color_counts, key=color_counts.get)


def ocr_card_rank(img):
    """Extract card rank from preprocessed image using OCR."""
    processed = preprocess_card_image(img)

    # Crop to top-left corner where rank is displayed
    rank_region = processed.crop((0, 0, processed.width // 2, processed.height // 3))

    text = pytesseract.image_to_string(
        rank_region,
        config='--psm 10 -c tessedit_char_whitelist=23456789TJQKA10'
    ).strip().upper()

    # Clean up OCR result
    text = text.replace('\n', '').replace(' ', '')

    if text in RANK_MAP:
        return RANK_MAP[text]

    # Try single character
    for char in text:
        if char in RANK_MAP:
            return RANK_MAP[char]

    return None


def detect_card(region, monitor_num=0):
    """Detect a card from a screen region. Returns card string like 'Ah' or None."""
    img = capture_region(region, monitor_num)

    # Check if region contains a card (not empty/facedown)
    # Cards are typically white/light with colored symbols
    pixels = list(img.getdata())
    avg_brightness = sum(sum(p) / 3 for p in pixels) / len(pixels) if pixels else 0

    # If too dark, probably no card or facedown
    if avg_brightness < 50:
        return None

    # Detect rank via OCR
    rank = ocr_card_rank(img)
    if not rank:
        return None

    # Detect suit via color analysis
    suit = detect_suit_by_color(img)
    if not suit:
        return None

    return rank + suit


def detect_all_cards(regions=None, monitor_num=0):
    """
    Detect all visible cards on the poker table.

    Returns:
        dict with keys:
            'hole_cards': list of card strings (e.g., ['Ah', 'Kd'])
            'community_cards': list of card strings
            'pot': float or None
    """
    if regions is None:
        regions = load_regions()

    result = {
        'hole_cards': [],
        'community_cards': [],
        'pot': None,
    }

    # Detect hole cards
    for key in ['hole_card_1', 'hole_card_2']:
        if key in regions:
            card = detect_card(regions[key], monitor_num)
            if card:
                result['hole_cards'].append(card)

    # Detect community cards
    for i in range(1, 6):
        key = f'community_{i}'
        if key in regions:
            card = detect_card(regions[key], monitor_num)
            if card:
                result['community_cards'].append(card)

    # Try to detect pot size
    if 'pot_area' in regions:
        try:
            pot_img = capture_region(regions['pot_area'], monitor_num)
            pot_processed = preprocess_card_image(pot_img)
            pot_text = pytesseract.image_to_string(
                pot_processed,
                config='--psm 7 -c tessedit_char_whitelist=0123456789,.$'
            ).strip()
            # Extract number from text like "$1,234.56"
            nums = re.findall(r'[\d,]+\.?\d*', pot_text.replace(',', ''))
            if nums:
                result['pot'] = float(nums[0])
        except Exception:
            pass

    return result


def calibrate_interactive(monitor_num=0):
    """
    Interactive calibration mode. Takes a screenshot and lets the user
    define card regions by clicking.
    """
    print("\n=== CALIBRATION MODE ===")
    print("Taking a screenshot of your poker table...")
    print("Make sure a hand is in progress with cards visible!\n")

    img = capture_full_screen(monitor_num)
    calib_path = os.path.join(os.path.dirname(__file__), 'calibration_screenshot.png')
    img.save(calib_path)

    print(f"Screenshot saved to: {calib_path}")
    print(f"Screenshot size: {img.width}x{img.height}")
    print()
    print("Now you need to identify the card regions.")
    print("Open the screenshot and note the pixel coordinates of each card area.")
    print()

    regions = load_regions()
    regions['screen_width'] = img.width
    regions['screen_height'] = img.height

    print("For each card region, enter: x y w h (space-separated)")
    print("Press Enter to skip (keep default/current value)")
    print()

    region_names = [
        ('hole_card_1', 'Your first hole card'),
        ('hole_card_2', 'Your second hole card'),
        ('community_1', 'First community card (flop 1)'),
        ('community_2', 'Second community card (flop 2)'),
        ('community_3', 'Third community card (flop 3)'),
        ('community_4', 'Fourth community card (turn)'),
        ('community_5', 'Fifth community card (river)'),
        ('pot_area', 'Pot size display area'),
    ]

    for key, desc in region_names:
        current = regions.get(key, {})
        default_str = f"[current: x={current.get('x', '?')} y={current.get('y', '?')} w={current.get('w', '?')} h={current.get('h', '?')}]"
        val = input(f"  {desc} {default_str}: ").strip()
        if val:
            parts = val.split()
            if len(parts) == 4:
                regions[key] = {
                    'x': int(parts[0]),
                    'y': int(parts[1]),
                    'w': int(parts[2]),
                    'h': int(parts[3]),
                }

    save_regions(regions)
    print(f"\nRegions saved to {CONFIG_FILE}")
    print("You can edit this file directly if needed.\n")
    return regions


def quick_test(monitor_num=0):
    """Quick test to see what cards are detected right now."""
    print("Detecting cards on screen...")
    result = detect_all_cards(monitor_num=monitor_num)
    print(f"  Hole cards:      {result['hole_cards']}")
    print(f"  Community cards: {result['community_cards']}")
    print(f"  Pot:             {result['pot']}")
    return result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'calibrate':
        mon = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        calibrate_interactive(mon)
    elif len(sys.argv) > 1 and sys.argv[1] == 'test':
        mon = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        quick_test(mon)
    else:
        print("Usage:")
        print("  python card_detector.py calibrate [monitor_num]  - Calibrate card regions")
        print("  python card_detector.py test [monitor_num]       - Test card detection")
