"""The two pages under Manage, and their read tools: what each shows, to
whom, that neither shows a value, and that the key is never shown."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.testing import PageClient

from pyth.page import connection_read, datasets_read, figures, hold, pages

from conftest import PAR, Sample, want, work

KEY = "test-key-not-real"


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    done = work(tmp_path)

    async def run() -> None:
        await done.on_want(want("w-1", [PAR]))
        await done.on_want(want("w-standing", [PAR], standing=True))
        await done.on_want(want("w-btc", ["INS-BTC"], key="crypto", data_type="meridian.v1.Price"))

    asyncio.run(run())
    hold(done)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        ("/", "admin"): 200,
        ("/", "write"): 403,
        ("/", "read"): 403,
        ("/datasets", "admin"): 200,
        ("/datasets", "write"): 403,
        ("/datasets", "read"): 403,
    }
    # No value on any page: the sample's yields and prices are the readers'.
    client.assert_no_account_data("4.11234567", "68123.45678901", "1.16431")


def test_connection_says_how_hermes_is_reached(client: PageClient) -> None:
    text = client.get("/", "admin").text
    assert text.index("<h2>Key</h2>") < text.index("<h2>Limits and use</h2>")
    assert text.index('<th scope="row">Catalogue</th>') < text.index("<h2>Stream</h2>")
    assert "Sample data" in text and "Pyth API key: not set" in text
    assert "21 feeds in its datasets, 10 in none" in text


def test_datasets_say_which_record_and_which_wait(client: PageClient) -> None:
    text = client.get("/datasets", "admin").text
    assert text.count(">Waits<") == 6 and "OpenYield" in text  # on the cell's title


def test_the_key_is_never_shown(tmp_path: Path) -> None:
    done = work(tmp_path, transport=Sample())
    done.hermes.session.mode = "live"
    done.hermes.use_key(KEY)
    read = connection_read(done)
    assert read.mode == "Live" and read.credentials[0].set
    assert KEY not in repr(read) and KEY not in repr(datasets_read(done))
    assert KEY not in repr(figures(done))


def test_without_a_key_the_mode_says_so(tmp_path: Path) -> None:
    done = work(tmp_path)
    done.hermes.session.mode = "live"
    assert connection_read(done).mode == "No key"
    assert [f.value for f in figures(done)][0] == "No key"
