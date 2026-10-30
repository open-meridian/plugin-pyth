"""Pyth's prices, held behind one small adapter until the lake can say them
(rulings 893 to 898).

A Pyth price is the composite of its publishers' prices -- neither a last
trade, a bid, an ask nor a mid -- with a confidence interval around it and
the second Pyth published it. Contract 28's price has no kind for a
composite and no field for a confidence interval, so recording one under
`mid` or `last` would mislabel it. An amendment to contract 28 adds
`PRICE_KIND_COMPOSITE`, `Price.confidence` and a dataset's declared
underlying source; until the SDK releasing it is pinned, the price datasets
(`crypto`, `fx`, `equity`, `metal`, `commodities`) are declared and not
presented, every want of them declined, and no price is recorded.

What is ready now is the conversion: an update read into a `PythPrice` --
its subject, the currency it is in, its value, its confidence interval and
its published time, exact -- which `row` makes the lake's price once the
amendment is pinned (`AMENDMENT_PINNED`). Moving to it is this module, the
catalogue's licence and underlying source (declared.py), and the suite's
not-presented reasons; nothing else.

`treasury_prices` waits for v29's `bond` template instead, however the
amendment lands: an on-the-run Treasury is a security that rolls to the
newest issue, which no instrument here describes yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .catalogue import PythFeed
from .hermes import Update

#: Whether the SDK this plugin pins carries the contract-28 amendment's
#: composite price kind and confidence (rulings 896 to 898): not yet.
AMENDMENT_PINNED = False

#: Why the price datasets are not presented, as the Datasets page, the docs
#: and the suite say it.
WHY_PRICES_WAIT = (
    "Pyth's composite price waits for the contract-28 amendment: the lake's price has no "
    "kind for a composite of publishers and no field for its confidence interval yet, and "
    "no price is recorded under another kind"
)
#: Why the on-the-run Treasuries are not presented.
WHY_TREASURIES_WAIT = (
    "an on-the-run Treasury is a security that rolls to the newest issue: its clean price "
    "and yield wait for v29's bond template"
)

#: Who stands behind each dataset, as Pyth names them: declared on the
#: dataset once the amendment's field is pinned, said in the docs meanwhile
#: (ruling 387; ruling 865 allows an aggregator). Pyth's announcement of
#: July 2026 names OpenYield, Fenics Market Data and Tradeweb as publishers
#: of its US Treasury pricing; no feed names its publishers one by one.
COMPOSITE = "Pyth Network's composite of its publishers' prices"
TREASURY_PUBLISHERS = (
    "Pyth Network's composite of its publishers, among them OpenYield, Fenics Market Data "
    "and Tradeweb"
)


class NotPresented(Exception):
    """A price was asked of the lake before the amendment is pinned."""


@dataclass(frozen=True)
class PythPrice:
    """One Pyth price, ready for the lake: the feed, its subject, the
    currency it is quoted in as Pyth states it, its value and confidence
    interval exactly, when Pyth published it and the raw record it came in."""

    feed_id: str
    subject: str
    quote: str
    value: Decimal
    confidence: Decimal
    published_ns: int
    raw_key: str


def price_of(update: Update, feed: PythFeed, subject: str, raw_key: str) -> PythPrice:
    """An update of a price feed, as a `PythPrice` for `subject`."""
    if update.feed_id != feed.feed_id:
        raise ValueError(f"an update of {update.feed_id} is not the feed {feed.feed_id}")
    return PythPrice(
        feed_id=feed.feed_id,
        subject=subject,
        quote=feed.quote,
        value=update.price,
        confidence=update.confidence,
        published_ns=update.published_ns,
        raw_key=raw_key,
    )


def presented() -> bool:
    """Whether the price datasets are presented: once the amendment is pinned."""
    return AMENDMENT_PINNED


def row(price: PythPrice, dataset: str) -> object:
    """The lake's price for a `PythPrice`: under `composite`, with its
    confidence, once the amendment is pinned; refused before."""
    raise NotPresented(f"{dataset}: {WHY_PRICES_WAIT}")
