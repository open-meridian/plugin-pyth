"""The data suite (meridian.suites) at contract v28, each case Pyth presents
mapped to the plugin's own work on Hermes' answers -- the feed catalogue as
Hermes answered it, and updates in Hermes' documented shape.

Presented, all about the `rates` dataset, Pyth's constant-maturity par
yields as points of the US Treasury par yield curve:

- `a-curve-for-a-date`: a business date's curve, read at its close;
- `a-tenor-not-published`: the same with the 30-year left out by Hermes --
  no row, never a zero;
- `a-curve-point-from-another-source`: each point recorded against
  Treasury's curve record, which Treasury's own plugin records too;
- `a-same-day-revision`: a tenor's new value from the stream, later the same
  day, the next version of the day's row;
- `records-a-datasets-liveness`: the stream's events, the dataset's sign of
  life;
- `an-asset-that-does-not-resolve`, the wants, the licences, the feed delay,
  and the cases the SDK answers.

Not presented, with why: every case about a price (`closes`, `bars`, a
currency's rate, a crypto asset's or a security's price, prices on a
venue), since Pyth's composite price waits for the contract-28 amendment
(prices.py); trades and quotes, which Hermes never states; outcomes, chains
and filings; a reference rate's fixing (Hermes states no effective date), an
index level and two conventions for one tenor, which Pyth never states; a
calendar and a settlement date, which it never needs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import RATES_NOT_PRESENTED, feed_delay
from meridian.suites import ANSWERED_BY_SDK, Recorder, run

from pyth import prices
from pyth.hermes import read_updates
from pyth.synthetic import Synthetic

from conftest import INSTANCE, PAR, Clock, Sample, answering, ids_of, want, work

#: The cases about a price, each waiting for the amendment.
_PRICES = (
    "a-daily-close", "the-forming-day-restated", "an-exact-price", "a-daily-bar",
    "an-fx-rate", "a-stablecoin-quote", "a-venue-resolved", "a-venue-not-held",
    "a-want-recorded-against", "a-subject-another-source-resolved",
)  # fmt: skip
PYTH_NEVER = {
    **{case: prices.WHY_PRICES_WAIT for case in _PRICES},
    "a-rate-fixing": (
        "the reference rates Pyth relays carry no effective date in Hermes, which a fixing's "
        "row needs; the administrator's own plugin records them"
    ),
    "an-index-level": "Pyth publishes no index level of a rate",
    "two-conventions-one-tenor": "Pyth states one convention for each tenor, a par yield",
    "reads-a-calendar": "its datasets declare no calendar; it records what Pyth publishes",
    "asks-for-a-settlement-date": "it records values as published; never a settlement date",
}
#: Trades, quotes, outcomes, chains and filings, as the SDK names a
#: rates-only plugin's (ruling 538); then Pyth's own.
NOT_PRESENTED = {
    **{k: v for k, v in RATES_NOT_PRESENTED.items() if k not in _PRICES},
    **PYTH_NEVER,
}
PRESENTED = {
    "a-curve-for-a-date", "a-tenor-not-published", "a-curve-point-from-another-source",
    "a-same-day-revision", "records-a-datasets-liveness", "an-asset-that-does-not-resolve",
    "a-subject-declined", "a-standing-want-withdrawn", "reads-its-datasets-licences",
    "reports-its-feed-delay",
}  # fmt: skip

DAY = "2026-10-29"


def _events() -> list[str]:
    return [line[5:] for line in Synthetic().events if line.startswith("data:")]


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    def wanted(message: Any, transport: Any = None) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            answering(recorder)
            done = work(tmp, recorder, transport)
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.receive(observations_wanted=done.on_want)

        return produce

    async def revised(recorder: Recorder) -> None:
        answering(recorder)
        clock = Clock()
        done = work(tmp, recorder, clock=clock)
        await done.ensure_catalogue()
        first, _, third = _events()
        await done.heard(read_updates(first), "responses/x#0")
        clock.advance(600)
        await done.heard(read_updates(third), "responses/x#2")

    async def alive(recorder: Recorder) -> None:
        answering(recorder)
        done = work(tmp, recorder)
        await done.ensure_catalogue()
        await done.heard(read_updates(_events()[0]), "responses/x#0")

    async def two_records(recorder: Recorder) -> None:
        recorder.answer(
            "ResolveIdentifier",
            lambda _: ops.ResolveIdentifierResult(
                found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS
            ),
        )
        done = work(tmp, recorder)
        await done.curve_subject()

    async def withdrawn(recorder: Recorder) -> None:
        done = work(tmp, recorder)
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=f"{INSTANCE}:rates"),
        )
        await recorder.receive(want_withdrawn=done.on_withdrawn)

    async def licences(recorder: Recorder) -> None:
        dataset = f"{INSTANCE}:rates"
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=dataset)]),
        )
        done = work(tmp, recorder)
        await done.read_licences()
        assert done.wants.licensed == {dataset}

    async def delayed(recorder: Recorder, latency: Any) -> None:
        # The stream's events recorded unasked, each value's age at the
        # edge -- when it was read, less Pyth's published time -- recorded.
        answering(recorder)
        done = work(tmp, recorder)
        done.latency = latency
        await done.ensure_catalogue()
        await done.heard(read_updates(_events()[0]), "responses/x#0")

    thirty = ids_of("InterestRate.Index.CMUS30Y")
    return {
        "a-curve-for-a-date": wanted(want("w-1", [PAR], day=DAY).message),
        "a-tenor-not-published": wanted(
            want("w-1", [PAR], day=DAY).message, Sample(leave_out=tuple(thirty))
        ),
        "a-curve-point-from-another-source": wanted(want("w-1", [PAR]).message),
        "a-same-day-revision": revised,
        "records-a-datasets-liveness": alive,
        "an-asset-that-does-not-resolve": two_records,
        "a-subject-declined": wanted(want("w-2", ["INS-SOFR"], day=DAY).message),
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
        "reports-its-feed-delay": feed_delay(delayed),
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id=INSTANCE)
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    assert set(report.passed_cases) == PRESENTED | set(ANSWERED_BY_SDK)


def test_every_price_case_waits_for_the_amendment() -> None:
    for case in _PRICES:
        assert NOT_PRESENTED[case] == prices.WHY_PRICES_WAIT
    assert not prices.presented()
