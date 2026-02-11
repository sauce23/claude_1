import json
import os

from .models import Portfolio

DEFAULT_FILE = os.path.join(os.path.expanduser("~"), ".portfolio.json")


def load(path: str = DEFAULT_FILE) -> Portfolio:
    if not os.path.exists(path):
        return Portfolio()
    with open(path, "r") as f:
        data = json.load(f)
    return Portfolio.from_dict(data)


def save(portfolio: Portfolio, path: str = DEFAULT_FILE):
    with open(path, "w") as f:
        json.dump(portfolio.to_dict(), f, indent=2)
