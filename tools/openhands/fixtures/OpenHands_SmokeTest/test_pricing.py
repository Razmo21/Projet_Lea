"""Regression tests that OpenHands must make pass without editing this file."""

import unittest

from pricing import calculate_total, format_receipt


class PricingTests(unittest.TestCase):
    """Check the small pricing API exposed by the smoke-test project."""

    def test_discount_reduces_the_subtotal(self):
        """A ten-percent discount must reduce, not increase, the subtotal."""
        self.assertEqual(calculate_total([20, 30], 10), 45.0)

    def test_receipt_has_the_expected_label(self):
        """The receipt should use the wording expected by the caller."""
        self.assertEqual(format_receipt("Mina", 45), "Total for Mina: $45.00")
