"""Pyth's US Treasury constant-maturity par yields as the lake's rates (the
`rates` dataset; contract v27's rates slice, the SDK's `rates.Feed`).

Pyth computes a constant-maturity par yield for each of its tenors
(`InterestRate.Index.CMUS2Y` ... `CMUS30Y`, "PYTH US TREASURY 10 YEAR
CONSTANT MATURITY PAR YIELD"), in per cent, through the US Treasury market's
day. Each is a point of the US Treasury par yield curve, so it is recorded
against the curve's record -- the platform's seeded referential record
named by Treasury's own title under `ustreasury`, the one the Treasury's
plugin records its daily curve against -- with its tenor, as another
source's point of that curve: both sit under the deployment's source
priority, and neither is the other's.

**A point** is a `par_yield`, bond-equivalent (`rates.BOND_EQUIVALENT`),
its value the yield Pyth states as an exact decimal, its business date New
York's date of the second Pyth published it, and that second its published
time. Its row key names the source, the kind, the tenor, the convention,
the date and the record, never the time: through the day each new value of
a tenor is the next version of the day's row, and the day's last is the
row as it stands.

**What is not a point**: a discount factor (`...DF`), deferred; a tenor
Pyth has not published is no row, never a zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from meridian.operations import Rate
from meridian.roles.data import rates

from .catalogue import PythFeed
from .hermes import Update

#: New York: the US Treasury market's day.
NEW_YORK = ZoneInfo("America/New_York")
#: The curve's record: Treasury's par yield curve, as the platform seeds it.
CURVE = ("symbol", "Daily Treasury Par Yield Curve Rates", "ustreasury")
CURVE_DESCRIPTION = "US Treasury par yield curve"
#: Who this plugin is, on its rows and its misses.
SOURCE = "pyth"
KIND = "par_yield"


def business_date(published_ns: int) -> str:
    """New York's date of the moment Pyth published a value."""
    return (
        datetime.fromtimestamp(published_ns / 1e9, tz=UTC).astimezone(NEW_YORK).date().isoformat()
    )


def points(
    feed: rates.Feed,
    subject: str,
    key: str,
    updates: Sequence[tuple[Update, str]],
    by_id: dict[str, PythFeed],
) -> list[Rate]:
    """The rows of the curve's points the updates state: one per update of a
    constant-maturity feed, each naming the raw record it came in."""
    rows = []
    for update, raw_key in updates:
        held = by_id.get(update.feed_id)
        if held is None or not held.tenor:
            continue
        rows.append(
            feed.rate(
                subject,
                key,
                KIND,
                rates.percent(update.price),
                business_date=business_date(update.published_ns),
                published_ns=update.published_ns,
                convention=rates.BOND_EQUIVALENT,
                tenor=held.tenor,
                raw_key=raw_key,
            )
        )
    return rows
