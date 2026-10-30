"""The pages on sample data, each printed as one HTML file: for looking at
them without a deployment.

    python -m pyth.preview connection > preview/connection.html
    python -m pyth.preview datasets > preview/datasets.html

The plugin's work runs on the SDK's lake as a test stands it in, in place of
a sidecar -- the par yield curve resolved to a record the stand-in holds,
every batch recorded -- against the sample data: the latest curve wanted and
recorded, a business date's answered, a standing want kept current from the
sample stream, and a want of a crypto price declined while the prices wait.
Each page links the kit where the dashboard serves it, /.meridian/ui/<version>/:
served beside the kit it is styled (`make preview SHOTS=...` checks each in a
browser). `connection-first` and `datasets-first` are the pages before any
want: the role's "not set up yet" states.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from meridian.edge import RawStore
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake
from meridian.testing import PageClient

from . import curve
from .hermes import Hermes
from .page import hold, pages
from .synthetic import Synthetic
from .work import Work

PAR = "INS-PREVIEW-UST-PAR"
PAGES = {
    "connection": "/",
    "datasets": "/datasets",
    "connection-first": "/",
    "datasets-first": "/datasets",
}


def _want(want_id: str, key: str, subject: str, day: str = "", standing: bool = False) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=f"pyth:{key}",
            data_type="meridian.v1.Rate" if key == "rates" else "meridian.v1.Price",
            subjects=[ops.SubjectRef(entity_id=subject)],
            business_date=day,
            standing=standing,
        ),
    )


def _work() -> Work:
    lake = Lake("pyth")
    lake.instruments.hold(
        PAR,
        ops.Identifier(scheme=curve.CURVE[0], value=curve.CURVE[1], source=curve.CURVE[2]),
        asset_class=ops.ASSET_CLASS_REFERENTIAL,
    )
    store = RawStore(Path(tempfile.mkdtemp(prefix="pyth-preview-")))
    return Work(lake, Hermes(store, Synthetic(), "synthetic"))


async def worked() -> Work:
    """The work as sample data leaves it, on the stand-in lake."""
    work = _work()
    await work.on_want(_want("want-latest", "rates", PAR))
    await work.on_want(_want("want-1029", "rates", PAR, "2026-10-29"))
    await work.on_want(_want("want-standing", "rates", PAR, standing=True))
    await work._run_stream([f.feed_id for f in work.curve_feeds()])
    await work.on_want(_want("want-btc", "crypto", "INS-PREVIEW-BTC"))
    return work


def render(page: str) -> str:
    work = _work() if page.endswith("-first") else asyncio.run(worked())
    hold(work)
    answer = PageClient(pages).get(PAGES[page], "admin")
    if answer.status != 200:
        raise SystemExit(f"{page} answered {answer.status}: {answer.text[:200]}")
    return answer.text


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "connection"
    if page not in PAGES:
        raise SystemExit(f"no page {page!r}: {', '.join(PAGES)}")
    sys.stdout.write(render(page))


if __name__ == "__main__":
    main()
