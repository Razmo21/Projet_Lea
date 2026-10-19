"""Independent regression test; fix the source, not this test."""

import unittest
from app import add


class AddTests(unittest.TestCase):
    """Cover the requested arithmetic contract."""

    def test_addition(self):
        """Two and three must total five."""
        self.assertEqual(add(2, 3), 5)


if __name__ == '__main__':
    unittest.main()
