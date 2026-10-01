-- 4. Solana sellers, week of 21-27 Sep: the Solana equivalent of wknipe.com/x402/sellers/.
-- Per payee: payments, USD, distinct buyers, repeat buyers (paid 2+ times), and the share from its largest buyer
-- (a dependence / wash signal). Payee addresses can be matched to Bazaar listings' Solana payTo to get what they sell.
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
x AS (
  SELECT fac.facilitator, t.from_owner AS payer, t.to_owner AS payee, t.amount / 1e6 AS usd
  FROM tokens_solana.transfers t JOIN fac ON fac.fee_payer = t.tx_signer
  WHERE t.token_mint_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' AND t.block_date BETWEEN DATE '2026-09-21' AND DATE '2026-09-27'
    AND t.from_owner <> t.to_owner
),
pair AS (SELECT payee, payer, COUNT(*) AS n, SUM(usd) AS usd FROM x GROUP BY 1, 2),
per_payee AS (SELECT payee, COUNT(*) AS buyers, COUNT_IF(n >= 2) AS repeat_buyers, MAX(usd) AS top_buyer_usd FROM pair GROUP BY 1)
SELECT x.payee, arbitrary(x.facilitator) AS facilitator, COUNT(*) AS payments, SUM(x.usd) AS usd, APPROX_PERCENTILE(x.usd, 0.5) AS median_usd,
       arbitrary(p.buyers) AS buyers, arbitrary(p.repeat_buyers) AS repeat_buyers, arbitrary(p.top_buyer_usd) / SUM(x.usd) AS top_buyer_share
FROM x JOIN per_payee p ON p.payee = x.payee
GROUP BY 1 ORDER BY usd DESC LIMIT 300;
