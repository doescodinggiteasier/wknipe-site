-- x402 on Solana, step 2 (rewritten 2026-09-30 after step 1): weekly volume through the KNOWN x402 facilitators.
-- Step 1 (x402_solana_candidates.sql) ranked every Solana wallet that pays fees for other people's USDC transfers.
-- Its top 100 were all non-x402 gas sponsors (wallets, exchanges, relayers: up to $1.45B a week, medians of $1-$500)
-- and none of the 27 published x402 facilitator fee payers below appeared in it. So this step uses the published list,
-- the same definition as the Base index: a settlement is a USDC transfer in a transaction whose fee payer is a facilitator.
-- Source: Merit-Systems/x402scan packages/external/facilitators (commit f205fbe, 2026-08-17), read 2026-09-30; PayAI's
-- CjNF... is marked deprecated there but facilitator.payai.network/supported returns it as the live mainnet fee payer.
-- Saved as data/x402/solana_facilitators_2026-09-30.json. Weeks are Monday..Sunday UTC, 2026-08-24 .. 2026-09-27.
WITH fac(facilitator, fee_payer) AS (VALUES
  ('anyspend', '34DmdeSbEnng2bmbSj9ActckY49km2HdhiyAwyXZucqP'),
  ('aurracloud', '8x8CzkTHTYkW18frrTR7HdCV6fsjenvcykJAXWvoPQW'),
  ('bitrefill', 'PcTZWki36z5Y82TAATKK48XUdfsgmS5oLkw2Ta7vWyK'),
  ('cascade', '7NetKx8TuRMBpqYFKZCVetkNuvWCPTrgekmGrsJwTmfN'),
  ('codenut', 'HsozMJWWHNADoZRmhDGKzua6XW6NNfNDdQ4CkE9i5wHt'),
  ('coinbase', 'L54zkaPQFeTn1UsEqieEXBqWrPShiaZEPD7mS5WXfQg'),
  ('coinbase', 'BENrLoUbndxoNMUS5JXApGMtNykLjFXXixMtpDwDR9SP'),
  ('coinbase', 'BFK9TLC3edb13K6v4YyH3DwPb5DSUpkWvb7XnqCL9b4F'),
  ('coinbase', 'D6ZhtNQ5nT9ZnTHUbqXZsTx5MH2rPFiBBggX4hY1WePM'),
  ('coinbase', 'GVJJ7rdGiXr5xaYbRwRbjfaJL7fmwRygFi1H6aGqDveb'),
  ('coinbase', 'Hc3sdEAsCGQcpgfivywog9uwtk8gUBUZgsxdME1EJy88'),
  ('coinbase', '92QcYJZpkwYyacR3G69QNR2JfjadQxd16cp5d7x5GEzU'),
  ('corbits', 'AepWpq3GQwL8CeKMtZyKtKPa7W91Coygh3ropAJapVdU'),
  ('daydreams', 'DuQ4jFMmVABWGxabYHFkGzdyeJgS1hp4wrRuCtsJgT9a'),
  ('dexter', 'DeXterR2kQm8AvRHnNPatWkE46TfAcMeBDjb6FySoAb8'),
  ('dexter', 'DEXVS3su4dZQWTvvPnLDJLRK1CeeKG6K3QqdzthgAkNV'),
  ('figment', '93syNmtT1tTd5ZtPwHqzGf6CM7fKhMmArpv4AM4FtyNX'),
  ('openfacilitator', 'Hbe1vdFs4EQVVAzcV12muHhr6DEKwrT9roMXGPLxLBLP'),
  ('openx402', '5xvht4fYDs99yprfm4UeuHSLxMBRpotfBtUCQqM3oDNG'),
  ('payai', '2wKupLR9q6wXYppw8Gr2NvWxKBUqm4PPJKkQfoxHDBg4'),
  ('payai', 'CjNFTjvBhbJJd2B5ePPMHRLx1ELZpa8dwQgGL727eKww'),
  ('payai', '8B5UKhwfAyFW67h58cBkQj1Ur6QXRgwWJJcQp8ZBsDPa'),
  ('relai', '4x4ZhcqiT1FnirM8Ne97iVupkN4NcQgc2YYbE2jDZbZn'),
  ('threews', 'WwwuGbqHrwF5RG89KhUbmRWEvjnRH9k5kVM5p7T3WwW'),
  ('threews', 'GGf9qBhJDCe1UUz4s4Vxq1uPPvcv7UW7sJTuj2Yo5XQj'),
  ('ultravioletadao', 'F742C4VfFLQ9zRQyithoj5229ZgtX2WqKCSFKgH2EThq'),
  ('x402jobs', '561oabzy81vXYYbs1ZHR1bvpiEr6Nbfd6PGTxPshoz4p')
),
tx AS (
  SELECT s.id AS tx_id, f.facilitator
  FROM solana.transactions s JOIN fac f ON f.fee_payer = s.signer
  WHERE s.block_time >= TIMESTAMP '2026-08-24' AND s.block_time < TIMESTAMP '2026-09-28' AND s.success
),
x AS (
  SELECT date_trunc('week', t.block_time) AS week, tx.facilitator, t.tx_id, t.amount / 1e6 AS usd,
         t.from_owner AS payer, t.to_owner AS payee
  FROM tokens_solana.transfers t JOIN tx ON tx.tx_id = t.tx_id
  WHERE t.token_mint_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
    AND t.block_time >= TIMESTAMP '2026-08-24' AND t.block_time < TIMESTAMP '2026-09-28'
    AND t.from_owner <> t.to_owner
),
payee_buyers AS (SELECT week, payee, COUNT(DISTINCT payer) AS buyers FROM x GROUP BY 1, 2)
SELECT x.week, x.facilitator,
       COUNT(*) AS payments, SUM(x.usd) AS usd, APPROX_PERCENTILE(x.usd, 0.5) AS median_usd,
       COUNT(DISTINCT x.payer) AS payers, COUNT(DISTINCT x.payee) AS payees,
       SUM(CASE WHEN pb.buyers >= 2 THEN x.usd ELSE 0 END) AS usd_after_single_buyer_filter
FROM x JOIN payee_buyers pb ON pb.week = x.week AND pb.payee = x.payee
GROUP BY 1, 2
ORDER BY 1, usd DESC;
