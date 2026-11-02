# Changelog

## 0.2.0

Pyth's prices recorded, as composite mids (rulings 906 and 990), on
open-meridian 0.35.2 (each role one class; rulings 1003 to 1005 and 1009 to
1029), contract v29, on core v29's harness.

- **The five price families record:** `crypto`, `fx`, `equity`, `metal` and
  `commodities`, each price Pyth's composite `mid` in its quote currency
  with its confidence interval (`Price.confidence`, ruling 895), and each
  dataset's class of source declared `composite` (`price_source_class`,
  contract 28 as amended). A price is asked for a record carrying Pyth's
  feed ID (`pyth_feed_id`) or a code Pyth names a feed by -- a symbol, or a
  currency's ISO 4217 code -- in the record's currency; anything else is
  declined not covered, as is a kind but `mid`. The latest, a business
  date's last second (UTC) or a valid time is read from Hermes; a standing
  want is kept current from Hermes' stream, each price recorded when it
  changed and at most once a second. A crypto feed quoted in another token
  (ETH in BTC) is not served this version. `treasury_prices` still waits
  for the bond template. The licence defaults are left as they stand
  (rulings 1030 to 1032): who stands behind each dataset is said on the
  Datasets page and in the documentation.
- **Enabling it on a deployment needs the PO's Pyth API key**: without one
  only sample data and Pyth's catalogue answer.
- **The stream on the SDK's supervisor** (`helpers.sessions.Supervisor`,
  ruling 1027): Hermes' stream, the plugin's own standard-library client
  (ruling 1038), opened for exactly the feeds the standing wants name --
  the curve's and each price's -- and again at once when they change;
  after a break a second, doubling to a minute, never sooner than a 429's
  `Retry-After`; a refused key waited out five minutes or until the
  settings change.
- **The pins:** open-meridian 0.33.4 to 0.35.2, plugin-python:0.35.2 by tag
  and digest, meridian 0.1.57 in the check, and the e2e's runtime and
  harness at core 1ae36f0 (contract v29) by digest.
- **One class for its role:** the work (`Work`) is the data role's class,
  its acts made on itself; `__main__.Lake` adds the settings applied as
  delivered and, in its `run`, the stream, the licences read and the health
  said each minute and the latency reported, registered with
  `meridian.run`, which restarts it after a backoff should it stop (the
  plugin no longer exits to be restarted). The raw answers are tended from
  the settings as delivered (`RawStore.tend(settings=...)`).
- **The suite at contract v29:** `an-exact-price`, `a-want-recorded-against`
  and `a-subject-another-source-resolved` presented; a close, a forming
  day, a bar, an FX close and a stablecoin quote named not presented with
  why, as are a derived series and a pool's factor.
- **The pages:** Datasets shows `treasury_prices` alone waiting, and the
  curve's record on the `rates` row alone; Connection's stream row names
  the feeds the standing wants name.
- **The e2e** reads the euro's composite mid of `fx`, its reader a
  `reporting` role class on `meridian.run_async`.

## 0.1.2

SDK 0.33.4: raw-record writes and enum conversion fixes (ruling 937).

- **The pins:** open-meridian 0.33.3 to 0.33.4, and plugin-python:0.33.4 by tag
  and digest (`meridian plugin migrate --to 0.33.4`: only the pins move).

## 0.1.1

A bug fix (ruling 926), until the SDK's own retry helpers replace it (924).

- **A 429 is waited out:** a request Hermes limits is tried again after its
  `Retry-After`, or without one after a backoff of 1, 2 then 4 seconds with
  jitter, at most three times, each counted in Connection's "Limits and use";
  only then is the call failed. Before, the first 429 failed the read.
- **The stream**, refused with a 429, is opened again no sooner than its
  `Retry-After`, and its growing pause carries jitter.

## 0.1.0

The first version: Pyth Network's values from its Hermes API, on
open-meridian 0.33.3 (contract v28) and meridian 0.1.53 (rulings 866, 868,
876, 879, 880 and 893 to 898).

- **Seven datasets, one per family Pyth publishes:** `crypto`, `fx`,
  `equity`, `metal`, `commodities`, `rates` and `treasury_prices`, vendor
  Pyth Network, each licence default what Pyth's subscription terms say.
- **`rates` records:** Pyth's US Treasury constant-maturity par yields, 2
  to 30 years, as points of Treasury's par yield curve record -- a par yield,
  bond-equivalent, its published time Pyth's -- the latest, a business
  date at its 17:00 New York close, and a standing want kept current from
  Hermes' stream, each tenor at most every five minutes.
- **The price families wait** for the contract-28 amendment's composite
  price kind and confidence interval: declared, every want declined, no
  price recorded under another kind; the conversion ready behind one
  adapter (prices.py). **`treasury_prices` waits** for v29's bond template.
- **The key:** the deployment's Pyth API key, a secret setting, sent to
  Hermes as a bearer token and nowhere else. Without it, only Pyth's feed
  catalogue is read.
- **Sample data:** Pyth's catalogue as Hermes answered it on 2026-10-30,
  cut to a few feeds, and made-up prices in Hermes' shape. No key needed.
- The data role's two pages, Connection and Datasets, each a read tool; the
  data suite; the e2e on the plugin harness of core 8def82a.
