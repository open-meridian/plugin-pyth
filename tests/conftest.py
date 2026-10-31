"""Shared stand-ins: Hermes answered from the sample data and the answers
recorded for the tests, a clock a test moves, the deployment's par yield
curve record as the platform seeds it, and the lake's wants as the sidecar
delivers them."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.edge import RawStore
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Instruments, Lake
from meridian.suites import Recorder

from pyth import curve
from pyth.hermes import Hermes
from pyth.synthetic import Synthetic
from pyth.work import Work

INSTANCE = "pyth"
#: Friday 30 October 2026, 15:00 New York: the sample's latest update.
AT = datetime(2026, 10, 30, 19, 0, tzinfo=UTC)
#: The par yield curve's record, as the platform seeds it.
PAR = "INS-UST-PAR"


def held(store: Instruments) -> Instruments:
    store.hold(
        PAR,
        ops.Identifier(scheme=curve.CURVE[0], value=curve.CURVE[1], source=curve.CURVE[2]),
        asset_class=ops.ASSET_CLASS_REFERENTIAL,
        instrument_type=ops.INSTRUMENT_TYPE_RATE_CURVE,
    )
    return store


def answering(recorder: Recorder) -> Recorder:
    """A suite recorder answering resolves from the curve's record."""
    held(Instruments().answering(recorder))
    return recorder


def lake() -> Lake:
    """The lake as a test stands it in, holding the curve's record."""
    made = Lake(INSTANCE)
    held(made.instruments)
    return made


class Clock:
    """A clock a test moves, in nanoseconds."""

    def __init__(self, at: datetime = AT) -> None:
        self.ns = int(at.timestamp()) * 1_000_000_000

    def __call__(self) -> int:
        return self.ns

    def advance(self, seconds: int) -> None:
        self.ns += seconds * 1_000_000_000


class Sample(Synthetic):
    """The sample data, with what a test changes: feeds whose updates it
    leaves out, and the HTTP status every price answers."""

    def __init__(self, leave_out: tuple[str, ...] = (), status: int = 200) -> None:
        super().__init__()
        for feed_id in leave_out:
            self.latest.pop(feed_id, None)
        self.status = status
        self.headers: list[dict[str, str]] = []

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]:
        self.headers.append(dict(headers))
        if self.status != 200 and "/updates/" in url:
            self.requests.append(url)
            return self.status, "unauthorized", {}
        return super().get(url, headers)


def work(tmp: Path, plugin: Any = None, transport: Any = None, clock: Any = None) -> Work:
    """The plugin's work on the lake as a test stands it in and the sample
    data."""
    hermes = Hermes(RawStore(tmp), transport or Sample(), "synthetic")
    return Work(plugin if plugin is not None else lake(), hermes, clock_ns=clock or Clock())


def ids_of(symbol_prefix: str) -> list[str]:
    feeds = json.loads(Synthetic().catalogue)
    return [f["id"] for f in feeds if f["attributes"]["symbol"].startswith(symbol_prefix)]


def want(
    want_id: str,
    subjects: list[str],
    *,
    key: str = "rates",
    day: str = "",
    standing: bool = False,
    data_type: str = "meridian.v1.Rate",
    valid_from_ns: int = 0,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=f"{INSTANCE}:{key}",
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
            standing=standing,
            valid_from_ns=valid_from_ns,
        ),
    )
