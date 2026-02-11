import unittest
from unittest.mock import patch, MagicMock
import json

from portfolio_tracker.prices import Quote, fetch_quote, _yahoo_symbol


class TestYahooSymbol(unittest.TestCase):
    def test_us_stock(self):
        self.assertEqual(_yahoo_symbol("AAPL", "US"), "AAPL")

    def test_asx_stock(self):
        self.assertEqual(_yahoo_symbol("CBA", "ASX"), "CBA.AX")

    def test_asx_suffix(self):
        self.assertEqual(_yahoo_symbol("BHP", "ASX"), "BHP.AX")


class TestQuote(unittest.TestCase):
    def test_is_market_open_regular(self):
        q = Quote("AAPL", 150.0, "USD", "REGULAR", "Apple Inc")
        self.assertTrue(q.is_market_open)

    def test_is_market_closed(self):
        q = Quote("AAPL", 150.0, "USD", "CLOSED", "Apple Inc")
        self.assertFalse(q.is_market_open)

    def test_is_market_pre(self):
        q = Quote("AAPL", 150.0, "USD", "PRE", "Apple Inc")
        self.assertFalse(q.is_market_open)


class TestFetchQuote(unittest.TestCase):
    @patch("portfolio_tracker.prices._fetch_json")
    def test_fetch_us_stock(self, mock_fetch):
        mock_fetch.return_value = {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 175.50,
                        "currency": "USD",
                        "marketState": "REGULAR",
                        "shortName": "Apple Inc",
                    }
                }]
            }
        }
        quote = fetch_quote("AAPL", "US")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.symbol, "AAPL")
        self.assertAlmostEqual(quote.price, 175.50)
        self.assertEqual(quote.currency, "USD")
        self.assertTrue(quote.is_market_open)

    @patch("portfolio_tracker.prices._fetch_json")
    def test_fetch_asx_stock(self, mock_fetch):
        mock_fetch.return_value = {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 112.30,
                        "currency": "AUD",
                        "marketState": "CLOSED",
                        "shortName": "COMMONWEALTH BANK",
                    }
                }]
            }
        }
        quote = fetch_quote("CBA", "ASX")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.symbol, "CBA")
        self.assertAlmostEqual(quote.price, 112.30)
        self.assertEqual(quote.currency, "AUD")
        self.assertFalse(quote.is_market_open)

    @patch("portfolio_tracker.prices._fetch_json")
    def test_fetch_returns_none_on_error(self, mock_fetch):
        import urllib.error
        mock_fetch.side_effect = urllib.error.URLError("Network error")
        quote = fetch_quote("INVALID", "US")
        self.assertIsNone(quote)

    @patch("portfolio_tracker.prices._fetch_json")
    def test_fetch_returns_none_on_bad_response(self, mock_fetch):
        mock_fetch.return_value = {"chart": {"result": []}}
        quote = fetch_quote("AAPL", "US")
        self.assertIsNone(quote)


if __name__ == "__main__":
    unittest.main()
