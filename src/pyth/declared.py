"""What this version declares beside its role, `data` (W8.1, W4.1): its
settings, its catalogue and its storage, built from code and used twice --
`__main__` registers with them, and `meridian plugin upload` reads them from
the built image (declaration.py puts them together with the pages and the
documentation).

**The catalogue: seven datasets, one per family Pyth publishes** (rulings
893 to 898): `crypto`, `fx`, `equity`, `metal`, `commodities`, `rates` and
`treasury_prices`.

- `vendor` Pyth Network: the composite price Pyth computes from its
  publishers is Pyth's own, so Pyth is the originator; no aggregator. Who
  stands behind it -- "Pyth Network's composite of its publishers' prices",
  and for the Treasury families the publishers Pyth's announcement names,
  OpenYield, Fenics Market Data and Tradeweb -- is said on the Datasets page
  and in docs/terms.md, and in the Treasury datasets' terms in words.
- **the five price families**: `meridian.v1.Price` with its confidence
  interval (`meridian.v1.Price.confidence`), pulled for the latest or a
  past moment and streamed from Hermes for a standing want; real time
  (Hermes serves each update as Pyth publishes it). Each price is Pyth's
  composite `mid`, the datasets' `price_source_class` `composite` (contract
  28 as amended, ruling 906; from 0.2.0, ruling 990). Their day is UTC's.
- **`rates`**: `meridian.v1.Rate`, Pyth's US Treasury constant-maturity par
  yields as points of the par yield curve (curve.py): pulled for the latest
  or a past business date (its close, 17:00 New York, the Treasury market's
  schedule in Pyth's catalogue), and streamed for a standing want, each
  tenor's value recorded at most every five minutes as the next version of
  the day's row. New York's day, ending at 17:00.
- **`treasury_prices`**: `meridian.v1.Price`, the on-the-run Treasuries'
  clean prices and yields, a composite too. **Not presented** until v29's
  `bond` template.
- `history` 0: Hermes states no bound on how far back a price at a time
  reaches; a moment before a feed's first is declined as beyond history.
- no venue (Pyth is no venue) and no calendar.

**Its terms and pricing** (contract 30, ruling 1032): no dataset declares a
licence. Each describes Pyth's terms in plain words (`TERMS`, and
`TREASURY_TERMS` for the Treasury datasets, naming the publishers Pyth
names; ruling 1039): its plans, Douro Labs' Terminal Subscription Terms (12
August 2026) and the composite behind every value (docs/terms.md). The
deployment admin sets the deployment's licence on Data sources, which is
the one enforced -- never whether a deployment meets Pyth's terms.

**How a gap is recovered** (W10.14): `rates` is `backfill` -- a business
date's curve is read again at its close from Hermes' history, one row a
tenor a day; the price families are `stream_only` -- Hermes answers a
moment, not every update in a range, so a gap in the stream is not fetched
again whole; `treasury_prices` is `none` -- it records nothing until v29's
`bond` template. No sessions calendar, no `most_shards`.

**Storage**: one kind of raw record, Hermes' answers as received (never the
key), a month by default.

**Settings**, in the data role's order: no environment (Hermes has one), the
credential -- the deployment's Pyth API key, secret, which every price asks
for since 26 August 2026 -- and sample data, a developer's.
"""

from __future__ import annotations

import meridian
from meridian import DatasetDeclaration, RecordKind

from .catalogue import COMMODITIES, CRYPTO, EQUITY, FX, METAL, RATES, TREASURY_PRICES

VENDOR = "Pyth Network"
PRICE, RATE = "meridian.v1.Price", "meridian.v1.Rate"
#: The price's optional field each price family fills: Pyth's confidence
#: interval (ruling 895).
CONFIDENCE = "meridian.v1.Price.confidence"
#: The class of source behind every Pyth price (ruling 906).
COMPOSITE = "composite"
API_KEY, SAMPLE_DATA = "api_key", "sample_data"
#: New York's day, ending at 17:00: the US Treasury market's close in Pyth's
#: schedule for its Treasury feeds.
DAY_TIME_ZONE = "America/New_York"
DAY_END_MINUTE = 17 * 60
#: Hermes serves each update as Pyth publishes it.
DECLARED_DELAY_NS = 0

