"""Pyth's Hermes API, as this plugin calls it, with the standard library.

Hermes is Pyth's off-chain price service (https://hermes.pyth.network). Since
Pyth's Core upgrade of 26 August 2026 every price it serves asks for a Pyth
API key, sent as `Authorization: Bearer <key>`: the latest prices, a price
at a past moment and the stream all answer 401 without one. Its feed
catalogue still answers without a key. The key is the deployment's, entered
by its admin in Settings (a secret setting): it is sent on each request and
nowhere else -- never logged, never kept with a response, never shown.

Four calls, each answer kept as received before anything is read from it
(the SDK's `RawStore`, decisions/028):

- `catalogue()`: `GET /v2/price_feeds`, every feed Pyth publishes, its ID
  and attributes (catalogue.py reads them);
- `latest(ids)`: `GET /v2/updates/price/latest?ids[]=...&parsed=true`, the
  latest price of each feed;
- `at(publish_time, ids)`: `GET /v2/updates/price/<publish_time>?ids[]=...`,
  each feed's price at a past moment, in seconds;
- `stream(ids)`: `GET /v2/updates/price/stream?ids[]=...&parsed=true`, a
  server-sent events stream, one `data:` line per update.

An update is read as Hermes documents it (`parsed[]`): its feed ID, its
price and confidence interval as integers in their text with one exponent
(`price.price`, `price.conf`, `price.expo`), and the second Pyth published
it (`price.publish_time`). Each is made a `Decimal` exactly -- `"412345678"`
at exponent -8 is 4.12345678 -- never through a float.

A 429 is waited out (0.1.1): its `Retry-After` when Hermes sends one, else
a backoff of 1, 2 then 4 seconds with jitter, at most `RETRIES` times, each
counted; only then is the call failed. The stream, refused with a 429, is
opened again after at least its `Retry-After` (work.py).

With sample data the plugin answers from files committed with it
(synthetic.py) and calls nothing.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from meridian.edge import RawStore
from meridian.roles.data import Endpoint, Health, Limits, Session

from .catalogue import PythFeed, read_catalogue

log = logging.getLogger(__name__)

BASE = "https://hermes.pyth.network"
CATALOGUE = "/v2/price_feeds"
LATEST = "/v2/updates/price/latest"
AT = "/v2/updates/price/"
STREAM = "/v2/updates/price/stream"
#: How long one request may take before it is given up, in seconds.
TIMEOUT_SECONDS = 20
#: The most feed IDs one request names: Hermes takes many, and a URL stays
#: well within what servers accept at this many.
MOST_IDS = 50
#: What Pyth's documentation says of its limits: the plan's, not stated per
#: request for Hermes with a key.
ALLOWED = "as the key's Pyth plan allows (Pyth states its limits per plan)"
NS = 1_000_000_000
#: How many times a 429 is waited out before the call fails.
RETRIES = 3
#: The first wait after a 429 without `Retry-After`, in seconds; doubled each time.
BACKOFF_FIRST_SECONDS = 1.0
#: The longest one wait may be, whatever `Retry-After` asks.
WAIT_MOST_SECONDS = 60.0


class HermesError(Exception):
    """Hermes answered with an error, or could not be reached: its status
    (0 for none) and what it said, in words that never carry the key."""

    def __init__(self, status: int, said: str, retry_after: float | None = None) -> None:
        super().__init__(said)
        self.status = status
        #: The seconds Hermes asked to be waited (`Retry-After`), where it said.
        self.retry_after = retry_after


def retry_after(headers: Mapping[str, str]) -> float | None:
    """Seconds from a `Retry-After` header given in seconds; None where it
    is absent or not a number (an HTTP date is not read: the backoff stands)."""
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                seconds = float(value.strip())
            except ValueError:
                return None
            return seconds if seconds >= 0 else None
    return None


def backoff(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """The wait before retry `attempt` (0 first) without `Retry-After`: 1, 2,
    4 seconds, each between half and the whole of it (jitter), so plugins
    refused together do not come back together."""
    full = min(BACKOFF_FIRST_SECONDS * (1 << attempt), WAIT_MOST_SECONDS)
    return full / 2 + rand() * full / 2


class Transport(Protocol):
    """How Hermes is reached: one request (its status, body and headers),
    and one stream of lines."""

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]: ...

    def lines(self, url: str, headers: dict[str, str]) -> Iterator[str]: ...


class Https:
    """Hermes over HTTPS, with the standard library."""

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310 - Hermes' https address
                return int(answer.status), answer.read().decode("utf-8"), dict(answer.headers)
        except urllib.error.HTTPError as refused:
            body = refused.read().decode("utf-8", "replace")
            return int(refused.code), body, dict(refused.headers or {})
        except (urllib.error.URLError, TimeoutError, OSError) as unreached:
            raise HermesError(0, f"Hermes was not reached: {unreached}") from None

    def lines(self, url: str, headers: dict[str, str]) -> Iterator[str]:
        request = urllib.request.Request(url, headers={**headers, "Accept": "text/event-stream"})
        try:
            answer = urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS * 3)  # noqa: S310 - Hermes' https address
        except urllib.error.HTTPError as refused:
            status = int(refused.code)
            raise HermesError(
                status, _said(status, ""), retry_after(dict(refused.headers or {}))
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as unreached:
            raise HermesError(0, f"Hermes' stream was not reached: {unreached}") from None
        with answer:
            for raw in answer:
                yield raw.decode("utf-8").rstrip("\r\n")


def _said(status: int, body: str) -> str:
    """What an error answer means, in words for a person."""
    if status == 401:
        return (
            "Hermes refused the request (401): it needs the deployment's Pyth API key, "
            "set in Settings, and a plan that serves this feed"
        )
    if status == 403:
        return "Hermes refused the key for this request (403): the key's plan does not serve it"
    if status == 404:
        return "Hermes has no price for this feed at that time (404)"
    if status == 429:
        return "Hermes is limiting this key's requests (429)"
    return f"Hermes answered {status}: {body[:120]}"


@dataclass(frozen=True)
class Update:
    """One price update as Hermes states it: the feed, its price and its
    confidence interval as exact decimals, the second Pyth published it, and
    the exponent and integers they were read from."""

    feed_id: str
    price: Decimal
    confidence: Decimal
    publish_time: int
    expo: int
    price_text: str
    conf_text: str

    @property
    def published_ns(self) -> int:
        return self.publish_time * NS


def _scaled(integer: str, expo: int) -> Decimal:
    """Hermes' integer text at its exponent, exactly: `"412345678"`, -8 is
    4.12345678."""
    return Decimal(int(integer)).scaleb(expo)


def read_updates(body: str) -> list[Update]:
    """Each parsed update of an answer (`parsed[]`), as Hermes documents it;
    one that does not read is left out and said."""
    held = json.loads(body)
    parsed = held.get("parsed", []) if isinstance(held, dict) else []
    out: list[Update] = []
    for entry in parsed:
        try:
            price = entry["price"]
            expo = int(price["expo"])
            out.append(
                Update(
                    feed_id=str(entry["id"]).lower().removeprefix("0x"),
                    price=_scaled(str(price["price"]), expo),
                    confidence=_scaled(str(price["conf"]), expo),
                    publish_time=int(price["publish_time"]),
                    expo=expo,
                    price_text=str(price["price"]),
                    conf_text=str(price["conf"]),
                )
            )
        except (KeyError, TypeError, ValueError) as unread:
            log.warning("an update Hermes sent did not read, left out: %r", unread)
    return out


def _query(ids: Sequence[str]) -> list[tuple[str, str]]:
    return [("ids[]", i) for i in ids] + [("parsed", "true")]


class Hermes:
    """Hermes, as this plugin calls it: each call counted on its session's
    health, each answer kept before it is read."""

    def __init__(
        self,
        store: RawStore,
        transport: Transport,
        mode: str = "live",
        key: str = "",
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self.store = store
        self.transport = transport
        self.key = key
        self.sleep, self.rand = sleep, rand
        self.session = Session(
            mode=mode,
            endpoints=(
                Endpoint("Feed catalogue", BASE + CATALOGUE, "every feed Pyth publishes"),
                Endpoint("Latest prices", BASE + LATEST, "the latest price of each feed wanted"),
                Endpoint("Prices at a time", BASE + AT + "<time>", "a past day's value"),
                Endpoint("Stream", BASE + STREAM, "each update of the feeds kept current"),
            ),
            limits=Limits(allowed=ALLOWED, spent="one request at a time"),
        )

    @property
    def mode(self) -> str:
        return self.session.mode

    @property
    def health(self) -> Health:
        return self.session.health

    def use_key(self, key: str) -> None:
        self.key = key.strip()

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "open-meridian-plugin-pyth", "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def _url(self, path: str, query: Sequence[tuple[str, str]] = ()) -> str:
        return BASE + path + ("?" + urllib.parse.urlencode(list(query)) if query else "")

    def _get(
        self, call: str, name: str, path: str, query: Sequence[tuple[str, str]]
    ) -> tuple[str, str]:
        """One request: its answer kept, then its body and the raw record's
        key; a 429 waited out (`Retry-After`, else backoff with jitter) up to
        `RETRIES` times; an error answer kept too, then raised in words."""
        url = self._url(path, query)
        health = self.health
        attempt = 0
        while True:
            health.calls += 1
            try:
                status, body, headers = self.transport.get(url, self._headers())
            except HermesError as failed:
                self._failed(str(failed))
                raise
            now = time.time_ns()
            key = self.store.keep(
                call, name, {"received_at_ns": now, "request": url, "status": status, "body": body}
            )
            if status != 429:
                break
            health.rate_limited += 1
            if attempt >= RETRIES:
                break
            asked = retry_after(headers)
            wait = backoff(attempt, self.rand) if asked is None else asked
            log.info("Hermes answered 429; waiting %.1f s before trying again", wait)
            self.sleep(min(wait, WAIT_MOST_SECONDS))
            attempt += 1
        if status != 200:
            said = _said(status, body)
            self._failed(said)
            raise HermesError(status, said)
        health.last_ok_ns = now
        return body, key

    def _failed(self, said: str) -> None:
        health = self.health
        health.failures += 1
        health.last_failed_ns = time.time_ns()
        health.last_error = said

    def catalogue(self) -> tuple[list[PythFeed], str]:
        """Every feed Pyth publishes, as its catalogue states it."""
        body, key = self._get("price_feeds", "all", CATALOGUE, ())
        return read_catalogue(body), key

    def latest(self, ids: Sequence[str]) -> list[tuple[Update, str]]:
        """The latest update of each feed, each with the raw record it came in."""
        out: list[tuple[Update, str]] = []
        for start in range(0, len(ids), MOST_IDS):
            chunk = list(ids[start : start + MOST_IDS])
            body, key = self._get("latest", f"{len(chunk)}-feeds", LATEST, _query(chunk))
            out += [(update, key) for update in read_updates(body)]
        return out

    def at(self, publish_time: int, ids: Sequence[str]) -> list[tuple[Update, str]]:
        """Each feed's update at a past second, each with its raw record;
        none where Hermes holds no price then (404)."""
        out: list[tuple[Update, str]] = []
        for start in range(0, len(ids), MOST_IDS):
            chunk = list(ids[start : start + MOST_IDS])
            try:
                body, key = self._get("at", str(publish_time), f"{AT}{publish_time}", _query(chunk))
            except HermesError as failed:
                if failed.status == 404:
                    continue
                raise
            out += [(update, key) for update in read_updates(body)]
        return out

    def stream(self, ids: Sequence[str]) -> Iterator[tuple[list[Update], str]]:
        """Hermes' stream of the feeds' updates: each event's updates and the
        raw line it was kept as, until the stream ends or fails."""
        url = self._url(STREAM, _query(ids))
        self.health.calls += 1
        try:
            for line in self.transport.lines(url, self._headers()):
                if not line.startswith("data:"):
                    continue
                body = line[len("data:") :].strip()
                now = time.time_ns()
                key = self.store.keep_line(
                    "stream", "updates", {"received_at_ns": now, "body": body}
                )
                self.health.last_ok_ns = now
                yield read_updates(body), key
        except HermesError as failed:
            if failed.status == 429:
                self.health.rate_limited += 1
            self._failed(str(failed))
            raise
