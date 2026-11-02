# Overview

Pyth Network publishes prices for crypto assets, currencies, US equities,
metals, commodities and US Treasuries, each a composite of the prices its
publishers -- exchanges, market makers and trading firms -- send it, with a
confidence interval around it. Its Hermes API serves them. This plugin reads
Hermes with your deployment's Pyth API key and puts Pyth's values into your
deployment's lake.

It is a data plugin: its first-use path, its two pages and its Summary figures are every data plugin's, described once on [Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/). These sections cover what is Pyth's own.

## Its datasets

One dataset per family Pyth publishes:

| Dataset | What it holds | Now |
|---|---|---|
| `crypto` | Crypto assets' prices, such as BTC in USD | Records |
| `fx` | Currencies' prices, such as EUR in USD | Records |
| `equity` | US equities' prices, such as AAPL in USD | Records |
| `metal` | Metals' prices, such as XAU in USD | Records |
| `commodities` | Commodities' prices | Records |
| `rates` | Pyth's US Treasury constant-maturity par yields, 2 to 30 years | Records |
| `treasury_prices` | The on-the-run US Treasuries' clean prices and yields | Waits for the bond template |

## The prices

A Pyth price is a composite of its publishers' prices, with a confidence
interval around it. Each is recorded as what it is:

- **a mid**, the price's kind, in its quote currency -- **BTC 68123.45678901
  USD** exactly as Hermes states it -- with its **confidence interval**
  beside it, in the same unit;
- each price dataset declares its class of source as **composite**, so a
  reader knows a mid here is Pyth's aggregate of its publishers, not one
  venue's book;
- its business date is UTC's date of the second Pyth published it, and that
  second its published time.

A price is asked for a record your deployment holds: the record carrying
Pyth's feed ID, or a code Pyth names its feed by -- a symbol such as `AAPL`
or `BTC`, or a currency's ISO 4217 code such as `EUR` -- priced in the
record's currency, a currency's or a metal's own in US dollars. A record
matching no feed is declined as not covered. A crypto asset Pyth quotes in
another token (ETH in BTC) is not recorded in this version.

## Why the Treasuries wait

`InterestRate.US10Y/USD` and `InterestRate.US10Y`
are the clean price and yield of whichever 10-year note is newest: a
security that rolls to each new issue. They are recorded once your
deployment can describe a bond.

## The rates

Pyth computes a constant-maturity par yield for each of 2, 3, 5, 7, 10, 20
and 30 years through the US Treasury market's day. Each is recorded as a
point of the US Treasury par yield curve -- the same record the US Treasury
plugin records the Treasury's own daily curve against -- with its tenor:

- **10Y 4.11234567** is Pyth's 10-year constant-maturity par yield, in per
  cent, bond-equivalent, exactly as Hermes states it;
- its business date is New York's date of the moment Pyth published it,
  and that moment is its published time;
- through the day each new value of a tenor is the next version of that
  day's row; the day's last stands.

Where both are recorded, your deployment's source priority on Data sources
chooses which a reader reads first. A tenor Pyth has not published is no
row, never a zero.

## When values arrive

- **The latest:** read from Hermes when the lake asks.
- **A past day:** a rate at its close, 17:00 New York; a price at the
  day's last second, UTC.
- **Kept current:** while a reader keeps a standing want, the plugin holds
  Hermes' stream open for exactly the feeds wanted and records each tenor's
  value when it changes, at most every five minutes, and each price when it
  changes, at most once a second.

## What it does not do

- It shows no price or rate on its own pages: values are read by the
  plugins that use them.
- It records no reference rate Pyth relays (SOFR, EFFR, OBFR, BGCR, TGCR):
  Hermes states no effective date for them. The administrator's own plugin
  records them.
- It records no discount factor yet, and no funding rate, redemption rate
  or crypto index.
- It never fits or interpolates a curve.
