"""The plugin's pages, under Manage alone: the data role's common pages
(spec/plugin-pages-follow-their-role), Connection and Datasets, each also a
read tool for agents on the deployment's MCP under the role's names
(`read_connection`, `read_datasets`). Each record is the role's
(`meridian.roles.data`), extended with Pyth's fields; each template is the
role's, with Pyth's nuance at its blocks only.

- **Connection** (`/`): the role's "Key" (the Pyth API key, set or not --
  never its value), "Limits and use" and "Stream"; then Pyth's own,
  "Catalogue": when Pyth's feed catalogue was last read, and how many of its
  feeds each dataset holds.
- **Datasets** (`/datasets`): the role's "Served", "Wants" and "Subjects",
  with Pyth's "Presented" column: whether each dataset records, or why it
  waits (prices.py); and a notice naming who stands behind the values.

Neither shows a price or a rate: those are the reading roles' to show.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import data

from . import prices
from .catalogue import KEYS, TREASURY_PRICES
from .declared import CATALOGUE
from .hermes import Hermes
from .synthetic import Synthetic
from .work import WAITING, Work

TITLE = "Pyth"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates")

#: How many wants the Datasets tab draws; read_datasets answers every one held.
SHOWN_WANTS = 3
DEFAULT_TERMS = "kept, internal use, display, derived use not restricted, no redistribution"
BEHIND = {
    **{key: prices.COMPOSITE for key in KEYS},
    "rates": prices.TREASURY_PUBLISHERS,
    TREASURY_PRICES: prices.TREASURY_PUBLISHERS,
}


@dataclass(frozen=True)
class Family:
    """One dataset as Pyth's catalogue fills it: how many feeds it holds,
    whether it records now, why not where it waits, and who stands behind
    its values."""

    dataset: str
    feeds: int
    presented: bool
    why_not: str = ""
    behind: str = ""


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then Pyth's: when its catalogue was read,
    each dataset's feeds in it, and the feeds no dataset holds."""

    catalogue_read_at: str = ""
    families: list[Family] = field(default_factory=list)
    not_served: int = 0
    stream_events: int = 0
    stream_error: str = ""


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then Pyth's: each dataset's feeds, whether
    it is presented and why not."""

    families: list[Family] = field(default_factory=list)
    #: The par yield curve's record the `rates` rows are about, or empty.
    curve_record: str = ""


_held: dict[str, Work] = {}


def hold(work: Work) -> None:
    """The work the pages read, once the plugin has registered."""
    _held["work"] = work


def _iso(at_ns: int) -> str:
    return data.iso_time(at_ns)


def families(work: Work) -> list[Family]:
    instance = work.plugin.identity.instance_id
    counts = work.catalogue.counts() if work.catalogue.feeds else {}
    return [
        Family(
            dataset=f"{instance}:{key}",
            feeds=counts.get(key, 0),
            presented=key not in WAITING,
            why_not=WAITING.get(key, ""),
            behind=BEHIND[key],
        )
        for key in KEYS
    ]


def _mode(work: Work) -> str:
    if work.hermes.mode != "live":
        return "Sample data"
    return "Live" if work.hermes.key else "No key"


def connection_read(work: Work) -> ConnectionRead:
    health = work.hermes.health
    keyed = bool(work.hermes.key)
    return ConnectionRead(
        mode=_mode(work),
        credentials=[data.Credential("Pyth API key", keyed)],
        entitled_at_vendor=(
            "Sample data: no key needed"
            if work.hermes.mode != "live"
            else "As the key's Pyth plan allows: Starter serves crypto, Pro every family"
            if keyed
            else "Pyth's feed catalogue only: every price asks for a key"
        ),
        limit=f"{work.hermes.session.limits.allowed}. This plugin: one request at a time",
        calls=health.calls,
        rate_limited=health.rate_limited,
        last_call_at=_iso(max(health.last_ok_ns, health.last_failed_ns)),
        last_error=health.last_error,
        sessions=1 if work.stream.open else 0,
        catalogue_read_at=_iso(work.catalogue.read_at_ns),
        families=families(work),
        not_served=work.catalogue.counts().get("", 0) if work.catalogue.feeds else 0,
        stream_events=work.stream.events,
        stream_error=work.stream.error,
    )


def datasets_read(work: Work) -> DatasetsRead:
    instance = work.plugin.identity.instance_id
    served = data.served(
        CATALOGUE,
        instance,
        work.wants,
        "As the key's plan allows" if work.hermes.mode == "live" else "Sample data",
    )
    return DatasetsRead(
        served=[replace(s, default_terms=DEFAULT_TERMS) for s in served],
        wants=list(data.want_rows(work.wants)),
        reads_instruments=True,
        families=families(work),
        curve_record=work.curve_record,
    )


def figures(work: Work) -> list[meridian.Figure]:
    """The data role's figures, in its order; Pyth's plugin reports none of
    its own."""
    health = work.hermes.health
    mode = _mode(work)
    if mode == "Sample data":
        connection: Any = "Sample data"
    elif mode == "No key":
        connection = "No key"
    elif not health.healthy:
        connection = meridian.Figure(
            "", "Not answering", state="error", why=health.last_error[:200]
        )
    else:
        connection = "Answering"
    last = work.wants.counts.last_ns
    presented = len([k for k in KEYS if k not in WAITING])
    return data.figures(
        connection=connection,
        entitled_at_vendor=f"{presented} of {len(KEYS)} datasets",
        stream="1 curve" if work.stream.open else "Off",
        last_recorded=datetime.fromtimestamp(last / 10**9, UTC) if last else None,
    )


def _running(request: meridian.Request) -> Work:
    held = _held.get("work")
    if held is None:
        held = Work(request.plugin, Hermes(RawStore(storage_root()), Synthetic(), "synthetic"))
    return held


@pages.page(
    "/",
    "Connection",
    levels="admin",
    answers=ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches Pyth's Hermes API, as every data plugin's Connection answers "
        "it: the mode (Live, No key or Sample data), whether the Pyth API key is set (never "
        "its value), what the key's plan serves, the calls made and the last error, and "
        "Hermes' stream. Then Pyth's own: when its feed catalogue was read and how many feeds "
        "each dataset holds. No price and no rate."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    return pages.answer("connection.html", connection_read(_running(request)))


@pages.page(
    "/datasets",
    "Datasets",
    levels="admin",
    answers=DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: its "
        "seven datasets as the catalogue declares them (Pyth's crypto, FX, equity, metal and "
        "commodity prices, its US Treasury constant-maturity par yields as rates, and the "
        "on-the-run Treasuries), whether a deployment admin has licensed each, what it "
        "recorded and declined, and the wants it answered and keeps current. Then Pyth's own: "
        "whether each dataset records now, or why it waits, and who stands behind its values. "
        "No price and no rate."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    read = datasets_read(_running(request))
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer("datasets.html", drawn)
