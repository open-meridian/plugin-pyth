"""Pyth Network's prices and rates as an Open Meridian data plugin.

It runs as the SDK runs a plugin (open-meridian 0.35, `meridian.run`): its
data role's class (`Lake`, work.py's `Work`) registered on the sidecar it is
launched beside with its whole declaration (declaration.py) -- its
catalogue, its storage, its settings, its pages (page.py) and its
documentation -- and the pages served. Once the settings
have said where to answer from -- Hermes with the deployment's Pyth API
key, or sample data -- it hears what the lake wants of it and records it or
declines it, and keeps each standing want current from Hermes' stream
(work.py), until stopped. Everything goes through the sidecar; nothing but
Hermes is called, and with sample data not even that (synthetic.py).

It holds nothing it cannot lose: Hermes' answers are kept in the storage
the deployment grants it (decisions/028), moved past their window as the
settings say; a restart reads Pyth's catalogue again and hears again what
the lake wants. The key is held in memory only, as the settings deliver it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import Latency

from .declaration import DECLARATION, PORT
from .declared import API_KEY, KIND, SAMPLE_DATA
from .hermes import Hermes, Https
from .page import figures, hold, pages
from .synthetic import Synthetic
from .work import Work

log = logging.getLogger("pyth")

#: How often the datasets' licences are read again and the health said.
LICENCES_SECONDS = 60


def source(store: RawStore, sample_data: bool, key: str) -> Hermes:
    """Hermes itself with the deployment's key, or the sample data."""
    if sample_data:
        return Hermes(store, Synthetic(), "synthetic")
    return Hermes(store, Https(), "live", key)


class Lake(Work):
    """The data role's class as the process runs it: the work (work.py),
    the settings applied as they are delivered, and in `run` Hermes' stream
    kept open, the licences read, the health said and the latency reported
    -- each restarted by `meridian.run` after a backoff should it stop."""

    store: RawStore

    async def on_settings(self, delivered: Any) -> None:
        """One delivery of the settings, the first before anything is heard:
        the source switched where sample data changed, the key given to
        Hermes, and the raw answers past their window moved. The key's value
        is never logged: only whether it is set."""
        values = delivered.values
        sample = values.get(SAMPLE_DATA) is True
        given = values.get(API_KEY)
        key = given.strip() if isinstance(given, str) else ""
        log.info("settings delivered: sample data %s, a Pyth API key %s", sample,
                 "set" if key else "not set")  # fmt: skip
        if sample != (self.hermes.mode != "live"):
            self.use(source(self.store, sample, key))
            log.info("answering from %s", self.hermes.mode)
            await self.prepare()
        if self.hermes.mode == "live":
            if key != self.hermes.key:
                self.stream.restart()
            self.hermes.use_key(key)
        try:
            await self.store.tend(self.plugin, settings=delivered)
        except (meridian.MeridianError, OSError, ValueError) as failed:
            log.warning("the raw answers were not tended this time: %s", failed)

    async def on_start(self) -> None:
        # Contract v28 (ruling 518): each row recorded unasked or for a
        # standing want has its age at the edge recorded, reported every 10
        # seconds (ReportLatency) through this class.
        self.latency.role = self
        await self.prepare()

    async def run(self) -> None:
        await asyncio.gather(self.stream.run(), self.each_minute(), self.latency.run())

    async def each_minute(self) -> None:
        """Each minute: its datasets' licences read again (contract v20), and
        whether Hermes answers said as the plugin's health."""
        while True:
            try:
                await self.read_licences()
            except meridian.MeridianError as failed:
                log.warning("licences not read: %s", failed)
            health = self.hermes.health
            detail = "Hermes answers" if health.healthy else health.last_error
            try:
                await self.plugin.report(healthy=health.healthy, detail=detail[:200])
            except (meridian.MeridianError, ValueError) as failed:
                log.warning("health not reported: %s", failed)
            await asyncio.sleep(LICENCES_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    store = RawStore(storage_root(), KIND)
    lake = Lake(source(store, sample_data=False, key=""))
    lake.store = store
    lake.latency = Latency()
    hold(lake)
    meridian.run(
        DECLARATION,
        roles=[lake],
        pages=pages,
        port=PORT,
        on_settings=lake.on_settings,
        figures=lambda: figures(lake),
    )


if __name__ == "__main__":
    main()
