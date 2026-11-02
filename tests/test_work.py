"""The work: what the lake wants answered from Hermes, the curve's points as
rates, the price families' composite mids, the on-the-run Treasuries
declined while they wait, and the stream kept and paced."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard

from pyth.hermes import read_updates
from pyth.synthetic import Synthetic
from pyth.work import PACE_SECONDS

from conftest import AAPL, BRENT, BTC, EUR, PAR, Clock, Sample, ids_of, lake, want, work

PRICE = "meridian.v1.Price"

DAY = "2026-10-29"


def _events() -> list[str]:
    return [line[5:] for line in Synthetic().events if line.startswith("data:")]


async def test_the_latest_curve_is_recorded_against_the_par_curve(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    await done.on_observations_wanted(want("w-1", [PAR]))
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
    await done.on_observations_wanted(want("w-1", [PAR], day=DAY))
    # 17:00 New York on 29 October 2026 is 21:00 UTC.
    assert any("/v2/updates/price/1793307600?" in url for url in sample.requests)


async def test_the_on_the_run_treasuries_wait_and_call_nothing(tmp_path: Path) -> None:
    held = lake()
    sample = Sample()
    done = work(tmp_path, held, sample)
    await done.on_observations_wanted(
        want("w-1", ["INS-1"], key="treasury_prices", data_type=PRICE)
    )
    [declined] = held.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_NOT_COVERED
    assert not held.on("RecordPrices") and not sample.requests


async def test_a_price_is_the_composite_mid_with_its_confidence(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    await done.on_observations_wanted(want("w-1", [BTC], key="crypto", data_type=PRICE))
    [batch] = held.on("RecordPrices")
    assert batch.want_id == "w-1"
    [price] = batch.prices
    assert price.kind == ops.PRICE_KIND_MID and price.basis == ops.PRICE_BASIS_PER_UNIT
    # Exactly as Hermes states it: "6812345678901" and "2345678901" at -8.
    assert as_decimal(price.price.amount) == Decimal("68123.45678901")
    assert price.price.currency_code == "USD"
    assert as_decimal(price.confidence) == Decimal("23.45678901")
    assert price.meta.subjects[0].entity_id == BTC
    assert price.meta.source.dataset == "pyth:crypto"
    assert price.meta.business_date == "2026-10-30"
    published = [t for t in price.meta.source_times if t.kind == ops.SOURCE_TIME_KIND_PUBLISHED]
    assert published[0].at_ns == price.meta.valid_from_ns == 1_793_386_800 * 10**9
    assert price.meta.row_key == f"pyth:mid:{BTC}:1793386800" and price.meta.raw.key


async def test_each_family_matches_its_records_by_code_or_feed_id(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    for key, subject in (("fx", EUR), ("equity", AAPL), ("commodities", BRENT)):
        await done.on_observations_wanted(want(f"w-{key}", [subject], key=key, data_type=PRICE))
    stated = {p.meta.subjects[0].entity_id: p for b in held.on("RecordPrices") for p in b.prices}
    assert as_decimal(stated[EUR].price.amount) == Decimal("1.16431")
    assert as_decimal(stated[AAPL].price.amount) == Decimal("231.04500")
    assert as_decimal(stated[BRENT].price.amount) == Decimal("73.12345")
    assert not held.on("DeclineWant")


async def test_a_price_not_matched_or_not_mid_is_not_covered(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    # Bitcoin's record is no equity; a close is no kind Pyth states.
    await done.on_observations_wanted(want("w-1", [BTC], key="equity", data_type=PRICE))
    close = want("w-2", [BTC], key="crypto", data_type=PRICE)
    close.message.kinds.append(ops.PRICE_KIND_CLOSE)
    await done.on_observations_wanted(close)
    declined = held.on("DeclineWant")
    assert [d.reason for d in declined] == [ops.UNANSWERED_REASON_NOT_COVERED] * 2
    assert not held.on("RecordPrices")


async def test_a_crypto_feed_quoted_in_a_token_is_not_served(tmp_path: Path) -> None:
    done = work(tmp_path)
    await done.ensure_catalogue()
    served = {f.symbol for f in done.priced_feeds("crypto")}
    assert "Crypto.BTC/USD" in served and "Crypto.ETH/BTC" not in served


async def test_a_business_dates_price_is_read_at_its_last_second(tmp_path: Path) -> None:
    sample = Sample()
    held = lake()
    done = work(tmp_path, held, sample)
    await done.on_observations_wanted(want("w-1", [BTC], key="crypto", data_type=PRICE, day=DAY))
    # 23:59:59 UTC on 29 October 2026.
    assert any("/v2/updates/price/1793318399?" in url for url in sample.requests)
    [price] = held.on("RecordPrices")[0].prices
    assert price.meta.business_date == DAY


async def test_another_subject_is_not_covered(tmp_path: Path) -> None:
    held = lake()
    await work(tmp_path, held).on_observations_wanted(want("w-1", ["INS-SOFR"]))
    [declined] = held.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_NOT_COVERED
    assert not held.on("RecordRates")


async def test_a_refused_key_declines_and_says_why(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held, Sample(status=401))
    await done.on_observations_wanted(want("w-1", [PAR]))
    [declined] = held.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_SOURCE_SILENT
    assert "Pyth API key" in done.hermes.health.last_error


async def test_a_standing_want_is_kept_current_from_the_stream_at_its_pace(
    tmp_path: Path,
) -> None:
    held = lake()
    clock = Clock()
    done = work(tmp_path, held, clock=clock)
    await done.on_observations_wanted(want("w-standing", [PAR], standing=True))
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
    await done.on_want_withdrawn(_withdrawn("w-standing"))
    assert not done.streaming_wanted()


def _withdrawn(want_id: str) -> Heard[ops.WantWithdrawnEvent]:
    return Heard(
        row="WantWithdrawn",
        message=ops.WantWithdrawnEvent(want_id=want_id, dataset="pyth:rates"),
    )


async def test_the_stream_runs_while_wanted(tmp_path: Path) -> None:
    held = lake()
    done = work(tmp_path, held)
    await done.on_observations_wanted(want("w-standing", [PAR], standing=True))
    assert len(done.stream.wanted) == 7
    # The SDK's supervisor (0.35): one session, the sample's three events.
    await done.stream.run(once=True)
    assert done.stream.state.messages == 3 and done.stream.state.opened == 1
    # The first event's seven points, after the want's own seven.
    assert sum(len(b.rates) for b in held.on("RecordRates")) == 14


async def test_a_standing_price_is_kept_current_from_the_stream(tmp_path: Path) -> None:
    held = lake()
    clock = Clock()
    done = work(tmp_path, held, clock=clock)
    await done.on_observations_wanted(
        want("w-btc", [BTC], key="crypto", data_type=PRICE, standing=True)
    )
    btc = ids_of("Crypto.BTC/USD")[0].removeprefix("0x")
    assert done.stream.wanted == (btc,)
    first, second, third = ([u for u in read_updates(e) if u.feed_id == btc] for e in _events())
    # The first event repeats the price the want recorded: unchanged, but
    # the first the stream states, so recorded; the second moved; the third
    # states the second's again.
    assert await done.heard(first, "k#0") == 1
    clock.advance(60)
    assert await done.heard(second, "k#1") == 1
    clock.advance(60)
    assert await done.heard(third, "k#2") == 0
    streamed = [p for b in held.on("RecordPrices")[1:] for p in b.prices]
    assert [as_decimal(p.price.amount) for p in streamed] == [
        Decimal("68123.45678901"),
        Decimal("68135.80178901"),
    ]
    assert all(b.want_id == "" for b in held.on("RecordPrices")[1:])
    liveness = [r.dataset for b in held.on("RecordLiveness") for r in b.liveness]
    assert liveness == ["pyth:crypto"] * 3
    await done.on_want_withdrawn(_withdrawn("w-btc"))
    assert not done.stream.wanted
