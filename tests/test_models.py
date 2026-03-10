import unittest

from portfolio_tracker.models import Holding, Portfolio, _detect_exchange


class TestExchangeDetection(unittest.TestCase):
    def test_asx_suffix(self):
        self.assertEqual(_detect_exchange("BHP.AX"), "ASX")

    def test_asx_lowercase(self):
        self.assertEqual(_detect_exchange("bhp.ax"), "ASX")

    def test_us_stock(self):
        self.assertEqual(_detect_exchange("AAPL"), "US")

    def test_us_stock_no_suffix(self):
        self.assertEqual(_detect_exchange("MSFT"), "US")


class TestHolding(unittest.TestCase):
    def test_value(self):
        h = Holding("AAPL", shares=10, price=150.0)
        self.assertAlmostEqual(h.value, 1500.0)

    def test_us_exchange_auto_detected(self):
        h = Holding("AAPL", shares=10, price=150.0)
        self.assertEqual(h.exchange, "US")
        self.assertEqual(h.currency, "USD")

    def test_asx_exchange_auto_detected(self):
        h = Holding("BHP.AX", shares=100, price=45.0)
        self.assertEqual(h.exchange, "ASX")
        self.assertEqual(h.currency, "AUD")

    def test_exchange_explicit(self):
        h = Holding("BHP", shares=100, price=45.0, exchange="ASX")
        self.assertEqual(h.exchange, "ASX")
        self.assertEqual(h.currency, "AUD")

    def test_to_dict_includes_exchange(self):
        h = Holding("BHP.AX", shares=100, price=45.0)
        d = h.to_dict()
        self.assertEqual(d["exchange"], "ASX")

    def test_from_dict_restores_exchange(self):
        h = Holding("BHP.AX", shares=100, price=45.0)
        d = h.to_dict()
        h2 = Holding.from_dict(d)
        self.assertEqual(h2.exchange, "ASX")
        self.assertEqual(h2.currency, "AUD")

    def test_from_dict_legacy_no_exchange(self):
        # Old saved data without exchange field should auto-detect
        d = {"symbol": "AAPL", "shares": 10, "price": 150.0}
        h = Holding.from_dict(d)
        self.assertEqual(h.exchange, "US")

    def test_to_dict_from_dict(self):
        h = Holding("AAPL", shares=10, price=150.0)
        d = h.to_dict()
        h2 = Holding.from_dict(d)
        self.assertEqual(h.symbol, h2.symbol)
        self.assertEqual(h.shares, h2.shares)
        self.assertEqual(h.price, h2.price)
        self.assertEqual(h.exchange, h2.exchange)


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

    def test_actual_pct_within_exchange(self):
        self.p.add_holding("AAPL", 10, 100.0)   # $1000 US
        self.p.add_holding("MSFT", 10, 100.0)   # $1000 US
        self.p.add_holding("BHP.AX", 100, 45.0)  # A$4500 ASX
        # Within US exchange: AAPL = 50%, MSFT = 50%
        self.assertAlmostEqual(self.p.actual_pct_within_exchange("AAPL"), 50.0)
        self.assertAlmostEqual(self.p.actual_pct_within_exchange("MSFT"), 50.0)
        # Within ASX exchange: BHP.AX = 100%
        self.assertAlmostEqual(self.p.actual_pct_within_exchange("BHP.AX"), 100.0)

    def test_total_value_by_exchange(self):
        self.p.add_holding("AAPL", 10, 100.0)   # $1000 US
        self.p.add_holding("BHP.AX", 100, 45.0)  # A$4500 ASX
        totals = self.p.total_value_by_exchange()
        self.assertAlmostEqual(totals["US"], 1000.0)
        self.assertAlmostEqual(totals["ASX"], 4500.0)

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
        self.p.add_holding("BHP.AX", 100, 45.0)
        self.p.set_target("AAPL", 30.0)
        self.p.set_target("BHP.AX", 70.0)
        self.p.aud_usd_rate = 0.65

        d = self.p.to_dict()
        p2 = Portfolio.from_dict(d)

        self.assertEqual(len(p2.holdings), 2)
        self.assertAlmostEqual(p2.holdings["AAPL"].shares, 10)
        self.assertAlmostEqual(p2.holdings["BHP.AX"].price, 45.0)
        self.assertEqual(p2.holdings["BHP.AX"].exchange, "ASX")
        self.assertEqual(p2.targets["AAPL"], 30.0)
        self.assertAlmostEqual(p2.aud_usd_rate, 0.65)

    def test_case_insensitive_symbols(self):
        self.p.add_holding("aapl", 10, 100.0)
        self.assertIn("AAPL", self.p.holdings)
        self.p.set_target("goog", 50.0)
        self.assertIn("GOOG", self.p.targets)

    def test_asx_symbol_normalised(self):
        self.p.add_holding("bhp.ax", 100, 45.0)
        self.assertIn("BHP.AX", self.p.holdings)
        self.assertEqual(self.p.holdings["BHP.AX"].exchange, "ASX")


class TestPortfolioComparison(unittest.TestCase):
    def test_over_and_under_weight(self):
        p = Portfolio()
        p.add_holding("AAPL", 75, 100.0)   # $7500 = 75%
        p.add_holding("GOOG", 25, 100.0)   # $2500 = 25%
        p.set_target("AAPL", 50.0)
        p.set_target("GOOG", 50.0)

        self.assertAlmostEqual(p.actual_pct("AAPL"), 75.0)
        diff_aapl = p.actual_pct("AAPL") - p.targets["AAPL"]
        self.assertAlmostEqual(diff_aapl, 25.0)

        diff_goog = p.actual_pct("GOOG") - p.targets["GOOG"]
        self.assertAlmostEqual(diff_goog, -25.0)


if __name__ == "__main__":
    unittest.main()
