# Troubleshooting

## Connection

| What you see | What it means | What to do |
|---|---|---|
| **No key** | No Pyth API key is set: Hermes serves only its catalogue | Enter the key in Settings |
| Last error: *refused the request (401)* | Hermes did not accept the key, or it is missing | Check the key in your Pyth Terminal account, and enter it again |
| Last error: *refused the key (403)* | The key's plan does not serve that feed | A Starter plan serves crypto alone; Pro serves every family |
| Last error: *limiting this key's requests (429)* | The plan's rate limit was reached | Nothing, usually: the plugin asks one request at a time and waits a 429 out, as long as Hermes' `Retry-After` asks or a short backoff, up to three times; seen often, the plan allows fewer requests than the wants ask |
| **Not answering** | Hermes could not be reached | Check the deployment's outbound access to hermes.pyth.network |

## Wants and datasets

| What you see | What it means | What to do |
|---|---|---|
| A price declined, *not covered* | The price datasets wait for the contract revision that adds Pyth's composite price | Nothing yet: the version that pins it records them |
| `treasury_prices` declined, *not covered* | The on-the-run Treasuries wait for the bond template | Nothing yet |
| `rates` declined, *not covered* | The want named a record other than the par yield curve's | Read the par yield curve's record |
| `rates` declined, *source silent* | Hermes answered nothing: no key, a plan without rates, or a refusal | See Connection's last error |
| `rates` declined, *beyond history* | Hermes holds no value at that day's close | Nothing: Pyth published none then |
| Datasets: **Not licensed yet** | No deployment admin has licensed the dataset | Ask a deployment admin to license it on Data sources |
