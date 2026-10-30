"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v28), beside `reader`, a reporting plugin (e2e/reader.py) entitled
to its datasets, and the harness's admin. Run from the repository's root by
the Makefile, which builds the image and writes the harness's plugins first;
standard library only. The harness's stand-in for the platform holds the
platform's seeded referential records, matched by `symbol` and the
administrator's source, so Treasury's par yield curve resolves to its `INS-`.

No Pyth API key is used: Hermes answers nowhere (the e2e's hosts file), and
sample data answers from Pyth's catalogue and made-up prices committed with
the plugin.

1. No key, Hermes unreachable: Connection says "No key", and nothing is
   recorded.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed catalogue and resolves the par yield curve's
   record by Treasury's title under `ustreasury`.
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show -- the key not set, seven
   datasets, the price families and `treasury_prices` waiting, the curve's
   `INS-` -- and core's `dashboard__list_datasets` lists the seven datasets
   as the catalogue declares them.
4. Licensed and entitled at the Data sources page: the reader is entitled to
   `rates`, `crypto` and `treasury_prices`.
5. Read back, as a curve for a date (`rates.read_curve`): the reader's read
   of 29 October 2026 is asked of the plugin, which reads it at the day's
   close and records seven points, 2 to 30 years in tenor order, the 10-year
   4.11234567 per cent, a par yield, bond-equivalent, published at 17:00 New
   York.
6. Declined while they wait: a price of `crypto` and of `treasury_prices`,
   each asked of the plugin and declined not covered; nothing is recorded as
   a price.
"""

import json
import os
import subprocess
import sys
import time

PROJECT = "pyth-e2e"
LOG = ".e2e/runner.log"
COMPONENTS = ".e2e/components.log"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml"]
INSTANCE = "pyth"
KEYS = ["crypto", "fx", "equity", "metal", "commodities", "rates", "treasury_prices"]
DATASETS = [f"{INSTANCE}:{key}" for key in KEYS]
RATES, CRYPTO, TREASURIES = f"{INSTANCE}:rates", f"{INSTANCE}:crypto", f"{INSTANCE}:treasury_prices"
DAY = "2026-10-29"
#: 17:00 New York on 29 October 2026, in nanoseconds: the day's close.
CLOSE_NS = 1_793_307_600 * 10**9


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True, timeout=600):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True,
                          timeout=timeout)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def call(tool, arguments=None):
    done = runner("mcp", "call", tool, json.dumps(arguments or {}), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}")
    must(answer.get("outcome") in ("read", "unchanged"), f"{tool} answered {done.stdout[-700:]}")
    return answer["data"]


def store_lake():
    return compose("run", "--rm", "-T", "store", "lake").stdout


def reader(path):
    return json.loads(page("reader", "read", path))


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    runner("ready")
    runner("ready", "--instance", "reader")

    # 1. No key, Hermes unreachable.
    runner("page", "--level", "admin", "/", "--until", "No key", "--seconds", "90")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded without a key: {lake[-500:]}")

    # 2. Sample data: the catalogue read, the curve's record resolved.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "21 feeds in its datasets", "--seconds", "120")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{INSTANCE}:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    connection = call(read_connection)
    must(connection["mode"] == "Sample data"
         and connection["credentials"] == [{"label": "Pyth API key", "set": False}]
         and [f["dataset"] for f in connection["families"]] == DATASETS
         and [f["presented"] for f in connection["families"]] == [False] * 5 + [True, False]
         and connection["families"][5]["feeds"] == 7,
         f"step 3, read_connection: {connection}")
    datasets = until(60, lambda: (lambda d: d if d["curve_record"] else None)(call(read_datasets)),
                     "step 3, read_datasets names the curve's record")
    record = datasets["curve_record"]
    must(record.startswith("INS-") and [s["dataset"] for s in datasets["served"]] == DATASETS,
         f"step 3, read_datasets: {datasets}")
    shown = page(INSTANCE, "admin", "/datasets")
    must(record in shown and shown.count(">Waits<") == 6,
         "step 3, Datasets shows what read_datasets answers")
    listed = {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]}
    entry = listed.get(RATES, {}).get("catalogue_entry", {})
    must(entry.get("modes") == ["pull", "stream"] and entry.get("day_time_zone") == "America/New_York"
         and entry.get("day_end_minute") == 1020,
         f"step 3, core lists {RATES} as declared: {listed.get(RATES)}")
    must(all(d in listed for d in DATASETS), f"step 3, core lists the seven datasets: {list(listed)}")

    # 4. Licensed and entitled.
    for dataset in (RATES, CRYPTO, TREASURIES):
        runner("licence", dataset, "kept=true", "retention_days=0", "derived_use=true",
               "display=true", "personal_use=false",
               "note=Pyth's subscription terms: internal use and display.")
        runner("entitle", "--instance", "reader", dataset, "note=The e2e's reader reads them.")
    runner("grant", "--instance", "reader", "--level", "read")

    # 5. A curve for a date, read at its close.
    curve = until(90, lambda: (lambda r: r if len(r["rates"]) == 7 else None)(
        reader(f"/curve?subject={record}&date={DAY}&dataset={RATES}")),
        "step 5, the curve of 29 October was not read")
    rates = curve["rates"]
    ten = [r for r in rates if r["tenor"] == "10Y"]
    must([r["tenor"] for r in rates] == ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
         and ten and ten[0]["value"] == "4.11234567" and ten[0]["kind"] == "RATE_KIND_PAR_YIELD"
         and ten[0]["unit"] == "VALUE_UNIT_PERCENT" and ten[0]["subject"] == record
         and ten[0]["convention"] == ["DAY_COUNT_ACT_ACT", "COMPOUNDING_COMPOUNDED", 2]
         and ten[0]["published"] == [CLOSE_NS] and ten[0]["business_date"] == DAY
         and ten[0]["dataset"] == RATES,
         f"step 5, the curve in tenor order, the 10-year as Hermes states it: {curve}")

    # 6. The prices wait: each asked of the plugin and declined.
    for dataset in (CRYPTO, TREASURIES):
        until(90, lambda: (lambda p: p["prices"] == 0 and [u["reason"] for u in p["unanswered"]]
                           == ["UNANSWERED_REASON_NOT_COVERED"])(
            reader(f"/prices?subject={record}&dataset={dataset}")),
            f"step 6, a price of {dataset} was not declined not covered")
    lake = store_lake()
    must(f"want|{CRYPTO}|declined|{record}|" in lake and f"want|{TREASURIES}|declined|{record}|" in lake,
         f"step 6, the lake holds the plugin's declines: {[l for l in lake.splitlines() if l.startswith('want|')]}")
    must(not any(line.startswith("row|") and "|meridian.v1.Price|" in line for line in lake.splitlines()),
         "step 6, no price recorded while the prices wait")

    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: no key said on Connection "
          f"and nothing recorded; sample data's catalogue read and the par yield curve's record "
          f"resolved to its INS-; read_connection and read_datasets answering what the pages show, "
          f"and core listing the seven datasets as declared; licensed and entitled; the curve of 29 "
          f"October read at its close, seven points in tenor order (10-year 4.11234567, a par "
          f"yield, bond-equivalent, published at 17:00 New York); and a crypto price and a "
          f"Treasury's declined not covered while they wait, no price recorded")


def main():
    os.makedirs(".e2e", exist_ok=True)
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError, TypeError) as failed:
        with open(COMPONENTS, "a", encoding="utf-8") as kept:
            kept.write(compose("logs", "--no-color", check=False).stdout)
        compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
        print(f"e2e FAILED: {failed}; the runner's log is in {LOG}, the components' in {COMPONENTS}",
              file=sys.stderr)
        return 1
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
