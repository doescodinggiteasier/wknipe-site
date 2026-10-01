-- 2. x402 on Solana since launch, DAILY by facilitator (same definition as x402_solana_weekly.sql).
-- Daily so the PayAI collapse (7.4M payments in the week of 24 Aug, 31k in the week of 21 Sep) can be dated exactly.
-- Uses tokens_solana.transfers only: tx_signer is the fee payer (the facilitator in x402's Solana scheme), so no join to
-- the (very large) solana.transactions table is needed.
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
)
SELECT t.block_date AS day, f.facilitator, COUNT(*) AS payments, SUM(t.amount / 1e6) AS usd,
       APPROX_PERCENTILE(t.amount / 1e6, 0.5) AS median_usd, COUNT(DISTINCT t.from_owner) AS payers, COUNT(DISTINCT t.to_owner) AS payees
FROM tokens_solana.transfers t JOIN fac f ON f.fee_payer = t.tx_signer
WHERE t.token_mint_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AND t.block_date >= DATE '2025-07-01' AND t.block_date < DATE '2026-09-28' AND t.from_owner <> t.to_owner
GROUP BY 1, 2 ORDER BY 1, usd DESC;
