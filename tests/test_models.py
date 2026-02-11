import unittest

from portfolio_tracker.models import Holding, Portfolio


class TestHolding(unittest.TestCase):
    def test_value(self):
        h = Holding("AAPL", shares=10, price=150.0)
        self.assertAlmostEqual(h.value, 1500.0)

    def test_to_dict_from_dict(self):
        h = Holding("AAPL", shares=10, price=150.0)
        d = h.to_dict()
        h2 = Holding.from_dict(d)
        self.assertEqual(h.symbol, h2.symbol)
        self.assertEqual(h.shares, h2.shares)
        self.assertEqual(h.price, h2.price)


class TestPortfolio(unittest.TestCase):
    def setUp(self):
        self.p = Portfolio()

    def test_add_holding(self):
        self.p.add_holding("AAPL", 10, 150.0)
        self.assertIn("AAPL", self.p.holdings)
        self.assertEqual(self.p.holdings["AAPL"].shares, 10)

    def test_add_holding_accumulates(self):
        self.p.add_holding("AAPL", 10, 150.0)
        self.p.add_holding("AAPL", 5, 155.0)
        self.assertEqual(self.p.holdings["AAPL"].shares, 15)
        self.assertEqual(self.p.holdings["AAPL"].price, 155.0)

    def test_remove_holding(self):
        self.p.add_holding("AAPL", 10, 150.0)
        self.assertTrue(self.p.remove_holding("AAPL"))
        self.assertNotIn("AAPL", self.p.holdings)

    def test_remove_holding_not_found(self):
        self.assertFalse(self.p.remove_holding("AAPL"))

    def test_total_value(self):
        self.p.add_holding("AAPL", 10, 100.0)
        self.p.add_holding("GOOG", 5, 200.0)
        self.assertAlmostEqual(self.p.total_value, 2000.0)

    def test_actual_pct(self):
        self.p.add_holding("AAPL", 10, 100.0)  # $1000
        self.p.add_holding("GOOG", 10, 100.0)  # $1000
        self.assertAlmostEqual(self.p.actual_pct("AAPL"), 50.0)
        self.assertAlmostEqual(self.p.actual_pct("GOOG"), 50.0)

    def test_actual_pct_empty(self):
        self.assertAlmostEqual(self.p.actual_pct("AAPL"), 0.0)

    def test_set_target(self):
        self.p.set_target("AAPL", 60.0)
        self.assertEqual(self.p.targets["AAPL"], 60.0)

    def test_remove_target(self):
        self.p.set_target("AAPL", 60.0)
        self.assertTrue(self.p.remove_target("AAPL"))
        self.assertNotIn("AAPL", self.p.targets)

    def test_targets_total(self):
        self.p.set_target("AAPL", 60.0)
        self.p.set_target("GOOG", 40.0)
        self.assertAlmostEqual(self.p.targets_total(), 100.0)

    def test_update_price(self):
        self.p.add_holding("AAPL", 10, 100.0)
        self.assertTrue(self.p.update_price("AAPL", 200.0))
        self.assertEqual(self.p.holdings["AAPL"].price, 200.0)

    def test_update_shares(self):
        self.p.add_holding("AAPL", 10, 100.0)
        self.assertTrue(self.p.update_shares("AAPL", 20))
        self.assertEqual(self.p.holdings["AAPL"].shares, 20)

    def test_roundtrip_serialization(self):
        self.p.add_holding("AAPL", 10, 150.0)
        self.p.add_holding("GOOG", 5, 2800.0)
        self.p.set_target("AAPL", 30.0)
        self.p.set_target("GOOG", 70.0)

        d = self.p.to_dict()
        p2 = Portfolio.from_dict(d)

        self.assertEqual(len(p2.holdings), 2)
        self.assertAlmostEqual(p2.holdings["AAPL"].shares, 10)
        self.assertAlmostEqual(p2.holdings["GOOG"].price, 2800.0)
        self.assertEqual(p2.targets["AAPL"], 30.0)
        self.assertEqual(p2.targets["GOOG"], 70.0)

    def test_case_insensitive_symbols(self):
        self.p.add_holding("aapl", 10, 100.0)
        self.assertIn("AAPL", self.p.holdings)
        self.p.set_target("goog", 50.0)
        self.assertIn("GOOG", self.p.targets)


class TestPortfolioComparison(unittest.TestCase):
    def test_over_and_under_weight(self):
        p = Portfolio()
        p.add_holding("AAPL", 75, 100.0)   # $7500 = 75%
        p.add_holding("GOOG", 25, 100.0)   # $2500 = 25%
        p.set_target("AAPL", 50.0)
        p.set_target("GOOG", 50.0)

        # AAPL is overweight: 75% actual vs 50% target
        self.assertAlmostEqual(p.actual_pct("AAPL"), 75.0)
        diff_aapl = p.actual_pct("AAPL") - p.targets["AAPL"]
        self.assertAlmostEqual(diff_aapl, 25.0)

        # GOOG is underweight: 25% actual vs 50% target
        diff_goog = p.actual_pct("GOOG") - p.targets["GOOG"]
        self.assertAlmostEqual(diff_goog, -25.0)


if __name__ == "__main__":
    unittest.main()
