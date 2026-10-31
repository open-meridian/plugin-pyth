# Changelog

## 0.1.2 (2026-10-30)

SDK 0.33.4: raw-record writes and enum conversion fixes (ruling 937).

- **The pins:** open-meridian 0.33.3 to 0.33.4, and plugin-python:0.33.4 by tag
  and digest (`meridian plugin migrate --to 0.33.4`: only the pins move).

## 0.1.1 (2026-10-30)

A bug fix (ruling 926), until the SDK's own retry helpers replace it (924).

- **A 429 is waited out:** a request Hermes limits is tried again after its
  `Retry-After`, or without one after a backoff of 1, 2 then 4 seconds with
  jitter, at most three times, each counted in Connection's "Limits and use";
  only then is the call failed. Before, the first 429 failed the read.
- **The stream**, refused with a 429, is opened again no sooner than its
  `Retry-After`, and its growing pause carries jitter.

## 0.1.0 (2026-10-30)

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
