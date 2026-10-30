# Pages

Both pages are the data role's, the same on every data plugin, under
**Manage**, for the plugin's admins. Neither shows a price or a rate. Each
is also a read tool on the deployment's MCP, answering what the page shows,
under the same names on every data plugin.

## Connection (`read_connection`)

How the plugin reaches Hermes:

- **Key:** the mode (Live, No key or Sample data), whether the Pyth API key
  is set -- never its value -- and what the key's plan serves;
- **Limits and use:** Pyth's limits are its plan's; the requests made, the
  last call and the last error; and **Catalogue**, when Pyth's feed
  catalogue was read and how many feeds each dataset holds. Its `…` opens
  each dataset with its feeds and whether it records now or why it waits;
- **Stream:** whether Hermes' stream is open, and how many events it has
  sent.

## Datasets (`read_datasets`)

What the plugin serves:

- **Served:** its seven datasets as the deployment's catalogue lists them,
  with the terms each declares and whether a deployment admin has licensed
  it, what it recorded and declined; and **Presented**: Yes, or Waits, with
  why;
- **Wants:** the standing wants it keeps current, and the last wants it
  answered; **Subjects**.
