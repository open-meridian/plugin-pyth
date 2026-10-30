"""The data plugin's work (the role `data`): Pyth's values into the lake,
converted at the edge, through the SDK's `Wants` and `rates.Feed`.

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
- the five price families and `treasury_prices`: declined `not_covered`,
  every subject, for the reason prices.py states; the reason is said once
  in the log and always on the Datasets page.

**The stream** (Hermes' server-sent events): open while any standing want
of `rates` stands, for the curve's feeds alone; each tenor's value recorded
when it changed and at most every five minutes, as the next version of the
day's row (`PACE_SECONDS`); each event the dataset's sign of life
(`Wants.liveness`) at most once a minute. A stream that ends or fails is
opened again after a pause that grows to a minute, with jitter, and is
never shorter than a 429's `Retry-After`.

**Its licences** (contract v20, W10.9): read on start and each minute.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as day_time
from decimal import Decimal
from typing import Any

import meridian
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data import Wants, rates

from . import curve, prices
from .catalogue import KEYS, PRICE_FAMILIES, RATES, TREASURY_PRICES, Catalogue, PythFeed
from .declared import DAY_END_MINUTE
from .hermes import Hermes, HermesError, Update

log = logging.getLogger(__name__)

#: The catalogue read again, in seconds: daily.
CATALOGUE_EVERY_SECONDS = 86_400
#: A tenor's value recorded from the stream at most this often, in seconds.
PACE_SECONDS = 300
#: The stream's sign of life recorded at most this often, in seconds.
LIVENESS_EVERY_SECONDS = 60
#: A failed stream opened again after this pause, doubling to the most.
RETRY_FIRST_SECONDS = 2
RETRY_MOST_SECONDS = 60
NS = 1_000_000_000


def stream_pause(pause: float, rand: Callable[[], float] = random.random) -> float:
    """The pause before the stream is opened again: `pause` and up to half
    as much again (jitter), so it is never shorter than a `Retry-After`."""
    return pause + rand() * pause / 2


#: Why each dataset not presented declines its wants.
WAITING = {
    **{key: prices.WHY_PRICES_WAIT for key in PRICE_FAMILIES.values()},
    TREASURY_PRICES: prices.WHY_TREASURIES_WAIT,
}

Plugin = Any  # meridian.Plugin, or the suite's Recorder: the SDK's typed operations


@dataclass
class Stream:
    """How the stream is going, for the Connection page."""

    open: bool = False
    opened: int = 0
    events: int = 0
    last_event_ns: int = 0
    error: str = ""


@dataclass
class Work:
    """The plugin's work against whatever operations it is given: the
    plugin's own when it runs, a recorder's in its tests."""

    plugin: Plugin
    hermes: Hermes
    clock_ns: Callable[[], int] = time.time_ns
    catalogue: Catalogue = field(default_factory=lambda: Catalogue([]))
    stream: Stream = field(default_factory=Stream)
    wants: Wants = field(init=False)
    rates: rates.Feed = field(init=False)
    #: The last value recorded from the stream per tenor's feed, and when.
    paced: dict[str, tuple[int, Decimal, str]] = field(default_factory=dict)
    alive_ns: int = 0
    #: The par yield curve's record, once resolved; empty before, or missed.
    curve_record: str = ""
    said_waiting: set[str] = field(default_factory=set)
    wake: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.wants = Wants(self.plugin, KEYS, clock_ns=self.clock_ns)
        self.rates = rates.Feed(
            self.plugin, curve.SOURCE, wants=self.wants, day_zone="America/New_York",
            clock_ns=self.clock_ns,
        )  # fmt: skip

    @property
    def latency(self) -> Any:
        return self.wants.latency

    @latency.setter
    def latency(self, value: Any) -> None:
        self.wants.latency = value

    def use(self, hermes: Hermes) -> None:
        """Answer from another source -- Hermes, or sample data -- its
        catalogue read again on the next want."""
        self.hermes = hermes
        self.catalogue = Catalogue([])
        self.paced.clear()
        self.wake.set()

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

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_want(self, heard: meridian.Heard[ops.ObservationsWantedEvent]) -> None:
        await self.wants.hear(heard, self.answer)

    async def on_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        if self.wants.withdraw(heard.message.want_id) is not None:
            log.info("standing want %s withdrawn", heard.message.want_id)
        self.wake.set()

    def _moment(self, want: ops.ObservationsWantedEvent) -> int | None:
        """The second a want asks about: a business date's close, 17:00 New
        York; a valid time; None for the latest."""
        if want.business_date:
            day = datetime.fromisoformat(want.business_date).date()
            close = day_time(DAY_END_MINUTE // 60, DAY_END_MINUTE % 60, tzinfo=curve.NEW_YORK)
            return int(datetime.combine(day, close).timestamp())
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
            self.wake.set()
        return declined

    def _by_id(self) -> dict[str, PythFeed]:
        return {f.feed_id: f for f in self.curve_feeds()}

    # ── The stream ──────────────────────────────────────────────────────

    def streaming_wanted(self) -> bool:
        return bool(self.wants.standing_of(RATES))

    async def heard(self, updates: Sequence[Update], raw_key: str) -> int:
        """One event of the stream: each tenor's value recorded where it
        changed and its pace allows, and the dataset's sign of life; how many
        rows were recorded."""
        now = self.clock_ns()
        self.stream.events += 1
        self.stream.last_event_ns = now
        if now - self.alive_ns >= LIVENESS_EVERY_SECONDS * NS:
            self.alive_ns = now
            with contextlib.suppress(meridian.MeridianError):
                await self.wants.liveness(RATES, now)
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
        rows = curve.points(self.rates, subject, RATES, due, self._by_id())
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

    async def keep_streaming(self) -> None:
        """Hermes' stream of the curve's feeds, open while a standing want of
        `rates` stands; opened again after a pause where it ends or fails."""
        pause: float = RETRY_FIRST_SECONDS
        while True:
            if not self.streaming_wanted():
                self.wake.clear()
                await self.wake.wait()
                continue
            try:
                await self.ensure_catalogue()
                ids = [f.feed_id for f in self.curve_feeds()]
                if ids:
                    await self._run_stream(ids)
                    pause = RETRY_FIRST_SECONDS
            except (HermesError, meridian.MeridianError, OSError) as failed:
                self.stream.error = str(failed)
                log.warning("the stream stopped: %s", failed)
                asked = failed.retry_after if isinstance(failed, HermesError) else None
                if asked is not None:
                    pause = max(pause, min(asked, RETRY_MOST_SECONDS))
            self.stream.open = False
            await asyncio.sleep(stream_pause(pause))
            pause = min(pause * 2, RETRY_MOST_SECONDS)

    async def _run_stream(self, ids: list[str]) -> None:
        events: Iterator[tuple[list[Update], str]] = self.hermes.stream(ids)
        self.stream.open = True
        self.stream.opened += 1
        self.stream.error = ""
        try:
            while self.streaming_wanted():
                event = await asyncio.to_thread(next, events, None)
                if event is None:
                    return
                updates, raw_key = event
                await self.heard(updates, raw_key)
        finally:
            close = getattr(events, "close", None)
            if close is not None:
                close()
