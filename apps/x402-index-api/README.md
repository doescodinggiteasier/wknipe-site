# x402-index-api

The public JSON API for the x402 Clean Index (ORDER_011 Module C). It runs as a Cloudflare Worker on Hono, with the x402 v2 middleware.

| Route | Price |
|---|---|
| `GET /v1/latest`, `/v1/method`, `/v1/metrics`, `/v1/series?metric=NAME` | free, 60 calls/min per client; over that, $0.001 per call |
| `GET /v1/route/demo?need=` | free (three picks; the demo on /x402/buy/), same 60/min |
| `GET /v1/check?domain=`, `/v1/probe?url=` | free, 30/min per client (they fetch third-party sites, so no paid overflow) |
| `GET /v1/series?stage=clean&category=all` | $0.001 per call |
| `GET /v1/sellers?category=all&n=20` | $0.001 per call |
| `GET /v1/seller?address=0x…` | $0.001 per call (one seller's full weekly series) |
| `GET /v1/comps/demo?find=&category=` | free (summary, histogram, 5 closest; the Price comps page), 60/min |
| `GET /v1/comps?find=&category=` | $0.001 per call (every comparable with seller buyers and realised price) |
| `GET /v1/route?need=&max_price=&verified=1&n=20` | `ROUTE_PRICE` per call (wrangler.jsonc; $0.001) |

Settled paid calls are counted per UTC day and route in the `CHECK_CACHE` KV namespace (`paid:v1:YYYY-MM-DD:route`); nothing about the payer is stored. Read them with `npx wrangler kv key list --binding CHECK_CACHE --prefix paid: --remote`.

Paid routes settle in USDC on Base mainnet (`eip155:8453`), `exact` scheme, to payTo `0x6ac87b6a48e329e2557c7f6054ed1518be76fbf9`.

**Facilitator:** PayAI's public facilitator, `https://facilitator.payai.network`. Its `/supported` endpoint lists v2 `exact` on `eip155:8453` and needs no API key.
- The Coinbase CDP facilitator needs CDP API keys.
- `x402.org/facilitator` and `facilitator.x402.rs` list testnet only (checked 2026-09-30).
- PayAI is on our facilitator list, so payments to this API appear in the index data. There they are excluded as ours (`scripts/x402_index/common.py` `OURS`).

**Data:** `npm run build:data` bundles `data/x402_index/` into `src/data.json`. Nothing is read at runtime, so a redeploy is how data updates.

**Versions:** hono 4.13.11, @x402/hono, @x402/core and @x402/evm 2.28.0, wrangler 4.144.0.

```
npm install
npm run dev            # wrangler dev on :8787
npm test               # smoke: free routes 200, paid routes 402 with Base USDC exact 1000-atomic requirements
npm run deploy         # needs `npx wrangler whoami` to show Wes's account
```
