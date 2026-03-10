from dataclasses import dataclass, field


def _detect_exchange(symbol: str) -> str:
    """Auto-detect exchange from symbol. ASX tickers end with .AX."""
    return "ASX" if symbol.upper().endswith(".AX") else "US"


def _currency_for_exchange(exchange: str) -> str:
    return "AUD" if exchange == "ASX" else "USD"


@dataclass
class Holding:
    symbol: str
    shares: float
    price: float
    exchange: str = ""

    def __post_init__(self):
        if not self.exchange:
            self.exchange = _detect_exchange(self.symbol)

    @property
    def currency(self) -> str:
        return _currency_for_exchange(self.exchange)

    @property
    def value(self) -> float:
        return self.shares * self.price

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "shares": self.shares,
            "price": self.price,
            "exchange": self.exchange,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Holding":
        exchange = data.get("exchange", _detect_exchange(data["symbol"]))
        return cls(
            symbol=data["symbol"],
            shares=data["shares"],
            price=data["price"],
            exchange=exchange,
        )


@dataclass
class Portfolio:
    holdings: dict[str, Holding] = field(default_factory=dict)
    targets: dict[str, float] = field(default_factory=dict)
    # Optional AUD->USD forex rate for cross-currency totals
    aud_usd_rate: float | None = None

    @property
    def total_value(self) -> float:
        return sum(h.value for h in self.holdings.values())

    def total_value_by_exchange(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for h in self.holdings.values():
            totals[h.exchange] = totals.get(h.exchange, 0.0) + h.value
        return totals

    def actual_pct(self, symbol: str) -> float:
        total = self.total_value
        if total == 0:
            return 0.0
        holding = self.holdings.get(symbol)
        if not holding:
            return 0.0
        return (holding.value / total) * 100

    def actual_pct_within_exchange(self, symbol: str) -> float:
        holding = self.holdings.get(symbol)
        if not holding:
            return 0.0
        exchange_total = sum(
            h.value for h in self.holdings.values() if h.exchange == holding.exchange
        )
        if exchange_total == 0:
            return 0.0
        return (holding.value / exchange_total) * 100

    def add_holding(self, symbol: str, shares: float, price: float, exchange: str = ""):
        symbol = symbol.upper()
        if not exchange:
            exchange = _detect_exchange(symbol)
        if symbol in self.holdings:
            self.holdings[symbol].shares += shares
            self.holdings[symbol].price = price
        else:
            self.holdings[symbol] = Holding(symbol=symbol, shares=shares, price=price, exchange=exchange)

    def remove_holding(self, symbol: str) -> bool:
        symbol = symbol.upper()
        if symbol in self.holdings:
            del self.holdings[symbol]
            return True
        return False

    def update_price(self, symbol: str, price: float) -> bool:
        symbol = symbol.upper()
        if symbol in self.holdings:
            self.holdings[symbol].price = price
            return True
        return False

    def update_shares(self, symbol: str, shares: float) -> bool:
        symbol = symbol.upper()
        if symbol in self.holdings:
            self.holdings[symbol].shares = shares
            return True
        return False

    def set_target(self, symbol: str, pct: float):
        symbol = symbol.upper()
        self.targets[symbol] = pct

    def remove_target(self, symbol: str) -> bool:
        symbol = symbol.upper()
        if symbol in self.targets:
            del self.targets[symbol]
            return True
        return False

    def targets_total(self) -> float:
        return sum(self.targets.values())

    def to_dict(self) -> dict:
        d = {
            "holdings": {s: h.to_dict() for s, h in self.holdings.items()},
            "targets": self.targets,
        }
        if self.aud_usd_rate is not None:
            d["aud_usd_rate"] = self.aud_usd_rate
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        portfolio = cls()
        for symbol, h_data in data.get("holdings", {}).items():
            portfolio.holdings[symbol] = Holding.from_dict(h_data)
        portfolio.targets = data.get("targets", {})
        portfolio.aud_usd_rate = data.get("aud_usd_rate")
        return portfolio
