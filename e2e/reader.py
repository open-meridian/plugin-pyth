"""A reading plugin for the e2e, on the Python SDK: the deployment's view of
what this plugin recorded, as a `reporting` plugin entitled to its datasets
reads it (W10.6). Not the plugin, and never shipped: the e2e runs it from
this directory in the plugin's own image, which carries the SDK.

It answers its page as JSON, so the harness's runner can read it
(`page --instance reader --level read PATH`):

  /curve?subject=ID&date=D[&dataset=D]
      a curve for a business date, every page read (`rates.read_curve`): each
      rate's dataset, row key, version, business date, kind, value as text,
      unit, tenor and convention; and what the lake left unanswered, with why;
  /prices?subject=ID&dataset=D
      the latest prices of a subject from one dataset, and what the lake left
      unanswered, with why;
  /datasets
      the datasets it may read.

Standard library and the SDK only; every value stays text, never a float.
"""
import asyncio
import http.server
import json
import threading
import urllib.parse

import meridian
from meridian import Interface, Page, SourceChoice
from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import reporting
from meridian.roles.data import rates

PORT = 8088
LOOP = asyncio.new_event_loop()


def rate_json(rate):
    meta = rate.meta
    convention = rate.convention
    return {
        "dataset": meta.source.dataset,
        "row_key": meta.row_key,
        "version": meta.version,
        "business_date": meta.business_date,
        "subject": meta.subjects[0].entity_id if meta.subjects else "",
        "kind": ops.RateKind.Name(rate.kind),
        "value": str(as_decimal(rate.value.value)),
        "unit": ops.ValueUnit.Name(rate.value.unit),
        "tenor": rates.tenor_label(rate.tenor) if rate.HasField("tenor") else "",
        "convention": [ops.DayCount.Name(convention.day_count),
                       ops.Compounding.Name(convention.compounding),
                       convention.periods_per_year],
        "published": [t.at_ns for t in meta.source_times if t.kind == ops.SOURCE_TIME_KIND_PUBLISHED],
    }


def price_json(price):
    meta = price.meta
    return {
        "dataset": meta.source.dataset,
        "subject": meta.subjects[0].entity_id if meta.subjects else "",
        "kind": ops.PriceKind.Name(price.kind),
        "amount": str(as_decimal(price.price.amount)),
        "currency": price.price.currency_code,
        "confidence": str(as_decimal(price.confidence)) if price.HasField("confidence") else "",
    }


class Reporting(reporting.Role):
    """`reporting`: reads the curve, prices and the datasets, and names the
    euro by its ISO 4217 code."""


class Reader:
    """What the stand-in answers, through its role class (SDK 0.35: each
    role one class, its acts made through it). It hears nothing: each read
    is asked when the runner asks."""

    def __init__(self):
        self.reporting = Reporting()
        self.euro = ""

    async def curve(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        sources = SourceChoice(named=[one("dataset")]) if one("dataset") else None
        read = await rates.read_curve(self.reporting, one("subject"), one("date"), sources=sources)
        # What the lake left unanswered, asked once more for it alone.
        answer = await self.reporting.list_rates(
            subjects=[meridian.SubjectRef(entity_id=one("subject"))], business_date=one("date"),
            sources=sources)
        return {
            "rates": [rate_json(r) for r in read],
            "unanswered": [
                {"subject": u.subject.entity_id, "dataset": u.dataset,
                 "reason": ops.UnansweredReason.Name(u.reason)}
                for u in answer.unanswered
            ],
        }

    async def prices(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        answer = await self.reporting.list_prices(
            subjects=[meridian.SubjectRef(entity_id=one("subject"))],
            sources=SourceChoice(named=[one("dataset")]))
        return {
            "prices": len(answer.prices),
            "rows": [price_json(p) for p in answer.prices],
            "unanswered": [
                {"subject": u.subject.entity_id, "dataset": u.dataset,
                 "reason": ops.UnansweredReason.Name(u.reason)}
                for u in answer.unanswered
            ],
        }

    async def resolve(self):
        """The euro's record, by its ISO 4217 code: a currency known by its
        code alone."""
        if not self.euro:
            found = await self.reporting.resolve_identifier(
                identifiers=[ops.Identifier(scheme="iso4217", value="EUR")])
            if not found.instrument_id:
                raise RuntimeError(f"the euro did not resolve: {found}")
            self.euro = found.instrument_id
        return {"euro": self.euro}

    async def answer(self, path, query):
        if path == "/resolve":
            return await self.resolve()
        if path == "/curve":
            return await self.curve(query)
        if path == "/prices":
            return await self.prices(query)
        if path == "/datasets":
            listed = await self.reporting.list_datasets()
            return {"datasets": [d.dataset for d in listed.datasets]}
        return {"page": "the e2e's reader"}


def serve(reader):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            future = asyncio.run_coroutine_threadsafe(
                reader.answer(parsed.path, urllib.parse.parse_qs(parsed.query)), LOOP)
            try:
                body, status = json.dumps(future.result(timeout=60), sort_keys=True), 200
            except Exception as failed:  # said on the page, for the run to quote
                body, status = json.dumps({"failed": f"{type(failed).__name__}: {failed}"}), 500
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


#: What the stand-in registers, its whole declaration (contract v25): the
#: e2e prints it with meridian-declaration and the harness holds the
#: stand-in's registration to it.
DECLARATION = meridian.Declaration(
    interface=Interface(PORT, "The e2e's reader", pages=[Page("/", "Rates", levels=["read"])])
)


def main():
    reader = Reader()
    threading.Thread(target=serve, args=(reader,), daemon=True).start()
    # SDK 0.35: its role class registered on the connection, until the
    # harness stops it.
    LOOP.run_until_complete(meridian.run_async(declaration=DECLARATION, roles=[reader.reporting]))


if __name__ == "__main__":
    asyncio.set_event_loop(LOOP)
    main()
