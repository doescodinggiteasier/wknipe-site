# x402 Clean Index: method (v0, ORDER_010)

A weekly index of what buyers pay for on the x402 agent-payment network on Base, after removing activity that is provably manufactured and single-buyer dust, with every seller put in a category. Raw x402 trackers (x402scan) report gross volume. This index reports the part that survives cleaning, split by what was bought, plus posted and transacted prices per call.

All inputs are public and free: Blockscout (Base), the Coinbase CDP Bazaar discovery listing, and the ORDER_001 x402scan resource pull. Code is in `scripts/x402_index/`.

## 1. Units and definitions
- **Week:** Monday 00:00 to Sunday 23:59:59 UTC. Base produces one block every 2 s, so week *w* spans blocks `51,579,727 + (w − 2026-09-21)/2 s` for 302,400 blocks. The anchor matches the ORDER_004 J.1 range (51,579,727–51,882,126), and Blockscout block timestamps were checked at both ends.
- **Settlement (raw):** a successful USDC `transferWithAuthorization` call on Base, either signature variant (`0xe3ee160e` EOA, `0xcf092995` smart wallet), whose transaction sender is one of the 128 known facilitator addresses (`data/x402/base_facilitators_2026-09-27.json`). The payer is the authorizer, the payee is the recipient, and the amount is the USDC value. Rows are de-duplicated by transaction hash.
  - **Excluded:** Permit2 and batch proxy settlements (411 + 49 + 43 transactions, about $23, in week 2026-09-21), and other calls facilitators send (about 14.5k transactions that are not payer-resolved settlements).
- **Seller** = payee address. **Buyer** = payer address.

