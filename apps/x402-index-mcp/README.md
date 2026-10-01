# x402-index-mcp

A stdio MCP server for the x402 Clean Index (ORDER_011 Module A).
- **SDK:** official MCP Python SDK `mcp==2.2.0`, where FastMCP is now `MCPServer`.
- **Why Python:** the index pipeline is Python and writes CSV/JSON, so the server reads them directly.

| Tool | Returns |
|---|---|
| `latest_week()` | headline numbers and the content+data tripwire |
| `weekly_series(stage, category)` | weekly payments/USD/sellers/buyers; stage raw, d05 or clean; category content, data, search, compute, other, large_ticket, unclassed or all |
| `top_sellers(category, n)` | top cleaned sellers by USD in the latest week |
| `price_stats(category)` | posted and transacted price per call, with chain-linked index |
| `method()` | key definitions from docs/X402_INDEX_METHOD.md |
| `price_comps(find, category)` | comparable x402 listings for a described API: posted price distribution, share whose sellers have 5+ genuine buyers, realised price. **Needs a wallet** for every comparable (paid `GET /v1/comps`, $0.001); without one, the free summary with the 5 closest |
| `best_execution(need, max_price_usd, verified_only, n)` | x402 endpoints for a task, ranked by price, the daily 402 check and genuine buyers. **Needs a wallet** for the full ranking (paid `GET /v1/route`, $0.001 per call); without one it returns the free three-pick demo |

## Install
```
cd apps/x402-index-mcp && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python test_server.py        # spawns the server over stdio and calls every tool; exit 0 = pass
```
- **Claude Code:** `claude mcp add x402-index -- $PWD/.venv/bin/python $PWD/server.py`
- **Claude Desktop:** see docs/WES_SETUP_011.md §5.

## Configuration
| Variable | Meaning | Default |
|---|---|---|
| `X402_INDEX_DATA` | folder with weekly.csv, prices_weekly.csv, payees_weekly.csv, headline.json | `../../data/x402_index` |
| `X402_INDEX_API` | remote mode, e.g. `https://api.wknipe.com` | unset |

| `X402_PAYER_PRIVATE_KEY` | Base wallet key that pays for `best_execution()`'s full ranking and `price_comps()`'s full list (`pip install "x402[httpx,evm]==2.25.0"`) | unset: free demo only |
| `X402_MAX_PRICE_USD` | refuse to pay more than this per call | `0.01` |

In remote mode, `latest_week()` and `method()` use the public API's free routes. The other tools stay local: their API routes cost $0.001 per call over x402, and this server holds no wallet.
