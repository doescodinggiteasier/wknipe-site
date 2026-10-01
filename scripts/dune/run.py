#!/usr/bin/env python3
"""Run a DuneSQL file through the Dune API and save the result as CSV.

The API key is read from the macOS keychain (service "dune") or $DUNE_API_KEY. It is never printed or written to disk.
  security add-generic-password -s dune -a "$USER" -w        # Wes, once: paste the key at the prompt

  python3 scripts/dune/run.py analytics/dune/1_x402_base_history.sql [--out data/dune/x.csv] [--perf medium|large]

Endpoints: POST /api/v1/sql/execute, GET /api/v1/execution/{id}/status, GET /api/v1/execution/{id}/results/csv
(paged with the x-dune-next-offset header). Every run is logged with its credits to local/dune_ledger.jsonl.
"""
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
API = 'https://api.dune.com/api/v1'
LEDGER = os.path.join(ROOT, 'local', 'dune_ledger.jsonl')


def key():
    k = os.environ.get('DUNE_API_KEY')
    if not k:
        r = subprocess.run(['security', 'find-generic-password', '-s', 'dune', '-w'], capture_output=True, text=True)
        k = r.stdout.strip()
    if not k: sys.exit('No Dune key: run  security add-generic-password -s dune -a "$USER" -w  and paste it.')
    return k


def call(method, path, body=None, raw=False):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'X-Dune-Api-Key': key(), 'Content-Type': 'application/json', 'User-Agent': 'wknipe-research/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
            return (data, dict(r.headers)) if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        sys.exit(f'Dune API {e.code} on {path}: {e.read().decode()[:500]}')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('sql'); ap.add_argument('--out'); ap.add_argument('--perf', default='medium')
    ap.add_argument('--timeout', type=int, default=1800)
    a = ap.parse_args()
    sql = open(a.sql).read()
    out = a.out or os.path.join(ROOT, 'data', 'dune', os.path.basename(a.sql)[:-4] + '.csv')
    t0 = time.time()
    ex = call('POST', '/sql/execute', {'sql': sql, 'performance': a.perf})
    eid = ex['execution_id']; print('execution', eid, flush=True)
    while True:
        st = call('GET', f'/execution/{eid}/status')
        s = st.get('state')
        if s == 'QUERY_STATE_COMPLETED': break
        if s in ('QUERY_STATE_FAILED', 'QUERY_STATE_CANCELLED', 'QUERY_STATE_EXPIRED'):
            sys.exit(f'{s}: {json.dumps(st.get("error") or st)[:800]}')
        if time.time() - t0 > a.timeout: sys.exit(f'still {s} after {a.timeout}s; execution {eid}')
        time.sleep(5)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    offset, first, rows = 0, True, 0
    with open(out, 'w') as f:
        while offset is not None:
            data, h = call('GET', f'/execution/{eid}/results/csv?limit=50000&offset={offset}', raw=True)
            text = data.decode()
            if not first: text = text.split('\n', 1)[1] if '\n' in text else ''
            f.write(text if text.endswith('\n') or not text else text + '\n'); first = False
            rows += max(0, text.count('\n') - (1 if offset == 0 else 0))
            nxt = {k.lower(): v for k, v in h.items()}.get('x-dune-next-offset')
            offset = int(nxt) if nxt else None
    credits = st.get('execution_cost_credits') or (st.get('result_metadata') or {}).get('execution_cost_credits')
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    open(LEDGER, 'a').write(json.dumps({'ts': time.time(), 'sql': a.sql, 'execution_id': eid, 'rows': rows, 'secs': round(time.time() - t0), 'credits': credits, 'perf': a.perf}) + '\n')
    print(f'{rows} rows -> {out} ({round(time.time() - t0)} s, credits {credits})')


if __name__ == '__main__':
    main()
