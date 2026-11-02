"""Hermes' stream on the SDK's supervisor (0.2.0): a session for exactly the
feeds wanted, a 429's Retry-After kept for the next wait, a refused key
waited out, and other feeds wanted opening a new session."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from meridian.edge import RawStore

from pyth.hermes import Hermes, HermesError
from pyth.stream import HermesLink, Refused, RetryAfter, Streamer

from conftest import Sample, ids_of


class Refusing(Sample):
    """Hermes refusing the stream with `status`, a Retry-After of 7 s."""

    def __init__(self, status: int) -> None:
        super().__init__()
        self.status_said = status

    def lines(self, url: str, headers: dict[str, str]) -> Iterator[str]:
        raise HermesError(self.status_said, f"refused ({self.status_said})", 7.0)
        yield ""  # pragma: no cover - a generator


def hermes(tmp: Path, transport: Any = None) -> Hermes:
    return Hermes(RawStore(tmp), transport or Sample(), "synthetic")


async def test_a_429_keeps_its_retry_after_for_the_next_wait(tmp_path: Path) -> None:
    backoff = RetryAfter(first_s=1, most_s=60, jitter=0.0)
    link = HermesLink(hermes(tmp_path, Refusing(429)), backoff)
    await link.subscribe(ids_of("Crypto.BTC/USD"))
    with pytest.raises(HermesError):
        await link.receive()
    assert backoff.asked == 7.0 and backoff.failed() == 7.0


async def test_a_refused_key_is_waited_out(tmp_path: Path) -> None:
    link = HermesLink(hermes(tmp_path, Refusing(401)), RetryAfter())
    await link.subscribe(ids_of("Crypto.BTC/USD"))
    with pytest.raises(Refused):
        await link.receive()

    async def nothing(_: Any) -> None:
        pass

    streamer = Streamer(lambda: hermes(tmp_path, Refusing(403)), nothing)
    streamer.want(ids_of("Crypto.BTC/USD"))
    await streamer.run(once=True)
    assert streamer.state.state == "refused" and "403" in streamer.state.last_error


async def test_a_session_carries_only_the_feeds_wanted(tmp_path: Path) -> None:
    sample = Sample()
    heard: list[Any] = []

    async def hear(events: list[Any]) -> None:
        heard.extend(events)

    btc = ids_of("Crypto.BTC/USD")
    streamer = Streamer(lambda: hermes(tmp_path, sample), hear)
    streamer.want(btc)
    await streamer.run(once=True)
    assert len(heard) == 3
    assert {u.feed_id for updates, _ in heard for u in updates} == set(btc)
    assert [u for u in sample.requests if "/stream" in u] and "EOFError" in (
        streamer.state.last_error
    )
