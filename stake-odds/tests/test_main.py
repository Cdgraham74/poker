"""Unit tests for main helpers (no screen capture)."""

import hashlib
import unittest

import main as stake_main


class TestGetStreet(unittest.TestCase):
    def test_lengths(self):
        self.assertEqual(stake_main.get_street([]), 'preflop')
        self.assertEqual(stake_main.get_street(['Ah']), 'dealing')
        self.assertEqual(stake_main.get_street(['Ah', 'Kd']), 'dealing')
        self.assertEqual(stake_main.get_street(['2c', '3c', '4c']), 'flop')
        self.assertEqual(stake_main.get_street(['2c', '3c', '4c', '5c']), 'turn')
        self.assertEqual(
            stake_main.get_street(['2c', '3c', '4c', '5c', '6c']), 'river'
        )


class TestEquitySeed(unittest.TestCase):
    def test_stable_for_same_cards(self):
        h, c = ['Ah', 'Kd'], ['Qc', 'Jc', 'Tc']
        s1 = stake_main._equity_seed(h, c)
        s2 = stake_main._equity_seed(h, c)
        self.assertEqual(s1, s2)

    def test_differs_when_cards_change(self):
        a = stake_main._equity_seed(['Ah', 'Kd'], [])
        b = stake_main._equity_seed(['As', 'Kh'], [])
        self.assertNotEqual(a, b)

    def test_matches_md5_prefix(self):
        h, c = ['2c', '3h'], ['4d']
        raw = ''.join(h) + '/' + ''.join(c)
        expect = int(hashlib.md5(raw.encode('utf-8')).hexdigest()[:8], 16)
        self.assertEqual(stake_main._equity_seed(h, c), expect)


if __name__ == '__main__':
    unittest.main()
