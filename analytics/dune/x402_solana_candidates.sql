-- ORDER_013 (prepared for Wes; run on Dune before the trial ends ~2026-10-13). x402 on Solana, step 1: find facilitators.
-- In the x402 SVM "exact" scheme the buyer signs a USDC transfer and the FACILITATOR pays the transaction fee, so
-- x402 settlements are USDC transfers whose fee payer (first signer) is not the token owner who authorised them.
-- This lists the fee payers that sponsor the most such transfers: candidates to check against known facilitators
-- (PayAI, Coinbase CDP, etc.) before step 2. Week = Monday..Sunday UTC.
WITH usdc AS (
  SELECT t.block_time, t.tx_id, t.amount / 1e6 AS usd, t.from_owner, t.to_owner
  FROM tokens_solana.transfers t
  WHERE t.token_mint_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
    AND t.block_time >= TIMESTAMP '2026-09-21' AND t.block_time < TIMESTAMP '2026-09-28'
), tx AS (
  SELECT id AS tx_id, signer AS fee_payer FROM solana.transactions
  WHERE block_time >= TIMESTAMP '2026-09-21' AND block_time < TIMESTAMP '2026-09-28' AND success
)
SELECT tx.fee_payer, COUNT(*) AS sponsored_transfers, COUNT(DISTINCT u.from_owner) AS payers,
       COUNT(DISTINCT u.to_owner) AS payees, SUM(u.usd) AS usd, APPROX_PERCENTILE(u.usd, 0.5) AS median_usd
FROM usdc u JOIN tx ON tx.tx_id = u.tx_id
WHERE tx.fee_payer <> u.from_owner
GROUP BY 1
HAVING COUNT(DISTINCT u.from_owner) >= 20
ORDER BY sponsored_transfers DESC
LIMIT 100;
