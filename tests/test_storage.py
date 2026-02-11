import json
import os
import tempfile
import unittest

from portfolio_tracker import storage
from portfolio_tracker.models import Portfolio


class TestStorage(unittest.TestCase):
    def test_save_and_load(self):
        p = Portfolio()
        p.add_holding("AAPL", 10, 150.0)
        p.set_target("AAPL", 60.0)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            storage.save(p, path)
            p2 = storage.load(path)
            self.assertEqual(len(p2.holdings), 1)
            self.assertAlmostEqual(p2.holdings["AAPL"].shares, 10)
            self.assertEqual(p2.targets["AAPL"], 60.0)
        finally:
            os.unlink(path)

    def test_load_missing_file(self):
        p = storage.load("/tmp/nonexistent_portfolio_test.json")
        self.assertEqual(len(p.holdings), 0)
        self.assertEqual(len(p.targets), 0)

    def test_saved_file_is_valid_json(self):
        p = Portfolio()
        p.add_holding("MSFT", 20, 300.0)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            storage.save(p, path)
            with open(path) as f:
                data = json.load(f)
            self.assertIn("holdings", data)
            self.assertIn("targets", data)
            self.assertIn("MSFT", data["holdings"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
