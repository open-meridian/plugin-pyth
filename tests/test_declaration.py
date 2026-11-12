"""The catalogue, from code, as the deployment approves it: one dataset per
family Pyth publishes (rulings 893 to 898, 906)."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from pyth.declaration import DECLARATION
from pyth.declared import CATALOGUE, TERMS, TREASURY_TERMS, VENDOR


def test_seven_datasets_one_per_family() -> None:
    assert [d.key for d in DECLARATION.catalogue] == [
        "crypto", "fx", "equity", "metal", "commodities", "rates", "treasury_prices",
    ]  # fmt: skip
    for dataset in CATALOGUE:
        assert dataset.vendor == VENDOR == "Pyth Network"
        # Pyth is no venue and computes its composite itself: no aggregator.
        assert not dataset.venue_id and not dataset.aggregator and not dataset.calendar_id
        assert dataset.declared_delay_ns == 0


def test_prices_and_rates_by_their_kinds() -> None:
    by_key = {d.key: d for d in CATALOGUE}
    # From 0.2.0 (ruling 906): each price family's a composite mid with its
    # confidence interval; the on-the-run Treasuries a composite too.
    for key in ("crypto", "fx", "equity", "metal", "commodities"):
        assert list(by_key[key].data_types) == ["meridian.v1.Price", "meridian.v1.Price.confidence"]
        assert by_key[key].price_source_class == "composite"
    assert list(by_key["treasury_prices"].data_types) == ["meridian.v1.Price"]
    assert by_key["treasury_prices"].price_source_class == "composite"
    assert list(by_key["rates"].data_types) == ["meridian.v1.Rate"]
    assert not by_key["rates"].price_source_class
    streamed = [ops.ObservationMode.Name(m) for m in by_key["rates"].modes]
    assert streamed == ["OBSERVATION_MODE_PULL", "OBSERVATION_MODE_STREAM"]
    assert by_key["rates"].day_time_zone == "America/New_York"
    assert by_key["rates"].day_end_minute == 17 * 60


def test_each_dataset_describes_pyths_terms_and_how_a_gap_is_recovered() -> None:
    # Contract 30 (ruling 1032): Pyth's terms in words, no licence; the
    # Treasury datasets name the publishers Pyth names (ruling 1039).
    by_key = {d.key: d for d in CATALOGUE}
    for dataset in CATALOGUE:
        said = dataset.terms_and_pricing
        assert said in (TERMS, TREASURY_TERMS) and len(said) <= 2000
        assert "redistribution are not allowed" in said and "not affiliated" in said
        assert not dataset.sessions_calendar_id
    assert by_key["rates"].terms_and_pricing == TREASURY_TERMS
    assert "Tradeweb" in TREASURY_TERMS
    recovery = {d.key: d.gap_recovery for d in CATALOGUE}
    assert recovery.pop("rates") == "backfill", "a day's curve read again at its close"
    assert recovery.pop("treasury_prices") == "none", "it records nothing yet"
    assert set(recovery.values()) == {"stream_only"}, "Hermes answers a moment, not a range"


def test_the_key_is_a_secret_setting() -> None:
    assert DECLARATION.secret_settings == ["api_key"]
    declared = {s.name: s for s in DECLARATION.settings}
    assert declared["api_key"].secret and not declared["api_key"].required
    assert declared["sample_data"].developer
    assert [s.name for s in DECLARATION.settings] == ["api_key", "sample_data"]


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