## 2. Filters (in this order)
1. **D05-approx manufacture filter**, after arXiv 2607.12575 (D05), approximated as in `scripts/o5/x402_filter.py`:
   - **C1 fictitious:** payer = payee, or payer and payee sit in the same strongly connected component of the week's payer→payee graph (a closed payment loop).
   - **C2 internal:** payer and payee fall in the same funding-linked cluster. Links come from Blockscout's newest 50 non-settlement USDC transfers in (payers' top-ups) and out (payees' sweeps) of the busiest addresses. Coverage runs until those addresses carry 90% of settlement endpoints, capped at 300 lookups a week. Counterparties that are contracts or named/tagged (exchanges, routers, bridges) are not linked.
   - C3 = everything else is kept.
2. **Fan-out manufacture check** (added 2026-09-30 after the 0x8a12… case: 874 one-time buyers, 10 of 12 sampled funded by three wallets). It covers the 20 largest cleaned sellers whose buyers mostly pay once (payments ÷ buyers ≤ 1.25, at least 20 buyers).
   - **Sample:** 12 buyers per seller; read each one's newest 50 incoming non-settlement USDC transfers.
   - **Flag a seller only when both hold:**
     - untagged funders that each funded 2 or more sampled buyers together funded at least 8 of the 12; **and**
     - the money is either **circular** (the seller's sweeps go to one of those funders) or **isolated** (at least 10 of the 12 sampled buyers pay no other seller that week).
   - **Why shared funding alone isn't enough:** it usually marks one operator running an agent fleet, which is real demand. On 2026-09-30, the buyers of most shared-funder sellers paid them 6–340 times each and also bought from other sellers.
   - Flagged sellers leave the cleaned set. Results are in `state/x402_index/fanout_<week>.json` and `headline.json` → `fanout_flagged`.
3. **Our own traffic:** payments to or from our addresses (`common.OURS`) are dropped before any filter:
   - the index API's payTo `0x6ac8…fbf9`;
   - the agent test wallet `0x5917…c013`.
4. **S385 dust filter:** after step 1, drop every seller paid by exactly one distinct buyer in the week.
5. **Clean** = what survives all of the above.

## 3. Categories
Every seller gets exactly one of the categories below. The model definitions are in `scripts/x402_index/classify.py` (`SYSTEM`).
- **content:** editorial or creative works (news, articles, reports, books, courses, media, paywalled pages).
- **data:** structured lookups (market, token and on-chain data, enrichment, public records, weather, sports, signals).
- **search:** web search, SERP, scraping, crawling, arbitrary page fetch.
- **compute:** the seller runs something on the buyer's input (LLM inference, generation, transcription, conversion, storage, utilities such as DNS or email checks).
- **other:** mints, memes, games, commerce, swaps, agent infrastructure (attestation, verification, trust scores), tests.
- **large_ticket (unidentified):** an unlisted seller whose median cleaned payment is above the 99th percentile of posted per-call prices. This is a label from price alone, not an identification; see the unlisted-seller review below.
- **unclassed:** the seller has no listing in any snapshot we hold.

**Evidence and precedence.**
- Evidence is the text (URL, name, category, tags, description) of every resource that names the seller as `payTo` on Base, in every Bazaar snapshot in `state/bazaar/` plus the ORDER_001 x402scan pull.
- Precedence, highest first:
  1. The ORDER_010 hand checks:
     - `data/x402_index/handcheck_30.csv` (30 random new sellers);
     - `data/x402_index/content_audit.csv`: **every** seller the pipeline had called content across the collected weeks (45). 17 were not content, including the largest, a livestream shout-out seller ($35). Content is small enough to audit in full each week, so do.
  2. The ORDER_002 hand labels for content/data (`data/o2_payees_reviewed.csv`, 355 sellers).
     - Where ORDER_002 said "not content/data", the model's search / compute / other split is kept.
     - If the model says content or data there, the seller is set to other (25 sellers).
  3. The model label (`data/x402_index/payee_classes.csv`, cached, so a rerun never re-asks).
  4. The unlisted-seller review (`data/x402_index/unlisted_review.csv`, below).
  5. unclassed.

**Unlisted-seller review (Wes, 2026-09-30: classify the top unclassed sellers until unclassed is under 25% of clean USD).**
- **Why these sellers are hard.** They have:
  - no listing in any snapshot;
  - no Blockscout name or tag;
  - buyers who pay no other seller;
  - real-USDC sweeps to single unlabelled wallets, sometimes bridged out through a USDC token pool, and surrounded by address-poisoning spam.
  So what they sell can't be read from free public data. x402scan's seller pages render client-side, and its API is paid; neither was used.
- **The one label the evidence supports.** `scripts/x402_index/review_unlisted.py` walks each week's unclassed cleaned sellers by USD, largest first. It stops when unclassed falls under 25% or when the next seller has no supporting evidence.
  - A seller gets **large_ticket (unidentified)** only if its median cleaned payment is above the 99th percentile of posted per-call prices ($1.25 in the 2026-09-30 snapshot; 1.5% of listed offers cost $1 or more).
  - Chain evidence (2026-09-30) shows these include B2B-sized transfers (0xffde…, $434–$7,652 tickets, bridged out) and consumer-app purchases from smart wallets that may be compute jobs (0x9386…, fixed $18 / $10.79 / $2.69 tiers). So the label says only that it isn't a metered per-call price.
  - It never assigns content or data, so **the tripwire does not depend on it**.
  - Each reviewed seller is written with its evidence: median ticket, top ticket tiers, buyers, sweep destinations.
- **Sensitivity.** Undo the review by deleting the CSV and rerunning `run.py`. The large_ticket figures then fall back into "unclassed" and nothing else moves.
- **Honest limit:** week 2026-09-07 stays at 36% unclassed. Its remaining unlisted sellers are priced like API calls, so the evidence supports no label.

**Model choice (pilot; working file not published, results below).** Candidates were scored against the 355 ORDER_002 hand labels on content / data / neither.

| Classifier | Agreement | Content+data precision | Content+data recall |
|---|---|---|---|
| keyword rules v2 (`scripts/x402/analyse_week.py`) | 59.2% | 0.686 | 0.946 |
| qwen/qwen3-30b-a3b-instruct-2507 | 83.4% | 0.900 | 0.893 |
| google/gemini-2.5-flash-lite | 83.7% | 0.879 | 0.930 |
| **mistralai/mistral-small-3.2-24b-instruct** (chosen) | **86.8%** | 0.905 | 0.946 |

- Mistral Small 3.2 is best on every column, at under $0.03 per 355 sellers.
- The `:batch` variant of Gemini Flash Lite stalled (no responses within minutes), so it was dropped.

**Fresh hand check (`data/x402_index/handcheck_30.csv`).**
- Sample: 30 sellers not in the ORDER_002 set, seed 10010.
  - 15 were paid in the cleaned week 2026-09-21.
  - 15 were drawn from the other listed new sellers.
- ClCo labelled them from the listing text before seeing the model label.
- Agreement:
  - All five categories: **20/30 = 67%** (Wilson 95% CI 49–81%).
  - Content / data / neither: **24/30 = 80%** (CI 63–91%).
- Errors cluster on:
  - thin listings (one bare URL);
  - verification or trust tools (other vs compute);
  - page fetchers (search vs data).
- One thin listing (x402station "watch / whats-new") was called content. Content is a small number (tens of dollars a week), so single misclassifications move it. Read the content line with that in mind.

## 3a. Reading the tripwire (analysis 2026-09-30, `data/x402_index/analysis.json`)
- **Content + data is concentrated.** One DefiLlama/CoinGecko price-lookup reseller (0xe903…) was 64% of it in 2026-09-07, and its drop explains the week's −61%. Continuing sellers account for −$2,522 of the −$2,489 change.
- **A single-seller swing moves the number more than market growth does.** Read the tripwire together with:
  - content + data **excluding the top seller**;
  - the count of content/data sellers with at least 10 buyers.
  Whether to switch the tripwire definition is Cowork's call.
- **Sensitivity of cleaned USD, week 2026-09-21:**
  - $73.3k as published;
  - $70.2k with the dust threshold at 5 buyers;
  - **$46.3k excluding single payments above $100**;
  - $74.8k without the fan-out check.

## 4. Prices
- **Posted:** every Bazaar snapshot is one observation for the week that contains its date. Price = the exact-scheme Base USDC `amount` (atomic ÷ 10⁶), per resource (resource URL + payTo, median if a pair repeats).
  - "upto", batch and other schemes are excluded; so are other chains and assets.
  - Per category we report the resource count, median and IQR.
  - The index is chain-linked Jevons: index_t = index_{t−1} × geometric mean of p_t/p_{t−1} over resources listed with a positive price in both weeks. The first week = 100.
  - Churn is reported as `basket_items` (continuing), `entered`, `exited`.
- **Transacted:** per cleaned seller, the median payment in the week, with the same chain-linked Jevons over sellers paid in consecutive weeks. It can be backfilled from chain data, unlike posted prices. It moves with a seller's product mix as well as its prices.

## 5. Outputs
| File | Content |
|---|---|
| `data/x402_index/weekly.csv` | week × stage (raw, d05, clean) × category (+ all): payments, USD, sellers, buyers |
| `data/x402_index/prices_weekly.csv` | week × measure (posted, transacted) × category: items, median, p25, p75, index, basket, entered, exited |
| `data/x402_index/payees_weekly.csv` | cleaned sellers per week with category, source of the label, payments, USD, buyers, median payment |
| `data/x402_index/headline.json` | latest week, tripwire, filter diagnostics per week |
| `site/x402_index/index.html` | the static page (artifact content: no `<html>`/`<head>`/`<body>`, inline SVG, fonts from Google Fonts only) |

## 6. Known biases
- **The manufacture filter is a lower bound.**
  - C1 sees only loops closed on the settlement layer inside one week.
  - C2 sees only funding links among the ~300 busiest addresses, and only in each address's newest 50 transfers at lookup time, not at the week's date.
  - So the cleaned figures are an **upper bound on genuine demand**. D05 itself found 84.98% of Base x402 settlements operator-internal; we remove far less.
- **Dust is a crude proxy.** A real seller with one real buyer in a week is dropped. A manufacturer using two wallets is kept.
- **Categories are inferred from sellers' own listing text by a model** (80% on content / data / neither in the blind check). Sellers with no listing are unclassed.
  - In 2026-09-21, unclassed carried **$50,365 of $74,798** cleaned.
  - Three unlisted sellers alone carried $44.5k: 0xffde…6003 (10 payments, median $1,042), 0x9386…ca25 and 0x47d3…9dda.
  - Blockscout has no name tags for any of them. After the unlisted-seller review, the first two count as other (large ticket, inferred); see §3.
- **Base only.** Solana x402 is not counted, although 6,205 of 19,076 Bazaar resources (33%) accept Solana. On-chain Solana volume was not measured. It is the first v1 item.
- **Listing concentration.** The largest listed seller holds 7.2% of Base exact-scheme offers (1,374 of 19,211, snapshot 2026-09-30), and the top six hold 28%. Posted medians are therefore resource-weighted, not seller-weighted.
- **Facilitator list is fixed** at 2026-09-27. A new facilitator is invisible until it is added. Settlements that bypass facilitators (direct transfers) are not x402 by this definition.
- **Posted-price history starts 2026-09-21.** The Bazaar has no history API, so the posted index can't be backfilled. The transacted index can.

## 7. Weekly run
```
export OPENROUTER_API_KEY=$(security find-generic-password -s openrouter -w) && python3 scripts/x402_index/run.py --weekly
```
- **Steps:** Bazaar snapshot (~1 min), collection of last Monday–Sunday (**~3 h**), classification of new sellers (seconds, ~$0.01), build and page (minutes; funding lookups are cached).
- **Rebuild only:** `python3 scripts/x402_index/run.py` rebuilds everything from cached data in under a minute, with no keys needed.
- **Why collection takes ~3 h:** Blockscout allows about 150 v2 calls per 5 min and about 10 v1 calls per 40 min (headers, observed 2026-09-30). A busy week is ~600k transactions. The collector uses both limits and never exceeds them.
- **Scheduling (plan only, not set up):** run on Mondays after 03:00 UTC, when the previous week is complete. Any scheduler that can run a shell command on this Mac works (cron, launchd, a Claude Code scheduled task). Commit `data/x402_index/` and `site/x402_index/` afterwards.
