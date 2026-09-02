import unittest

from src.context_matcher import choose_sign, load_signs


class ContextMatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signs = load_signs()

    def test_music_rock_context(self):
        result = choose_sign(
            "I listen to music. My favorite genre is rock.",
            "rock",
            self.signs,
        )
        self.assertEqual(result.sense, "music")
        self.assertFalse(result.used_default)

    def test_stone_rock_context(self):
        result = choose_sign(
            "We found a rock on the ground near the mountain.",
            "rock",
            self.signs,
        )
        self.assertEqual(result.sense, "stone")

    def test_baseball_bat_context(self):
        result = choose_sign(
            "She swung the bat and hit the baseball across the field.",
            "bat",
            self.signs,
        )
        self.assertEqual(result.sense, "baseball")

    def test_river_bank_context(self):
        result = choose_sign(
            "We walked along the bank beside the river and watched the water.",
            "bank",
            self.signs,
        )
        self.assertEqual(result.sense, "river")

    def test_default_when_context_is_unknown(self):
        result = choose_sign(
            "The story mentions rock without any useful context.",
            "rock",
            self.signs,
        )
        self.assertEqual(result.sense, "stone")
        self.assertTrue(result.used_default)

    def test_missing_word_raises_error(self):
        with self.assertRaises(LookupError):
            choose_sign("A simple story.", "missing", self.signs)


if __name__ == "__main__":
    unittest.main()
