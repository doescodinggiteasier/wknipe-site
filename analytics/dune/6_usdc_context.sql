-- 6. Denominator: all USDC transfers per week on Base and Solana, 24 Aug - 27 Sep.
-- Puts x402 in context ("x402 is N% of USDC transfers by count, M% by value").
SELECT 'base' AS chain, date_trunc('week', evt_block_time) AS week, COUNT(*) AS transfers, SUM(CAST(value AS DOUBLE)) / 1e6 AS usd,
       COUNT_IF(CAST(value AS DOUBLE) < 1e6) AS transfers_under_1_usd
FROM erc20_base.evt_Transfer
WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND evt_block_date >= DATE '2026-08-24' AND evt_block_date < DATE '2026-09-28'
GROUP BY 1, 2
UNION ALL
SELECT 'solana', date_trunc('week', block_time), COUNT(*), SUM(amount) / 1e6, COUNT_IF(amount < 1e6)
FROM tokens_solana.transfers
WHERE token_mint_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AND block_time >= TIMESTAMP '2026-08-24' AND block_time < TIMESTAMP '2026-09-28'
GROUP BY 1, 2 ORDER BY 1, 2;
