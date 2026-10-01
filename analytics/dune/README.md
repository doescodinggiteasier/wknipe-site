# Dune queries (run while the trial lasts, ~2026-10-13)

None of these has been run by Claude (no Dune access). Paste any error back; the usual fixes are column names.
Run each as a new DuneSQL query, then Export → CSV into `data/dune/` (any file name) or send it to Claude.

Done:
- `x402_solana_candidates.sql` → `data/x402_solana/candidates_2026-09-21.csv`: the biggest Solana fee sponsors; not x402.
- `x402_solana_weekly.sql` → `data/x402_solana/weekly_by_facilitator.csv`: 5 weeks through the 27 published facilitators.

Next, in priority order:
1. `1_x402_base_history.sql` (Base since launch, weekly by facilitator). The index has 5 weeks; this gives 17 months.
   The week of 21 Sep should total 593,454 settlements / $134,479, which doubles as a check of the Blockscout pipeline.
2. `2_x402_solana_history.sql` (Solana since launch, daily by facilitator). Dates the PayAI collapse.
3. `3_x402_solana_missing_facilitators.sql`: x402-shaped transfers whose fee payer is not in the list (coverage check).
4. `4_x402_solana_sellers.sql`: Solana sellers for 21-27 Sep, with buyers, repeat buyers and top-buyer share.
5. `5_x402_solana_funding.sql`: who first funded each Solana buyer (the shared-funding filter, Solana version).
6. `6_usdc_context.sql`: all USDC transfers per week on both chains, the denominator for "x402's share".

Optional, already written: `x402_base_weekly.sql` and `x402_base_top_payees.sql` (one-week Base checks, ORDER_011).
If something times out, each file says which date to move to make it smaller.

## Results (run by Claude via the API, 2026-10-01; credits in local/dune_ledger.jsonl)
- Base check (`x402_base_weekly.sql`, 0.7 cr): Dune found 655,692 settlements in week 09-21 vs 593,454 collected from
  Blockscout. Hourly comparison located the gap (Blockscout 5xx hours on 21-22 and 25-26 Sep); `scripts/dune/patch_week.py`
  filled weeks 08-24 and 09-21 from Dune. Weeks 08-31, 09-07, 09-14 matched exactly.
- `1_x402_base_history.sql` (187 cr): 73 weeks, peak week of 10 Nov 2025 at $9.78M (86% single-buyer sellers). On /x402/.
- `3_...missing_facilitators.sql` (17 cr; a first version timed out at 30 min): the 27 listed fee payers reconcile with step 2;
  13 unlisted fee payers look x402-like but cannot be confirmed (the Bazaar lists no Solana payTo). Not counted.
- `4_x402_solana_sellers.sql` (11 cr): week 09-21, $75,215 of $84,250 went to one seller from one buyer in 21 payments.
- `5_x402_solana_funding.sql` (166 cr): no large shared-funding clusters (3 funders behind 10+ buyers, $1.2k in all).
- `2_x402_solana_history.sql` (291 cr): Solana peaked Dec 2025 ($6.3M in the month); PayAI fell from 949k payments on
  7 Sep 2026 to 16k a day from 9 Sep.
- `6_usdc_context.sql` (11 cr): x402 is ~2.8% of Base USDC transfers by count, <0.1% on Solana.
Lesson: on Solana, use tokens_solana.transfers.tx_signer (the fee payer) instead of joining solana.transactions.
