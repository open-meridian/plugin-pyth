"""Hermes' stream kept open by the SDK's supervisor (open-meridian 0.35,
ruling 1027: `helpers.sessions.Supervisor` over the plugin's own `Link`).

**The link** (`HermesLink`) is Hermes' server-sent events over HTTPS, the
standard library's (hermes.py, ruling 1038): the feeds wanted are named in
the stream's address, so a session is opened for exactly them, each event's
updates and the raw line they were kept as handed on. A stream that ends
(Hermes closes one after a day), breaks or times out is opened again by the
supervisor, a second later and doubling to a minute, each wait within a
fifth of itself -- never sooner than a 429's `Retry-After` (`RetryAfter`).
A refused key (401, 403) is waited out five minutes, or until the settings
change.

**Other feeds wanted** (`Streamer.want`): Hermes takes no subscription in a
stream already open, so a different set of feeds opens a new session at
once.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator, Sequence
from typing import Any

from meridian.helpers import sessions

from .hermes import Hermes, HermesError, Update

#: After the key is refused, how long before the stream is tried again.
REFUSED_SECONDS = 300.0
#: The waits between sessions: a second, doubling to a minute.
FIRST_SECONDS, MOST_SECONDS = 1.0, 60.0
#: Statements handed on: one event's updates and the raw line they came in.
Event = tuple[list[Update], str]


class Refused(Exception):
    """Hermes refused the stream: the key, or its plan."""


class RetryAfter(sessions.Backoff):
    """The supervisor's backoff, never shorter than the `Retry-After` Hermes
    last asked (`asked`), within the most it waits."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.asked = 0.0

    def failed(self) -> float:
        wait = super().failed()
        asked, self.asked = self.asked, 0.0
        return max(wait, min(asked, self.most_s))


class HermesLink:
    """One session of Hermes' stream for the feeds wanted (see the module)."""

    name = "Hermes' stream"

    def __init__(self, hermes: Hermes, backoff: RetryAfter) -> None:
        self.hermes, self.backoff = hermes, backoff
        self.ids: tuple[str, ...] = ()
        self.events: Iterator[Event] | None = None

    async def open(self) -> None:
        """Nothing yet: the stream is opened for the feeds it is subscribed to."""

    async def subscribe(self, wanted: Sequence[str]) -> None:
        if tuple(wanted) != self.ids or self.events is None:
            await self.close()
            self.ids = tuple(wanted)
            self.events = self.hermes.stream(self.ids)

    async def receive(self) -> list[Any]:
        """The next event, as one statement: its updates and its raw line."""
        events = self.events
        if events is None:
            raise EOFError("no stream is open")
        try:
            event = await asyncio.to_thread(next, events, None)
        except HermesError as failed:
            if failed.status in (401, 403):
                raise Refused(str(failed)) from None
            if failed.retry_after is not None:
                self.backoff.asked = failed.retry_after
            raise
        if event is None:
            raise EOFError("Hermes ended the stream")
        return [event]

    async def close(self) -> None:
        events, self.events = self.events, None
        if events is not None:
            close = getattr(events, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    close()


class Streamer(sessions.Supervisor):
    """Hermes' stream kept open while any feed is wanted (see the module):
    each event handed to `heard`."""

    def __init__(
        self,
        hermes: Callable[[], Hermes],
        heard: Callable[[list[Any]], Awaitable[Any]],
        **kwargs: Any,
    ) -> None:
        backoff = RetryAfter(first_s=FIRST_SECONDS, most_s=MOST_SECONDS)
        kwargs.setdefault("silent_seconds", 0.0)
        super().__init__(
            lambda: HermesLink(hermes(), backoff),
            heard=heard,
            session="hermes",
            refused=(Refused,),
            refused_seconds=REFUSED_SECONDS,
            backoff=backoff,
            **kwargs,
        )

    def want(self, wanted: Sequence[str]) -> None:
        """Stream these feeds, and only these, from now on: a session open
        for others is opened again for these."""
        given = tuple(dict.fromkeys(wanted))
        if given == self.wanted:
            return
        super().want(given)
        if given and self.state.state == "open":
            self.restart()
