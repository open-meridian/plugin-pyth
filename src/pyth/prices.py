"""Pyth's prices in the lake (rulings 893 to 898, 906 and 990).

A Pyth price is the composite of its publishers' prices, with a confidence
interval around it and the second Pyth published it. Contract 28 as amended
(ruling 906) says it as it is: the price keeps its real kind, `mid`, the
class of source behind it is declared on the dataset -- `price_source_class`
`composite` (declared.py) -- and the interval travels on the price as
`Price.confidence`, in the price's own unit (ruling 895). No price is
recorded under another kind.

An update read into a `PythPrice` -- its subject, the currency it is in, its
value, its confidence interval and its published time, exact -- is the
lake's price by `row`: a `mid`, `per_unit`, its business date UTC's date of
the second Pyth published it (the price datasets' day, declared.py), that
second its published time and the start of its validity, its row key the
subject and the second, so each second published is its own row.

**Priced in a currency.** A price is recorded in its quote currency by its
ISO 4217 code. A crypto feed quoted in another token (`Crypto.ETH/BTC`) is
not served this version: its quote has no code, and its own record is not
resolved here (`quoted_in_a_currency`).

`treasury_prices` waits for v29's `bond` template instead: an on-the-run
Treasury is a security that rolls to the newest issue, which no instrument
here describes yet.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import meridian
from meridian.operations import Money, ObservationMeta, Price, SourceTime
from meridian.plugin.v1 import operations_pb2 as ops

from .catalogue import CRYPTO, PythFeed
from .hermes import Update

#: The kind every Pyth price is recorded under (ruling 906): a composite's
#: is its mid.
MID = "mid"
#: Why a crypto feed quoted in a token is not served.
WHY_TOKEN_QUOTE = (
    "a crypto asset Pyth quotes in another token (ETH in BTC) is not served this version: the "
    "quote has no ISO 4217 code, and its own record is not resolved here"
)
#: Why the on-the-run Treasuries are not presented.
WHY_TREASURIES_WAIT = (
    "an on-the-run Treasury is a security that rolls to the newest issue: its clean price "
    "and yield wait for v29's bond template"
)

#: Who stands behind each dataset, as Pyth names them, said on the Datasets
#: page and in the docs (ruling 387; ruling 865 allows an aggregator).
#: Pyth's announcement of July 2026 names OpenYield, Fenics Market Data and
#: Tradeweb as publishers of its US Treasury pricing; no feed names its
#: publishers one by one.
COMPOSITE = "Pyth Network's composite of its publishers' prices"
TREASURY_PUBLISHERS = (
    "Pyth Network's composite of its publishers, among them OpenYield, Fenics Market Data "
    "and Tradeweb"
)


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


def quoted_in_a_currency(feed: PythFeed, tokens: Collection[str]) -> bool:
    """Whether a price feed's quote is a currency, by its ISO 4217 code: any
    family's but a crypto feed's quoted in a token -- one Pyth prices as a
    crypto asset of its own (`tokens`, the crypto feeds' bases)."""
    quote = feed.quote.strip().upper()
    if len(quote) != 3 or not quote.isalpha():
        return False
    return not (feed.dataset == CRYPTO and quote in tokens)


def business_date(published_ns: int) -> str:
    """UTC's date of the second Pyth published a price: the price datasets'
    day (declared.py)."""
    return datetime.fromtimestamp(published_ns // 1_000_000_000, tz=UTC).date().isoformat()


def row(price: PythPrice, dataset: str, raw: ops.RawRecordRef) -> Price:
    """The lake's price for a `PythPrice`: its `mid`, in its quote currency,
    with its confidence interval (ruling 906)."""
    second = price.published_ns // 1_000_000_000
    return Price(
        meta=ObservationMeta(
            row_key=f"pyth:mid:{price.subject}:{second}",
            subjects=[meridian.SubjectRef(entity_id=price.subject)],
            source=ops.Source(dataset=dataset),
            valid_from_ns=price.published_ns,
            business_date=business_date(price.published_ns),
            source_times=[SourceTime(kind="published", at_ns=price.published_ns)],
            raw=raw,
        ),
        kind=MID,
        price=Money(price.value, price.quote.strip().upper()),
        basis="per_unit",
        confidence=price.confidence,
    )
