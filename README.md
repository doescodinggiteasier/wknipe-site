# wknipe.com

Source, data and pipeline for [wknipe.com](https://wknipe.com): measurements of how AI agents find, judge and pay for information.

| Path | What it is |
|---|---|
| `site/` | The Quarto website. `cd site && quarto render` builds `_site/`; it is served by the Cloudflare Worker `wknipe` (static assets). |
| `scripts/x402_index/` | The **x402 Clean Index** pipeline: collect Base x402 settlements from Blockscout, remove manufactured and single-buyer volume, classify sellers, build weekly series and prices. |
| `data/x402_index/` | The published index: `weekly.csv`, `prices_weekly.csv`, `payees_weekly.csv`, `headline.json`, and the hand-audit files behind the categories. |
| `state/` | Compact pipeline state that lets anyone rebuild the published numbers exactly: Bazaar listing snapshots (text + Base offers only), per-week filter results, the Blockscout funding-link cache. |
| `docs/X402_INDEX_METHOD.md` | Method note: every filter, category rule and known bias. |
| `apps/x402-index-api/` | `api.wknipe.com`: free and x402-paid JSON endpoints (Cloudflare Worker, Hono). |
| `apps/x402-index-mcp/` | An MCP server exposing the index to Claude Desktop / Claude Code. |
| `.github/workflows/weekly.yml` | Every Monday 14:00 UTC: collect last week → rebuild → commit data → render → deploy. |

## Rebuild the published numbers

Python 3.12, standard library only; no keys needed to rebuild from `state/`.

```bash
X402_STATE=state python3 scripts/x402_index/run.py
git diff --stat data/   # should be empty: the committed data is exactly what the committed state produces
```

Collecting a new week needs no keys either (public Blockscout, ~3 h inside its published rate limits); classifying
sellers never seen before needs an OpenRouter key:

```bash
X402_STATE=state OPENROUTER_API_KEY=... python3 scripts/x402_index/run.py --weekly
```

## Citing

Knipe, W. (2026). *x402 Clean Index*. https://wknipe.com/x402/

## License

- **Code:** MIT — see [`LICENSE`](LICENSE).
- **Data, essays and charts:** CC BY 4.0 — see [`LICENSE-CONTENT.md`](LICENSE-CONTENT.md). Please cite as: Knipe, W. (2026). *x402 Clean Index*. https://wknipe.com/x402/
