"""Regression tests for the intentionally broken Stage 10 calculator project."""

import unittest

from calculator import add


class CalculatorTests(unittest.TestCase):
    """Verify the small public arithmetic contract."""

    def test_adds_two_positive_integers(self) -> None:
        """The agent must repair the source without changing this observed test."""

        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