#: Its one kind of raw record, Hermes' answers as received.
KIND = "responses"
LABEL = "Raw responses"
WINDOW_DAYS = 30
RESPONSES_KIND = RecordKind(KIND, LABEL, window_days=WINDOW_DAYS)

NOT_AFFILIATED = (
    "Pyth and Pyth Network are trademarks of their owners. This plugin is not affiliated "
    "with or endorsed by the Pyth Data Association or Douro Labs."
)
#: Pyth's terms, in plain words (contract 30, ruling 1032), as docs/terms.md
#: summarises them on 30 October 2026.
TERMS = (
    "Pyth Network's prices from Hermes, each Pyth's composite of its publishers' prices. A "
    "Pyth API key under a Pyth Terminal plan is needed for every price: Free has no API "
    "access, Starter serves crypto with display rights and no redistribution, Pro every "
    "family with display and non-display rights and limited redistribution. Douro Labs' "
    "Terminal Subscription Terms (12 August 2026) put the data to the subscriber's internal "
    "business purposes; it may be displayed in the subscriber's own products, provided no "
    "third party gets it as a feed or file; derived data may be distributed where it neither "
    "discloses nor recreates the data; resale and redistribution are not allowed; fees are "
    "not cancellable. Pyth provides its feeds as they are, and they may change or stop "
    "without notice. " + NOT_AFFILIATED
)
#: The Treasury datasets' terms: Pyth's, and the publishers it names for them.
TREASURY_TERMS = TERMS + (
    " Pyth's announcement of July 2026 names OpenYield, Fenics Market Data and Tradeweb among "
    "the publishers of its US Treasury pricing."
)


@meridian.settings
class Config:
    """The settings, in the data role's order: the credential, then sample
    data."""

    api_key: str = meridian.setting(
        "Pyth API key",
        secret=True,
        description=(
            "The deployment's Pyth API key, from its Pyth Terminal account. Hermes asks for "
            "it on every price since 26 August 2026. Pyth's Starter plan serves crypto; its "
            "Pro plan every family, Treasuries and rates among them. Without it only Pyth's "
            "feed catalogue is read."
        ),
    )
    sample_data: bool = meridian.sample_data(
        description=(
            "Answer from Pyth's feed catalogue and made-up prices in Hermes' shape, committed "
            "with the plugin, instead of calling Hermes. No key needed. Development "
            "deployments only."
        )
    )


def _price(key: str) -> DatasetDeclaration:
    return DatasetDeclaration(
        key=key,
        vendor=VENDOR,
        data_types=[PRICE, CONFIDENCE],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        terms_and_pricing=TERMS,
        gap_recovery="stream_only",
        day_time_zone="Etc/UTC",
        day_end_minute=0,
        declared_delay_ns=DECLARED_DELAY_NS,
        price_source_class=COMPOSITE,
    )


CATALOGUE = [
    *(_price(key) for key in (CRYPTO, FX, EQUITY, METAL, COMMODITIES)),
    DatasetDeclaration(
        key=RATES,
        vendor=VENDOR,
        data_types=[RATE],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        terms_and_pricing=TREASURY_TERMS,
        gap_recovery="backfill",
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
        declared_delay_ns=DECLARED_DELAY_NS,
    ),
    DatasetDeclaration(
        key=TREASURY_PRICES,
        vendor=VENDOR,
        data_types=[PRICE],
        modes=["pull"],
        cadence=1,
        history=0,
        terms_and_pricing=TREASURY_TERMS,
        gap_recovery="none",
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
        declared_delay_ns=DECLARED_DELAY_NS,
        price_source_class=COMPOSITE,
    ),
]
