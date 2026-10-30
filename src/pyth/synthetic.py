"""Sample data: Hermes answered from files committed with the plugin, so it
runs, and is tested, with no Pyth API key and nothing called.

- `synthetic/price_feeds.json`: Pyth's feed catalogue as Hermes answered
  `/v2/price_feeds` on 2026-10-30 (no key asked), the array cut to the
  feeds below: a few of each family, every constant-maturity par yield and
  its discount factor, two on-the-run Treasuries, SOFR, and two kinds no
  dataset holds. Each entry is as Pyth sent it.
- `synthetic/updates.json`: a made-up latest update for each of those feeds,
  in Hermes' documented shape (`price`, `conf`, `expo`, `publish_time`) --
  never Pyth's prices. A price at a past moment is the same values,
  published at that moment.
- `synthetic/stream.sse`: three made-up events of Hermes' stream for the
  constant-maturity curve, a minute apart, as server-sent events.

The transport answers each request as Hermes would, by its path; an ID the
sample does not hold is left out of the answer.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator, Mapping
from importlib import resources
from typing import Any

from .hermes import AT, CATALOGUE, LATEST, STREAM


def _text(name: str) -> str:
    return (resources.files("pyth") / "synthetic" / name).read_text(encoding="utf-8")


class Synthetic:
    """Hermes, answered from the committed sample data."""

    def __init__(self) -> None:
        self.catalogue = _text("price_feeds.json")
        held = json.loads(_text("updates.json"))
        self.latest: dict[str, dict[str, Any]] = held["latest"]
        self.events = _text("stream.sse").splitlines()
        self.requests: list[str] = []

    def _answer(self, ids: list[str], at: int | None) -> str:
        parsed = []
        for feed_id in ids:
            held = self.latest.get(feed_id)
            if held is None:
                continue
            price = dict(held)
            if at is not None:
                price["publish_time"] = at
            parsed.append({"id": feed_id, "price": price, "ema_price": price, "metadata": {}})
        return json.dumps({"binary": {"encoding": "hex", "data": []}, "parsed": parsed})

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]:
        self.requests.append(url)
        parts = urllib.parse.urlsplit(url)
        ids = [v for k, v in urllib.parse.parse_qsl(parts.query) if k == "ids[]"]
        if parts.path == CATALOGUE:
            return 200, self.catalogue, {}
        if parts.path == LATEST:
            return 200, self._answer(ids, None), {}
        if parts.path.startswith(AT) and parts.path[len(AT) :].isdigit():
            return 200, self._answer(ids, int(parts.path[len(AT) :])), {}
        return 404, "not found", {}

    def lines(self, url: str, headers: dict[str, str]) -> Iterator[str]:
        self.requests.append(url)
        if urllib.parse.urlsplit(url).path != STREAM:
            return
        yield from self.events
