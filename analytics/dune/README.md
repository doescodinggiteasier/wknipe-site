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
