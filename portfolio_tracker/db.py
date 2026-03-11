"""SQLite persistence layer for the portfolio tracker.

Schema
------
holdings  – one row per ticker (symbol PK, shares, price, exchange)
targets   – one row per ticker (symbol PK, target_pct)
settings  – generic key/value store (used for aud_usd_rate)

On first use the module auto-migrates any existing portfolio.json so
the switch to SQLite is transparent.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

from .models import Holding, Portfolio

DEFAULT_DB = os.path.join(os.path.expanduser("~"), "portfolio.db")

# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS holdings (
    symbol   TEXT PRIMARY KEY,
    shares   REAL NOT NULL,
    price    REAL NOT NULL,
    exchange TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    symbol     TEXT PRIMARY KEY,
    target_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# ── Internal helpers ──────────────────────────────────────────────────────────

@contextmanager
def _connect(path: str):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(_DDL)
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Public API ────────────────────────────────────────────────────────────────

def load(path: str = DEFAULT_DB) -> Portfolio:
    """Load the portfolio from *path* (creating tables if needed)."""
    _migrate_json_if_needed(path)
    p = Portfolio()
    with _connect(path) as con:
        for row in con.execute("SELECT symbol, shares, price, exchange FROM holdings"):
            p.holdings[row["symbol"]] = Holding(
                symbol=row["symbol"],
                shares=row["shares"],
                price=row["price"],
                exchange=row["exchange"],
            )
        for row in con.execute("SELECT symbol, target_pct FROM targets"):
            p.targets[row["symbol"]] = row["target_pct"]
        rate_row = con.execute(
            "SELECT value FROM settings WHERE key = 'aud_usd_rate'"
        ).fetchone()
        if rate_row:
            try:
                p.aud_usd_rate = float(rate_row["value"])
            except (TypeError, ValueError):
                pass
    return p


def save(portfolio: Portfolio, path: str = DEFAULT_DB):
    """Persist *portfolio* to *path* atomically."""
    with _connect(path) as con:
        # holdings – upsert all, delete removed ones
        con.execute("DELETE FROM holdings")
        con.executemany(
            "INSERT INTO holdings (symbol, shares, price, exchange) VALUES (?,?,?,?)",
            [
                (h.symbol, h.shares, h.price, h.exchange)
                for h in portfolio.holdings.values()
            ],
        )
        # targets – upsert all, delete removed ones
        con.execute("DELETE FROM targets")
        con.executemany(
            "INSERT INTO targets (symbol, target_pct) VALUES (?,?)",
            list(portfolio.targets.items()),
        )
        # settings
        if portfolio.aud_usd_rate is not None:
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('aud_usd_rate', ?)",
                (str(portfolio.aud_usd_rate),),
            )


def update_shares(symbol: str, shares: float, path: str = DEFAULT_DB):
    """Update a single holding's share count without rewriting the whole DB."""
    with _connect(path) as con:
        con.execute(
            "UPDATE holdings SET shares = ? WHERE symbol = ?", (shares, symbol)
        )


def update_target(symbol: str, target_pct: float, path: str = DEFAULT_DB):
    """Update a single target allocation without rewriting the whole DB."""
    with _connect(path) as con:
        con.execute(
            "INSERT OR REPLACE INTO targets (symbol, target_pct) VALUES (?, ?)",
            (symbol, target_pct),
        )


# ── Migration ─────────────────────────────────────────────────────────────────

def _migrate_json_if_needed(db_path: str):
    """If a portfolio.json lives next to the DB and the DB is empty, import it."""
    json_path = os.path.join(os.path.dirname(db_path), "portfolio.json")
    if not os.path.exists(json_path):
        return

    # Check if holdings table is already populated
    with _connect(db_path) as con:
        count = con.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
        if count > 0:
            return  # already migrated

        try:
            with open(json_path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        for sym, h in data.get("holdings", {}).items():
            con.execute(
                "INSERT OR IGNORE INTO holdings (symbol, shares, price, exchange) VALUES (?,?,?,?)",
                (sym, h["shares"], h["price"], h.get("exchange", "ASX")),
            )
        for sym, pct in data.get("targets", {}).items():
            con.execute(
                "INSERT OR IGNORE INTO targets (symbol, target_pct) VALUES (?,?)",
                (sym, pct),
            )
        rate = data.get("aud_usd_rate")
        if rate is not None:
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('aud_usd_rate', ?)",
                (str(rate),),
            )
