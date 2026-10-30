"""The catalogue, from code, as the deployment approves it: one dataset per
family Pyth publishes (rulings 893 to 898)."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from pyth.declaration import DECLARATION
from pyth.declared import CATALOGUE, VENDOR


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
    for key in ("crypto", "fx", "equity", "metal", "commodities", "treasury_prices"):
        assert list(by_key[key].data_types) == ["meridian.v1.Price"]
    assert list(by_key["rates"].data_types) == ["meridian.v1.Rate"]
    streamed = [ops.ObservationMode.Name(m) for m in by_key["rates"].modes]
    assert streamed == ["OBSERVATION_MODE_PULL", "OBSERVATION_MODE_STREAM"]
    assert by_key["rates"].day_time_zone == "America/New_York"
    assert by_key["rates"].day_end_minute == 17 * 60


def test_each_licence_is_pyths_subscription_terms() -> None:
    for dataset in CATALOGUE:
        licence = dataset.licence_default
        assert licence is not None
        assert licence.kept and licence.display and not licence.personal_use
        assert licence.derived_use_terms == "not_restricted"
        assert licence.redistribution == "not_allowed"
        assert "not affiliated" in licence.not_affiliated_notice


def test_the_key_is_a_secret_setting() -> None:
    assert DECLARATION.secret_settings == ["api_key"]
    declared = {s.name: s for s in DECLARATION.settings}
    assert declared["api_key"].secret and not declared["api_key"].required
    assert declared["sample_data"].developer
    assert [s.name for s in DECLARATION.settings] == ["api_key", "sample_data"]


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
