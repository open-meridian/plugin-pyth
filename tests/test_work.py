"""The work: what the lake wants answered from Hermes, the curve's points as
rates, the price families declined while they wait, and the stream kept and
paced."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard

from pyth import prices
from pyth.hermes import read_updates
from pyth.synthetic import Synthetic
from pyth.work import PACE_SECONDS

from conftest import PAR, Clock, Sample, lake, want, work

DAY = "2026-10-29"


def _events() -> list[str]:
    return [line[5:] for line in Synthetic().events if line.startswith("data:")]


async def test_the_latest_curve_is_recorded_against_the_par_curve(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    await done.on_want(want("w-1", [PAR]))
    [batch] = held.on("RecordRates")
    assert batch.want_id == "w-1"
    rows = batch.rates
    assert {r.tenor.count for r in rows} == {2, 3, 5, 7, 10, 20, 30}
    ten = next(r for r in rows if r.tenor.count == 10)
    assert ten.kind == ops.RATE_KIND_PAR_YIELD
    assert ten.meta.subjects[0].entity_id == PAR
    assert ten.meta.business_date == "2026-10-30"
    # Exactly as Hermes states it: "411234567" at exponent -8, a percent.
    assert as_decimal(ten.value.value) == Decimal("4.11234567")
    assert ten.value.unit == ops.VALUE_UNIT_PERCENT
    assert ten.convention.compounding
    published = [t for t in ten.meta.source_times if t.kind == ops.SOURCE_TIME_KIND_PUBLISHED]
    assert published[0].at_ns == 1_793_386_800 * 10**9
    assert ten.meta.row_key.startswith("pyth:par_yield:10Y:")
    assert ten.meta.raw.key


async def test_a_business_date_is_read_at_its_close(tmp_path: Path) -> None:
    sample = Sample()
    done = work(tmp_path, transport=sample)
    await done.on_want(want("w-1", [PAR], day=DAY))
    # 17:00 New York on 29 October 2026 is 21:00 UTC.
    assert any("/v2/updates/price/1793307600?" in url for url in sample.requests)


async def test_the_price_families_wait_and_call_nothing(tmp_path: Path) -> None:
    held = lake()
    sample = Sample()
    done = work(tmp_path, held, sample)
    for key in ("crypto", "fx", "equity", "metal", "commodities", "treasury_prices"):
        await done.on_want(want(f"w-{key}", ["INS-1"], key=key, data_type="meridian.v1.Price"))
    declined = held.on("DeclineWant")
    assert len(declined) == 6
    assert {d.reason for d in declined} == {ops.UNANSWERED_REASON_NOT_COVERED}
    assert not held.on("RecordPrices") and not sample.requests
    assert not prices.presented()


async def test_another_subject_is_not_covered(tmp_path: Path) -> None:
    held = lake()
    await work(tmp_path, held).on_want(want("w-1", ["INS-SOFR"]))
    [declined] = held.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_NOT_COVERED
    assert not held.on("RecordRates")


async def test_a_refused_key_declines_and_says_why(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held, Sample(status=401))
    await done.on_want(want("w-1", [PAR]))
    [declined] = held.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_SOURCE_SILENT
    assert "Pyth API key" in done.hermes.health.last_error


async def test_a_standing_want_is_kept_current_from_the_stream_at_its_pace(
    tmp_path: Path,
) -> None:
    held = lake()
    clock = Clock()
    done = work(tmp_path, held, clock=clock)
    await done.on_want(want("w-standing", [PAR], standing=True))
    assert done.streaming_wanted()
    first, second, third = (read_updates(e) for e in _events())
    assert await done.heard(first, "k#0") == 7
    clock.advance(60)
    # Within the pace: nothing recorded, though the values moved.
    assert await done.heard(second, "k#1") == 0
    clock.advance(PACE_SECONDS)
    assert await done.heard(third, "k#2") == 7
    # The dataset's sign of life, once a minute at most: each of the three.
    assert len(held.on("RecordLiveness")) == 3
    await done.on_withdrawn(_withdrawn("w-standing"))
    assert not done.streaming_wanted()


def _withdrawn(want_id: str) -> Heard[ops.WantWithdrawnEvent]:
    return Heard(
        row="WantWithdrawn",
        message=ops.WantWithdrawnEvent(want_id=want_id, dataset="pyth:rates"),
    )


async def test_the_stream_runs_while_wanted(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    await done.on_want(want("w-standing", [PAR], standing=True))
    await done._run_stream([f.feed_id for f in done.curve_feeds()])
    assert done.stream.events == 3 and done.stream.opened == 1
    # The first event's seven points, after the want's own seven.
    assert sum(len(b.rates) for b in held.on("RecordRates")) == 14
