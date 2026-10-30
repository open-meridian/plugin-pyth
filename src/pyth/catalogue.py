"""Pyth's feed catalogue, read into the plugin's datasets.

Hermes' `/v2/price_feeds` lists every feed Pyth publishes: its 32-byte ID
in hex, and its attributes -- its symbol (`Crypto.BTC/USD`,
`Equity.US.AAPL/USD`, `InterestRate.Index.CMUS10Y`), its asset type, its
description and its quote currency. Each feed goes to one dataset by Pyth's
own family (ruling 893's keys), or to none, with why:

- `crypto`, `fx`, `equity`, `metal`, `commodities`: Pyth's asset types
  `Crypto`, `FX`, `Equity`, `Metal` and `Commodities`, a base priced in a
  quote (`BTC` in `USD`). Their prices wait for the contract-28 amendment
  (rulings 896 to 898): the lake's price has no kind for Pyth's composite of
  its publishers and no field for its confidence interval yet, so these
  datasets are declared and not presented (prices.py).
- `rates`: Pyth's US Treasury constant-maturity par yields
  (`InterestRate.Index.CMUS<tenor>`), one curve, a point per tenor -- the
  rate kind as it is (rates.py).
- `treasury_prices`: the on-the-run US Treasuries, their clean prices
  (`InterestRate.US10Y/USD`) and their yields (`InterestRate.US10Y`), each a
  security that rolls to the newest issue. They wait for v29's `bond`
  template, so the dataset is declared and not presented.
- none: the constant-maturity discount factors (`...DF`, deferred), the
  reference rates Pyth relays (SOFR, EFFR, OBFR, BGCR, TGCR: Hermes states
  no effective date, which a fixing's row needs), and the kinds no dataset
  here holds (redemption rates, funding rates, NAVs, indices of crypto).

A feed is named in the lake by its ID under the vendor scheme
`pyth_feed_id` (ruling 895) where a row or a miss names it; never a key in
core.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

CRYPTO, FX, EQUITY, METAL, COMMODITIES = "crypto", "fx", "equity", "metal", "commodities"
RATES, TREASURY_PRICES = "rates", "treasury_prices"
#: The price families, by Pyth's asset type.
PRICE_FAMILIES = {
    "Crypto": CRYPTO,
    "FX": FX,
    "Equity": EQUITY,
    "Metal": METAL,
    "Commodities": COMMODITIES,
}
#: Every dataset this plugin declares, in the catalogue's order.
KEYS = (CRYPTO, FX, EQUITY, METAL, COMMODITIES, RATES, TREASURY_PRICES)
#: The vendor scheme a Pyth feed's ID is named by (ruling 895).
SCHEME = "pyth_feed_id"

_CONSTANT_MATURITY = re.compile(r"^InterestRate\.Index\.CMUS(\d+[WMY])$")
_DISCOUNT_FACTOR = re.compile(r"^InterestRate\.Index\.CMUS\d+[WMY]DF$")
_ON_THE_RUN = re.compile(r"^InterestRate\.US(\d+[WMY])(OFF)?(/USD)?$")
_REFERENCE_RATES = {"SOFR", "EFFR", "OBFR", "BGCR", "TGCR"}

#: Why a feed is in no dataset this version, by its kind.
NOT_SERVED = {
    "discount_factor": "a constant-maturity discount factor: deferred (ruling 898)",
    "reference_rate": (
        "a reference rate Pyth relays: Hermes states no effective date, which a fixing's "
        "row needs; the administrator's own plugin records it"
    ),
    "other": "a kind of value no dataset of this plugin holds",
}


@dataclass(frozen=True)
class PythFeed:
    """One feed of Pyth's catalogue: its ID, its symbol and description as
    Pyth writes them, its asset type, its base and quote (the quote currency
    Pyth states), the dataset it belongs to (empty for none, with why), and
    for a curve's point its tenor."""

    feed_id: str
    symbol: str
    asset_type: str
    description: str
    base: str = ""
    quote: str = ""
    dataset: str = ""
    tenor: str = ""
    why_not: str = ""

    @property
    def short_id(self) -> str:
        return self.feed_id[:8]


def _base_of(symbol: str, asset_type: str) -> str:
    """The base a price feed prices, in Pyth's words: `BTC` of
    `Crypto.BTC/USD`, `AAPL` of `Equity.US.AAPL/USD`, `Index.BRENT` of
    `Commodities.Index.BRENT/USD`."""
    named = symbol.split(".", 1)[1] if "." in symbol else symbol
    named = named.split("/", 1)[0]
    if asset_type == "Equity" and "." in named:
        named = named.split(".", 1)[1]
    return named


def classify(feed_id: str, attributes: dict[str, object]) -> PythFeed:
    """A feed of the catalogue, put in its dataset or in none with why."""
    symbol = str(attributes.get("symbol", ""))
    asset_type = str(attributes.get("asset_type", ""))
    quote = str(attributes.get("quote_currency", "") or "")
    said = {
        "feed_id": feed_id.lower().removeprefix("0x"),
        "symbol": symbol,
        "asset_type": asset_type,
        "description": str(attributes.get("description", "")),
        "quote": quote,
    }
    if asset_type in PRICE_FAMILIES and "/" in symbol:
        return PythFeed(
            **said, base=_base_of(symbol, asset_type), dataset=PRICE_FAMILIES[asset_type]
        )
    point = _CONSTANT_MATURITY.match(symbol)
    if point:
        return PythFeed(**said, base="CMUS", dataset=RATES, tenor=point.group(1))
    if _DISCOUNT_FACTOR.match(symbol):
        return PythFeed(**said, why_not=NOT_SERVED["discount_factor"])
    on_the_run = _ON_THE_RUN.match(symbol)
    if on_the_run:
        return PythFeed(**said, base=symbol.split(".", 1)[1].split("/", 1)[0],
                        dataset=TREASURY_PRICES, tenor=on_the_run.group(1))  # fmt: skip
    if symbol.removeprefix("InterestRate.") in _REFERENCE_RATES:
        return PythFeed(**said, why_not=NOT_SERVED["reference_rate"])
    return PythFeed(**said, why_not=NOT_SERVED["other"])


def read_catalogue(body: str) -> list[PythFeed]:
    """Hermes' catalogue answer, each feed classified; an entry without an
    ID or attributes is left out."""
    listed = json.loads(body)
    out: list[PythFeed] = []
    for entry in listed if isinstance(listed, list) else []:
        attributes = entry.get("attributes") if isinstance(entry, dict) else None
        feed_id = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(attributes, dict) and isinstance(feed_id, str) and feed_id:
            out.append(classify(feed_id, attributes))
    return out


@dataclass
class Catalogue:
    """The catalogue as last read: every feed, by ID and by dataset."""

    feeds: list[PythFeed]
    read_at_ns: int = 0

    def of(self, dataset: str) -> list[PythFeed]:
        return [f for f in self.feeds if f.dataset == dataset]

    def by_id(self, feed_id: str) -> PythFeed | None:
        return next((f for f in self.feeds if f.feed_id == feed_id), None)

    def counts(self) -> dict[str, int]:
        """How many feeds each dataset holds, and how many are in none."""
        held = {key: len(self.of(key)) for key in KEYS}
        held[""] = len([f for f in self.feeds if not f.dataset])
        return held
