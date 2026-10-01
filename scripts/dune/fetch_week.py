#!/usr/bin/env python3
"""Collect one index week from Dune instead of Blockscout (2026-10-01), grouped to keep the export small.

One row per (facilitator, payer, payee, selector, amount) with its count n; the index, market and review loaders
expand n. Weeks 2026-08-03/10/17 hold 1.5M-4.2M settlements but only ~400k such groups each, so the export is about
40 MB a week (about 80 Dune credits at 2 credits/MB) instead of several hundred MB.
Writes STATE/x402_week_<week>/txs.jsonl and COMPLETE (with "dune" as the source).
  python3 scripts/dune/fetch_week.py 2026-08-17
"""
import csv, datetime as dt, json, os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
week = sys.argv[1]; w0 = dt.date.fromisoformat(week); w1 = w0 + dt.timedelta(days=6)
base = open(os.path.join(ROOT, 'analytics', 'dune', 'x402_base_weekly.sql')).read()
fac = re.search(r'WITH facilitators \(address, name\) AS \(\n  VALUES\n(.*?)\n\),', base, re.S).group(1)
sql = f"""WITH facilitators (address, name) AS (
  VALUES
{fac}
)
SELECT lower(to_hex(t."from")) AS f, lower(to_hex(bytearray_substring(t.data, 1, 4))) AS s,
       lower(to_hex(bytearray_substring(t.data, 17, 20))) AS p, lower(to_hex(bytearray_substring(t.data, 49, 20))) AS q,
       CAST(bytearray_to_uint256(bytearray_substring(t.data, 69, 32)) AS VARCHAR) AS a, COUNT(*) AS n
FROM base.transactions t JOIN facilitators fa ON t."from" = fa.address
WHERE t.block_date BETWEEN DATE '{w0}' AND DATE '{w1}' AND t."to" = {USDC}
  AND bytearray_substring(t.data, 1, 4) IN (0xe3ee160e, 0xcf092995) AND t.success
GROUP BY 1, 2, 3, 4, 5
"""
tmp = os.path.join(ROOT, 'local', 'dune'); os.makedirs(tmp, exist_ok=True)
sp, cp = os.path.join(tmp, f'week_{week}.sql'), os.path.join(tmp, f'week_{week}.csv')
open(sp, 'w').write(sql)
if not (os.path.exists(cp) and os.path.getsize(cp) > 0):
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'dune', 'run.py'), sp, '--out', cp], check=True)
out = os.path.join(ROOT, 'local', f'x402_week_{week}'); os.makedirs(out, exist_ok=True)
groups = total = 0
with open(os.path.join(out, 'txs.jsonl'), 'w') as f:
    for i, r in enumerate(csv.DictReader(open(cp))):
        n = int(float(r['n'])); groups += 1; total += n
        f.write(json.dumps({'hash': f'dune:{week}:{i}', 'block': None, 'ts': f'{w0}T00:00:00.000000Z', 'facilitator': '0x' + r['f'], 'target': USDC,
                            'selector': '0x' + r['s'], 'payer': '0x' + r['p'], 'payee': '0x' + r['q'], 'usdc_atomic': int(r['a']), 'n': n, 'source': 'dune'}) + '\n')
open(os.path.join(out, 'COMPLETE'), 'w').write(f'dune {groups} groups {total} settlements\n')
print(f'{week}: {groups:,} groups, {total:,} settlements -> {out}')
