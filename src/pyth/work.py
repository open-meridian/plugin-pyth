"""The data plugin's work (the role `data`): Pyth's values into the lake,
converted at the edge, through the SDK's `Wants` and `rates.Feed`. `Work`
is the data role's class (open-meridian 0.35): its acts are made on itself.

**The catalogue** is read from Hermes on the first want and then daily
(catalogue.py): it says which feeds each dataset holds. It asks for no key.

**Wants** (W10.7), by dataset:

- `rates`: the subject is the US Treasury par yield curve's record
  (curve.py), resolved once by Treasury's title under `ustreasury`; any
  other subject is declined `not_covered`. The latest is read from Hermes
  (`latest`), a business date at its close, 17:00 New York (`at`), a valid
  time at that moment. Each constant-maturity tenor Pyth states is a row;
  nothing stated is `source_silent`, and a moment before Hermes holds any is
  `beyond_history`. A standing want is kept current from Hermes' stream.
- the five price families (from 0.2.0; rulings 906 and 990): each subject's
  record read (`ResolveInstrument`) and matched to one feed of the family
  (`feed_of`): by Pyth's feed ID under `pyth_feed_id` where the record
  carries it, else by its code -- a symbol, a ticker or an ISO 4217 code --
  as Pyth's base, priced in the record's currency (a currency's or a
  metal's own record, in US dollars); a subject matched to none is declined
  `not_covered`. The latest is read from Hermes, a business date at the end
  of its UTC day, a valid time at that second; each is recorded as Pyth's
  composite `mid` with its confidence interval (prices.py). A want of a
  kind but `mid` is declined `not_covered`. A standing want is kept current
  from Hermes' stream, each subject's price recorded when it changed and at
  most once a second (`PRICE_PACE_SECONDS`).
- `treasury_prices`: declined `not_covered`, every subject, for the reason
  prices.py states; the reason is said once in the log and always on the
  Datasets page.

**The stream** (Hermes' server-sent events, stream.py): open while any
standing want of `rates` or a price family stands, for exactly the feeds
those wants name, kept open by the SDK's supervisor. Each curve tenor's
value recorded when it changed and at most every five minutes, as the next
version of the day's row (`PACE_SECONDS`); each event the dataset's sign of
life (`Wants.liveness`) at most once a minute.

**Its licences** (contract v20, W10.9): read on start and each minute.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as day_time
from decimal import Decimal
from typing import Any

import meridian
from meridian.errors import NotGranted
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import Wants, rates

from . import curve, prices
from .catalogue import (
    CRYPTO,
    KEYS,
    PRICE_FAMILIES,
    RATES,
    SCHEME,
    TREASURY_PRICES,
    Catalogue,
    PythFeed,
)
from .declared import DAY_END_MINUTE, PRICE
from .hermes import Hermes, HermesError, Update
from .stream import Streamer

log = logging.getLogger(__name__)

#: The catalogue read again, in seconds: daily.
CATALOGUE_EVERY_SECONDS = 86_400
#: A tenor's value recorded from the stream at most this often, in seconds.
PACE_SECONDS = 300
#: A subject's price recorded from the stream at most this often, in seconds.
PRICE_PACE_SECONDS = 1
#: The stream's sign of life recorded at most this often, in seconds.
LIVENESS_EVERY_SECONDS = 60
NS = 1_000_000_000
#: The price families' dataset keys.
PRICE_KEYS = tuple(PRICE_FAMILIES.values())
#: The identifier schemes a record's code is read from, to meet Pyth's base.
CODES = ("symbol", "ticker", "iso4217")

#: Why each dataset not presented declines its wants.
WAITING = {TREASURY_PRICES: prices.WHY_TREASURIES_WAIT}


@dataclass
class Work(data.Role):
    """The data role's class: the plugin's work, its acts made on itself --
    registered on the connection when it runs (`__main__`), bound to the
    suites' recorder in its tests."""

    hermes: Hermes
    clock_ns: Callable[[], int] = time.time_ns
    catalogue: Catalogue = field(default_factory=lambda: Catalogue([]))
    wants: Wants = field(init=False)
    rates: rates.Feed = field(init=False)
    stream: Streamer = field(init=False)
    #: The last value recorded from the stream per tenor's feed, and when.
    paced: dict[str, tuple[int, Decimal, str]] = field(default_factory=dict)
    #: The last price recorded from the stream per subject, and when.
    priced: dict[str, tuple[int, Decimal]] = field(default_factory=dict)
    #: Each dataset's sign of life last recorded, by its key.
    alive_ns: dict[str, int] = field(default_factory=dict)
    #: The par yield curve's record, once resolved; empty before, or missed.
    curve_record: str = ""
    #: The feed each subject of a price family was matched to, by (key,
    #: subject); empty where it matched none.
    feeds_of: dict[tuple[str, str], str] = field(default_factory=dict)
    reads_instruments: bool = True
    said_waiting: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.wants = Wants(self, KEYS, clock_ns=self.clock_ns)
        self.rates = rates.Feed(
            self, curve.SOURCE, wants=self.wants, day_zone="America/New_York",
            clock_ns=self.clock_ns,
        )  # fmt: skip
        self.stream = Streamer(lambda: self.hermes, self.streamed)

    @property
    def latency(self) -> Any:
        return self.wants.latency

    @latency.setter
    def latency(self, value: Any) -> None:
        self.wants.latency = value
        self.stream.latency = value

    def use(self, hermes: Hermes) -> None:
        """Answer from another source -- Hermes, or sample data -- its
        catalogue read again on the next want, the stream opened anew."""
        self.hermes = hermes
        self.catalogue = Catalogue([])
        self.paced.clear()
        self.priced.clear()
        self.stream.restart()

    async def read_licences(self) -> None:
        await self.wants.read_licences()

    # ── The catalogue ───────────────────────────────────────────────────

    async def ensure_catalogue(self) -> Catalogue:
        """The catalogue, read from Hermes where it is not read yet or is a
        day old."""
        now = self.clock_ns()
        if self.catalogue.feeds and now - self.catalogue.read_at_ns < CATALOGUE_EVERY_SECONDS * NS:
            return self.catalogue
        feeds, _ = await asyncio.to_thread(self.hermes.catalogue)
        self.catalogue = Catalogue(feeds, now)
        log.info("Pyth's catalogue read: %s", self.catalogue.counts())
        self.restream()
        return self.catalogue

    def curve_feeds(self) -> list[PythFeed]:
        return self.catalogue.of(RATES)

    async def curve_subject(self) -> str:
        """The par yield curve's record, or empty with the miss reported."""
        self.curve_record = await self.rates.subject(
            curve.CURVE, description=curve.CURVE_DESCRIPTION, instrument_type="rate_curve"
        )
        return self.curve_record

    async def prepare(self) -> None:
        """Once the settings have said where to answer from: Pyth's catalogue
        read (it asks no key) and the curve's record resolved, so the pages
        say both before the first want. A failure is said, and asked again
        on the first want."""
        try:
            await self.ensure_catalogue()
        except HermesError as failed:
            log.warning("Pyth's catalogue was not read: %s", failed)
        try:
            await self.curve_subject()
        except meridian.MeridianError as failed:
            log.warning("the par yield curve's record was not resolved: %s", failed)

    # ── A price family's subjects ───────────────────────────────────────

    def priced_feeds(self, key: str) -> list[PythFeed]:
        """A price family's feeds this version serves: each quoted in a
        currency, not a token Pyth prices as a crypto asset (prices.py)."""
        tokens = {f.base.upper() for f in self.catalogue.of(CRYPTO)}
        return [f for f in self.catalogue.of(key) if prices.quoted_in_a_currency(f, tokens)]

    async def feed_of(self, key: str, subject: str) -> PythFeed | None:
        """The feed of the family `key` a subject's record is, or None: by
        Pyth's feed ID where the record carries it, else by its code as
        Pyth's base, in the record's currency -- US dollars for a currency's
        or a metal's own record, or one stating none. Asked once."""
        if (key, subject) in self.feeds_of:
            return self.catalogue.by_id(self.feeds_of[(key, subject)])
        if not self.reads_instruments:
            return None
        try:
            found = await self.resolve_instrument(instrument_id=subject, as_of_ns=self.clock_ns())
        except NotGranted:
            log.warning("this data plugin may not read an instrument's record")
            self.reads_instruments = False
            return None
        feed = self._matched(key, found.instrument) if found.found else None
        self.feeds_of[(key, subject)] = feed.feed_id if feed is not None else ""
        return feed

    def _matched(self, key: str, record: Any) -> PythFeed | None:
        feeds = self.priced_feeds(key)
        named = {
            i.value.strip().lower().removeprefix("0x")
            for i in record.identifiers
            if i.scheme == SCHEME
        }
        by_id = next((f for f in feeds if f.feed_id in named), None)
        if by_id is not None:
            return by_id
        codes = {i.value.strip().upper() for i in record.identifiers if i.scheme in CODES}
        own = any(i.scheme == "iso4217" for i in record.identifiers)
        currency = "USD" if own or not record.currency else record.currency.upper()
        matched = [f for f in feeds if f.base.upper() in codes and f.quote.upper() == currency]
        return matched[0] if len(matched) == 1 else None

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_observations_wanted(
        self, heard: meridian.Heard[ops.ObservationsWantedEvent]
    ) -> None:
        await self.wants.hear(heard, self.answer)

    async def on_want_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        if self.wants.withdraw(heard.message.want_id) is not None:
            log.info("standing want %s withdrawn", heard.message.want_id)
        self.restream()

    def _moment(self, want: ops.ObservationsWantedEvent) -> int | None:
        """The second a want of `rates` asks about: a business date's close,
        17:00 New York; a valid time; None for the latest."""
        if want.business_date:
            day = datetime.fromisoformat(want.business_date).date()
            close = day_time(DAY_END_MINUTE // 60, DAY_END_MINUTE % 60, tzinfo=curve.NEW_YORK)
            return int(datetime.combine(day, close).timestamp())
        if want.valid_from_ns:
            return int(want.valid_from_ns // NS)
        return None

    def _price_moment(self, want: ops.ObservationsWantedEvent) -> int | None:
        """The second a want of a price asks about: a business date's last
        second, UTC's (the price datasets' day); a valid time; None for the
        latest."""
        if want.business_date:
            day = datetime.fromisoformat(want.business_date).date()
            end = datetime.combine(day + timedelta(days=1), day_time(0, tzinfo=UTC))
            return int(end.timestamp()) - 1
        if want.valid_from_ns:
            return int(want.valid_from_ns // NS)
        return None

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered: its rows recorded against it, and each subject
        declined, with why."""
        if key in WAITING:
            if key not in self.said_waiting:
                self.said_waiting.add(key)
                log.info("wants of %s declined: %s", key, WAITING[key])
            return {s: "not_covered" for s in subjects}
        if key in PRICE_KEYS:
            return await self.answer_prices(want, key, subjects, kinds)
        if key != RATES or want.data_type not in ("", "meridian.v1.Rate"):
            return {s: "not_covered" for s in subjects}
        subject = await self.curve_subject()
        declined = {s: "not_covered" for s in subjects if s != subject}
        if not subject or subject not in subjects:
            return declined
        await self.ensure_catalogue()
        ids = [f.feed_id for f in self.curve_feeds()]
        if not ids:
            declined[subject] = "source_silent"
            return declined
        moment = self._moment(want)
        if moment is not None and moment * NS > self.clock_ns():
            moment = None
        if moment is None:
            updates = await asyncio.to_thread(self.hermes.latest, ids)
        else:
            updates = await asyncio.to_thread(self.hermes.at, moment, ids)
        rows = curve.points(self.rates, subject, RATES, updates, self._by_id())
        if rows:
            await self.rates.record(RATES, rows, want.want_id)
        else:
            declined[subject] = "beyond_history" if moment is not None else "source_silent"
        if want.standing:
            self.wants.stand(want, [subject], kinds)
            self.restream()
        return declined

    async def answer_prices(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """A want of a price family: each subject's feed read at the moment
        asked and its composite mid recorded against the want (prices.py)."""
        if want.data_type not in ("", PRICE) or (kinds and ops.PRICE_KIND_MID not in kinds):
            return {s: "not_covered" for s in subjects}
        await self.ensure_catalogue()
        matched: dict[str, PythFeed] = {}
        declined: dict[str, str] = {}
        for subject in subjects:
            feed = await self.feed_of(key, subject)
            if feed is None:
                declined[subject] = "not_covered"
            else:
                matched[subject] = feed
        if not matched:
            return declined
        ids = sorted({f.feed_id for f in matched.values()})
        moment = self._price_moment(want)
        if moment is not None and moment * NS > self.clock_ns():
            moment = None
        if moment is None:
            updates = await asyncio.to_thread(self.hermes.latest, ids)
        else:
            updates = await asyncio.to_thread(self.hermes.at, moment, ids)
        stated = {update.feed_id: (update, raw_key) for update, raw_key in updates}
        rows = []
        for subject, feed in matched.items():
            got = stated.get(feed.feed_id)
            if got is None:
                declined[subject] = "beyond_history" if moment is not None else "source_silent"
                continue
            rows.append(self._price_row(key, subject, feed, *got))
        if rows:
            await self.wants.record("prices", rows, key, want.want_id)
        if want.standing:
            self.wants.stand(want, list(matched), kinds)
            self.restream()
        return declined

    def _price_row(
        self, key: str, subject: str, feed: PythFeed, update: Update, raw_key: str
    ) -> meridian.Price:
        price = prices.price_of(update, feed, subject, raw_key)
        raw = self.plugin.raw_record(raw_key[:256])
        return prices.row(price, self.wants.dataset(key), raw)

    def _by_id(self) -> dict[str, PythFeed]:
        return {f.feed_id: f for f in self.curve_feeds()}

    # ── The stream ──────────────────────────────────────────────────────

    def streaming_wanted(self) -> bool:
        return bool(self.stream_ids())

    def streamed_subjects(self) -> dict[str, list[tuple[str, str]]]:
        """Each price feed streamed, and the (dataset key, subject) pairs
        its standing wants name."""
        held: dict[str, list[tuple[str, str]]] = {}
        for key in PRICE_KEYS:
            for standing in self.wants.standing_of(key):
                for subject in standing.subjects:
                    feed_id = self.feeds_of.get((key, subject), "")
                    if feed_id and (key, subject) not in held.get(feed_id, []):
                        held.setdefault(feed_id, []).append((key, subject))
        return held

    def stream_ids(self) -> list[str]:
        """The feeds the standing wants name: the curve's while a want of
        `rates` stands, and each price subject's feed."""
        ids = [f.feed_id for f in self.curve_feeds()] if self.wants.standing_of(RATES) else []
        return ids + [i for i in sorted(self.streamed_subjects()) if i not in ids]

    def restream(self) -> None:
        """The stream asked for exactly the feeds wanted now."""
        self.stream.want(self.stream_ids())

    async def streamed(self, events: Sequence[Any]) -> None:
        """What the stream hands on: each event's updates and its raw line."""
        for updates, raw_key in events:
            await self.heard(updates, raw_key)

    async def heard(self, updates: Sequence[Update], raw_key: str) -> int:
        """One event of the stream: each tenor's value recorded where it
        changed and its pace allows, each streamed price likewise, and each
        dataset's sign of life; how many rows were recorded."""
        recorded = await self._curve_heard(updates, raw_key)
        return recorded + await self._prices_heard(updates, raw_key)

    async def _alive(self, key: str, now: int) -> None:
        """A dataset's sign of life, at most once a minute."""
        if now - self.alive_ns.get(key, 0) >= LIVENESS_EVERY_SECONDS * NS:
            self.alive_ns[key] = now
            with contextlib.suppress(meridian.MeridianError):
                await self.wants.liveness(key, now)

    async def _curve_heard(self, updates: Sequence[Update], raw_key: str) -> int:
        by_id = self._by_id()
        if by_id and not any(u.feed_id in by_id for u in updates):
            return 0
        now = self.clock_ns()
        await self._alive(RATES, now)
        subject = await self.curve_subject()
        if not subject:
            return 0
        due: list[tuple[Update, str]] = []
        for update in updates:
            last = self.paced.get(update.feed_id)
            day = curve.business_date(update.published_ns)
            if last is not None:
                at_ns, value, last_day = last
                if value == update.price and last_day == day:
                    continue
                if last_day == day and now - at_ns < PACE_SECONDS * NS:
                    continue
            due.append((update, raw_key))
        rows = curve.points(self.rates, subject, RATES, due, by_id)
        if not rows:
            return 0
        await self.rates.record(RATES, rows)
        for update, _ in due:
            self.paced[update.feed_id] = (
                now,
                update.price,
                curve.business_date(update.published_ns),
            )
        return len(rows)

    async def _prices_heard(self, updates: Sequence[Update], raw_key: str) -> int:
        streamed = self.streamed_subjects()
        if not streamed:
            return 0
        now = self.clock_ns()
        due: dict[str, list[meridian.Price]] = {}
        for update in updates:
            feed = self.catalogue.by_id(update.feed_id)
            if feed is None:
                continue
            for key, subject in streamed.get(update.feed_id, []):
                await self._alive(key, now)
                last = self.priced.get(subject)
                if last is not None and (
                    last[1] == update.price or now - last[0] < PRICE_PACE_SECONDS * NS
                ):
                    continue
                self.priced[subject] = (now, update.price)
                due.setdefault(key, []).append(self._price_row(key, subject, feed, update, raw_key))
        recorded = 0
        for key, rows in due.items():
            recorded += await self.wants.record("prices", rows, key)
        return recorded
