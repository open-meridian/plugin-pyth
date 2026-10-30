# Setup

## The Pyth API key

Since 26 August 2026 Pyth's Hermes API asks for an API key on every price:
without one, Hermes answers only its feed catalogue. The key comes from a
Pyth Terminal account, under a Pyth plan your organisation chooses:

- **Free:** no API access.
- **Starter:** API access for crypto symbols.
- **Pro:** every family -- equities, currencies, metals, commodities,
  US Treasuries and rates -- with display and non-display rights.

Pyth's plans page has the current prices. The plugin works with whatever
the key's plan serves; a feed the plan does not serve is refused by Hermes,
and Connection says so.

## Launching it

1. Launch the plugin and approve its one role, `data` (a data plugin).
2. In the dashboard's Settings form, enter the **Pyth API key**. It is a
   secret setting: no page, tool or log shows it, and the plugin sends it
   to Hermes alone.
3. Its other settings: **Raw responses window** and **past the window**
   (the SDK's), how long Hermes' answers are kept in the plugin's storage, a
   month by default; and **Sample data**, on a deployment installed for
   development only: Pyth's feed catalogue and made-up prices in Hermes'
   shape, committed with the plugin, in place of Hermes. No key needed.

## Its datasets

On the deployment's **Data sources** page (deployment admins):

1. **License** `<instance>:rates`, and the other datasets when they record.
   Each catalogue default is what Pyth's subscription terms say: kept, for
   your internal business use, displayed in your own products, derived use
   not restricted, no redistribution. Confirm it, or set your own, with a
   note saying why.
2. **Entitle** each plugin that reads rates, such as your reporting or
   analytics plugin.
3. **Priority**, where the US Treasury plugin records the same curve: put
   the one your readers should read first.

## The curve's record

The `rates` rows are about one record, the platform's seeded US Treasury
par yield curve, found by Treasury's title as a `symbol` scoped to
`ustreasury`. If your deployment does not hold it, pull it from the
platform at the Instruments page; the plugin asks again within the hour.
