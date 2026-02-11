from dataclasses import dataclass, field

VALID_MARKETS = ("US", "ASX")


@dataclass
class Holding:
    symbol: str
    shares: float
    price: float
    market: str = "US"  # "US" or "ASX"

    @property
    def value(self) -> float:
        return self.shares * self.price

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "shares": self.shares,
            "price": self.price,
            "market": self.market,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Holding":
        return cls(
            symbol=data["symbol"],
            shares=data["shares"],
            price=data["price"],
            market=data.get("market", "US"),
        )


@dataclass
class Portfolio:
    holdings: dict[str, Holding] = field(default_factory=dict)
    targets: dict[str, float] = field(default_factory=dict)

    @property
    def total_value(self) -> float:
        return sum(h.value for h in self.holdings.values())

    def actual_pct(self, symbol: str) -> float:
        total = self.total_value
        if total == 0:
            return 0.0
        holding = self.holdings.get(symbol)
        if not holding:
            return 0.0
        return (holding.value / total) * 100

    def add_holding(self, symbol: str, shares: float, price: float, market: str = "US"):
        symbol = symbol.upper()
        market = market.upper()
        if symbol in self.holdings:
            self.holdings[symbol].shares += shares
            self.holdings[symbol].price = price
            self.holdings[symbol].market = market
        else:
            self.holdings[symbol] = Holding(
                symbol=symbol, shares=shares, price=price, market=market
            )

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

    def symbols_with_markets(self) -> list[tuple[str, str]]:
        """Return list of (symbol, market) tuples for all holdings."""
        return [(h.symbol, h.market) for h in self.holdings.values()]

    def to_dict(self) -> dict:
        return {
            "holdings": {s: h.to_dict() for s, h in self.holdings.items()},
            "targets": self.targets,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        portfolio = cls()
        for symbol, h_data in data.get("holdings", {}).items():
            portfolio.holdings[symbol] = Holding.from_dict(h_data)
        portfolio.targets = data.get("targets", {})
        return portfolio
