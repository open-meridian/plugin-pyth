# plugin-pyth

Pyth Network's prices and rates for [Open Meridian](https://open-meridian.com),
as a data plugin: Pyth's Hermes API, read with your deployment's Pyth API
key, into your deployment's lake.

| Dataset | What it holds | Now |
|---|---|---|
| `crypto`, `fx`, `equity`, `metal`, `commodities` | Pyth's composite prices, by family | Wait for the contract revision adding a composite price and its confidence interval |
| `rates` | Pyth's US Treasury constant-maturity par yields, 2 to 30 years, as points of the par yield curve | Records |
| `treasury_prices` | The on-the-run US Treasuries' clean prices and yields | Waits for the bond template |

**A Pyth API key is needed.** Since 26 August 2026 Hermes asks for one on
every price. Pyth's Starter plan serves crypto; its Pro plan every family.
The key is a secret setting: sent to Hermes alone, never logged or shown.
Pyth's terms are your deployment's to settle with Pyth: see
[docs/terms.md](docs/terms.md).

The documentation the plugin ships with -- overview, setup, pages,
troubleshooting and terms -- is in [docs/](docs/README.md); `AGENTS.md` is
for whoever works on it next.

## Develop

    make ci-remote     # lint and the tests, in a container
    make check         # meridian plugin check --verified --run-tests
    make e2e           # the plugin on the plugin harness, on sample data
    make preview       # the pages on sample data, in preview/

Every gate runs in a container; plugins land CI-first, through a pull
request.

Apache-2.0. Pyth and Pyth Network are trademarks of their owners; this
project is not affiliated with or endorsed by the Pyth Data Association or
Douro Labs.
