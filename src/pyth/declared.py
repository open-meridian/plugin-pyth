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
  OpenYield, Fenics Market Data and Tradeweb -- is declared on each dataset
  once the contract-28 amendment's `underlying_source` is pinned
  (prices.py), and said in docs/terms.md meanwhile.
- **the five price families**: `meridian.v1.Price`, pulled for the latest or
  a past moment and streamed from Hermes for a standing want; real time
  (Hermes serves each update as Pyth publishes it). **Not presented** until
  the amendment's composite kind and confidence are pinned: every want is
  declined, and no price is recorded under another kind (prices.py).
- **`rates`**: `meridian.v1.Rate`, Pyth's US Treasury constant-maturity par
  yields as points of the par yield curve (curve.py): pulled for the latest
  or a past business date (its close, 17:00 New York, the Treasury market's
  schedule in Pyth's catalogue), and streamed for a standing want, each
  tenor's value recorded at most every five minutes as the next version of
  the day's row. New York's day, ending at 17:00.
- **`treasury_prices`**: `meridian.v1.Price`, the on-the-run Treasuries'
  clean prices and yields. **Not presented** until v29's `bond` template.
- `history` 0: Hermes states no bound on how far back a price at a time
  reaches; a moment before a feed's first is declined as beyond history.
- no venue (Pyth is no venue) and no calendar.

**Each licence default** is what Pyth's subscription terms say (Douro Labs'
Terminal Subscription Terms, 12 August 2026; docs/terms.md), which the
deployment's licence confirms or replaces on Data sources -- never whether
a deployment meets them: kept, for the subscriber's internal business use;
displayed in the subscriber's own products, never as a feed or file to a
third party; derived data distributable where it neither discloses nor
recreates the data, so not restricted here; redistribution not allowed
(Pro's limited rights are set by its own order); no attribution asked; Pyth's
names not affiliated. Not one person's terms: a subscription is a
business's.

**Storage**: one kind of raw record, Hermes' answers as received (never the
key), a month by default.

**Settings**, in the data role's order: no environment (Hermes has one), the
credential -- the deployment's Pyth API key, secret, which every price asks
for since 26 August 2026 -- and sample data, a developer's.
"""

from __future__ import annotations

import meridian
from meridian import DatasetDeclaration, DatasetLicence, RecordKind

from .catalogue import COMMODITIES, CRYPTO, EQUITY, FX, METAL, RATES, TREASURY_PRICES

VENDOR = "Pyth Network"
PRICE, RATE = "meridian.v1.Price", "meridian.v1.Rate"
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
LICENCE = DatasetLicence(
    kept=True,
    derived_use=True,
    derived_use_terms="not_restricted",
    display=True,
    redistribution="not_allowed",
    not_affiliated_notice=NOT_AFFILIATED,
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
        data_types=[PRICE],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        licence_default=LICENCE,
        day_time_zone="Etc/UTC",
        day_end_minute=0,
        declared_delay_ns=DECLARED_DELAY_NS,
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
        licence_default=LICENCE,
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
        licence_default=LICENCE,
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
        declared_delay_ns=DECLARED_DELAY_NS,
    ),
]
