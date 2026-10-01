#!/usr/bin/env python3
"""Fill Blockscout collection gaps in one index week from Dune (2026-10-01).

Compares hourly settlement counts (Dune vs local/x402_week_<week>/txs.jsonl), then exports from Dune only the
settlements in hours where local data is short, and appends the ones missing locally (by tx hash) to txs.jsonl
in the collector's own row format. A backup of txs.jsonl is kept as txs.jsonl.pre_dune.
  python3 scripts/dune/patch_week.py 2026-09-21
"""
import csv, datetime as dt, json, os, re, shutil, subprocess, sys, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
SEL = ('0xe3ee160e', '0xcf092995')
week = sys.argv[1]
w0 = dt.date.fromisoformat(week); w1 = w0 + dt.timedelta(days=6)
base = open(os.path.join(ROOT, 'analytics', 'dune', 'x402_base_weekly.sql')).read()
fac = re.search(r'WITH facilitators \(address, name\) AS \(\n  VALUES\n(.*?)\n\),', base, re.S).group(1)
tmp = os.path.join(ROOT, 'local', 'dune'); os.makedirs(tmp, exist_ok=True)
src = os.path.join(ROOT, 'local', f'x402_week_{week}', 'txs.jsonl')


def run(sql, name):
    p = os.path.join(tmp, name + '.sql'); open(p, 'w').write(sql)
    out = os.path.join(tmp, name + '.csv')
    if os.path.exists(out) and os.path.getsize(out) > 0:  # exports cost credits: reuse one already fetched
        return list(csv.DictReader(open(out)))
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'dune', 'run.py'), p, '--out', out], check=True)
    return list(csv.DictReader(open(out)))


def cte(where):
    return f"""WITH facilitators (address, name) AS (
  VALUES
{fac}
)
SELECT {{cols}}
FROM base.transactions t JOIN facilitators f ON t."from" = f.address
WHERE t.block_date BETWEEN DATE '{w0}' AND DATE '{w1}' AND t."to" = {USDC}
  AND bytearray_substring(t.data, 1, 4) IN (0xe3ee160e, 0xcf092995) AND t.success {where}"""


hourly = run(cte('').replace('{cols}', "date_trunc('hour', t.block_time) AS hr, COUNT(*) AS n") + ' GROUP BY 1', f'hourly_{week}')
loc = collections.Counter(); have = set()
for l in open(src):
    r = json.loads(l)
    if r.get('target') == USDC and r.get('selector') in SEL and r['hash'] not in have:
        have.add(r['hash']); loc[r['ts'][:13]] += 1
gaps = sorted(r['hr'][:13] for r in hourly if int(float(r['n'])) > loc.get(r['hr'][:13].replace(' ', 'T'), 0))
print(f'{len(gaps)} short hours; local {len(have):,} vs Dune {sum(int(float(r["n"])) for r in hourly):,}')
if not gaps: sys.exit(0)
hours = ', '.join(f"TIMESTAMP '{h}:00:00'" for h in gaps)
cols = ("lower(to_hex(t.hash)) AS hash, t.block_number AS block, t.block_time AS ts, lower(to_hex(t.\"from\")) AS facilitator, "
        "lower(to_hex(bytearray_substring(t.data, 1, 4))) AS selector, lower(to_hex(bytearray_substring(t.data, 17, 20))) AS payer, "
        "lower(to_hex(bytearray_substring(t.data, 49, 20))) AS payee, CAST(bytearray_to_uint256(bytearray_substring(t.data, 69, 32)) AS VARCHAR) AS atomic")
rows = run(cte(f"AND date_trunc('hour', t.block_time) IN ({hours})").replace('{cols}', cols), f'gaprows_{week}')
bak = src + '.pre_dune'
if not os.path.exists(bak): shutil.copy(src, bak)
added = 0
with open(src, 'a') as f:
    for r in rows:
        h = '0x' + r['hash']
        if h in have: continue
        ts = r['ts'].replace(' UTC', '').replace(' ', 'T')
        f.write(json.dumps({'hash': h, 'block': None,  # Dune's CSV gives block as a rounded float; nothing downstream reads it
                             'ts': ts[:19] + '.000000Z', 'facilitator': '0x' + r['facilitator'], 'target': USDC,
                            'selector': '0x' + r['selector'], 'payer': '0x' + r['payer'], 'payee': '0x' + r['payee'], 'usdc_atomic': int(r['atomic']), 'source': 'dune'}) + '\n')
        have.add(h); added += 1
print(f'added {added:,} settlements from Dune; local now {len(have):,}')
