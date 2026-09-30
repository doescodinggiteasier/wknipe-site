#!/usr/bin/env python3
"""ORDER_010: collect Base x402 facilitator transactions for one or more Mon-Sun UTC weeks.

Source: base.blockscout.com, both public APIs at once, each inside its published rate limit (scripts/x402_index/bs.py):
  v1 txlist (10,000 rows per call, ~10 calls per 40 min) takes the busy facilitators;
  v2 keyset listing (50 rows per call, 150 calls per 5 min) takes the quiet ones, then steals from v1's queue.
Base makes one block every 2 s, so week boundaries come from an anchor block (51,579,727 = 2026-09-21T00:00:00Z,
checked on Blockscout; it matches the ORDER_004 J.1 range 51,579,727-51,882,126).
Rows match scripts/x402/base_week.py (hash, block, ts, facilitator, target, selector [, payer, payee, usdc_atomic]).
Output: STATE/x402_week_<start>/txs.jsonl, done.txt (finished facilitators), COMPLETE (finished week).
Re-running resumes; duplicates from an interrupted facilitator are dropped by hash downstream.
--deadline SECONDS: stop handing out facilitators after that long and exit 75 (incomplete) so a CI job can save its
progress and resume in a later run instead of hitting the runner's time limit.
Usage: python3 scripts/x402_index/collect.py 2026-09-14 2026-09-07 ...   or   --latest [--deadline 18000]
"""
import argparse, collections, datetime as dt, json, os, queue, sys, threading, time, urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import bs, common

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ANCHOR_BLOCK, ANCHOR_TS = 51579727, int(dt.datetime(2026, 9, 21, tzinfo=dt.timezone.utc).timestamp())
FAC = os.path.join(ROOT, 'data', 'x402', 'base_facilitators_2026-09-27.json')
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TWA = {"0xe3ee160e", "0xcf092995"}
BIG = 5000  # facilitators with >= this many txs in the reference week go to the v1 queue first


def week_blocks(start):
    ts = int(dt.datetime(start.year, start.month, start.day, tzinfo=dt.timezone.utc).timestamp())
    b0 = ANCHOR_BLOCK + (ts - ANCHOR_TS) // 2
    return b0, b0 + 7 * 86400 // 2 - 1


def latest_complete(today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    return today - dt.timedelta(days=today.weekday() + 7)


def row(h, block, ts, frm, to, inp):
    inp = (inp or '').lower(); sel = inp[:10]
    r = {'hash': h, 'block': int(block), 'ts': ts, 'facilitator': frm.lower(), 'target': (to or '').lower(), 'selector': sel}
    if r['target'] == USDC and sel in TWA and len(inp) >= 10 + 64 * 3:
        w = lambda i: inp[10 + 64 * i: 10 + 64 * (i + 1)]
        r['payer'], r['payee'], r['usdc_atomic'] = '0x' + w(0)[24:], '0x' + w(1)[24:], int(w(2), 16)
    return r


def via_v1(addr, b0, b1, emit):
    n, start = 0, b0
    while True:
        d = bs.get(f'/api?module=account&action=txlist&address={addr}&startblock={start}&endblock={b1}&page=1&offset=10000&sort=asc')
        res = d.get('result')
        if not isinstance(res, list):
            if 'No transactions' in str(d.get('message')): return n
            raise RuntimeError(f'v1 {addr}: {str(d)[:200]}')
        for t in res:
            if t['from'].lower() != addr or t.get('isError') != '0' or t.get('txreceipt_status') not in ('1', None, ''):
                continue
            ts = dt.datetime.fromtimestamp(int(t['timeStamp']), dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000000Z')
            emit(row(t['hash'], t['blockNumber'], ts, t['from'], t['to'], t['input'])); n += 1
        if len(res) < 10000: return n
        start = int(res[-1]['blockNumber'])  # re-reads that block; duplicates dropped by hash


def via_v2(addr, b0, b1, emit):
    n, params = 0, f'filter=from&block_number={b1 + 1}&index=0&items_count=50'
    while True:
        d = bs.get(f'/api/v2/addresses/{addr}/transactions?{params}')
        items = d.get('items') or []
        for tx in items:
            b = tx.get('block_number')
            if b is None: continue
            if b < b0: return n
            if b > b1 or tx.get('status') != 'ok' or tx['from']['hash'].lower() != addr: continue
            emit(row(tx['hash'], b, tx['timestamp'], tx['from']['hash'], (tx.get('to') or {}).get('hash'), tx.get('raw_input'))); n += 1
        nxt = d.get('next_page_params')
        if not items or not nxt: return n
        params = 'filter=from&' + urllib.parse.urlencode(nxt)


REFCOUNTS = os.path.join(ROOT, 'data', 'x402', 'facilitator_tx_counts_2026-09-21.json')


def reference_counts():
    """Transactions per facilitator in the reference week 2026-09-21 (sorts busy ones to the v1 queue)."""
    if os.path.exists(REFCOUNTS):
        return collections.Counter(json.load(open(REFCOUNTS)))
    p = os.path.join(common.STATE, 'x402_week_2026-09-21', 'txs.jsonl')
    c = collections.Counter()
    if os.path.exists(p):
        for l in open(p): c[json.loads(l)['facilitator']] += 1
    return c


def collect(start, ref, deadline=None):
    out = os.path.join(common.STATE, f'x402_week_{start}')
    if os.path.exists(os.path.join(out, 'COMPLETE')):
        print(f'{start}: already complete', flush=True); return out
    if any(os.path.exists(os.path.join(common.STATE, 'x402_index', f'week_{start}.json{z}')) for z in ('', '.gz')):
        print(f'{start}: already built (filter cache present); raw rows not needed', flush=True); return out
    os.makedirs(out, exist_ok=True)
    b0, b1 = week_blocks(start)
    t0 = time.time()
    done_p = os.path.join(out, 'done.txt')
    done = set(open(done_p).read().split()) if os.path.exists(done_p) else set()
    facs = [f for f in json.load(open(FAC)) if f[1].lower() not in done]
    big = sorted([f for f in facs if ref[f[1].lower()] >= BIG], key=lambda f: -ref[f[1].lower()])
    small = sorted([f for f in facs if ref[f[1].lower()] < BIG], key=lambda f: -ref[f[1].lower()])
    qs = {'v1': collections.deque(big), 'v2': collections.deque(small)}
    lock = threading.Lock()
    tries, failed = {}, []
    print(f'{start}: blocks {b0}-{b1}; {len(big)} busy + {len(small)} quiet facilitators to fetch', flush=True)
    with open(os.path.join(out, 'txs.jsonl'), 'a') as fo, open(done_p, 'a') as dp:
        def emit(r):
            with lock: fo.write(json.dumps(r) + '\n')

        def worker(kind):
            fetch = via_v1 if kind == 'v1' else via_v2
            other = 'v2' if kind == 'v1' else 'v1'
            while True:
                if deadline and time.time() - t0 > deadline: return
                with lock:
                    if qs[kind]: f = qs[kind].popleft()
                    elif qs[other]:  # v1 steals the busiest quiet job; v2 steals the quietest busy job
                        f = qs[other].popleft() if kind == 'v1' else qs[other].pop()
                    else: return
                try:
                    n = fetch(f[1].lower(), b0, b1, emit)
                except Exception as e:  # persistent 5xx on one facilitator: requeue it (partial rows dedupe by hash)
                    print(f'{start}\t{kind}\tFAILED {f[1]} ({str(e)[:80]}); requeued', flush=True)
                    with lock:
                        tries[f[1]] = tries.get(f[1], 0) + 1
                        if tries[f[1]] < 5: qs[other].append(f)
                        else: failed.append(f[1])
                    time.sleep(60)
                    continue
                with lock:
                    fo.flush(); dp.write(f[1].lower() + '\n'); dp.flush()
                print(f'{start}\t{kind}\t{f[0]}\t{f[1]}\t{n}\t{bs.STATS}', flush=True)

        ths = [threading.Thread(target=worker, args=(k,)) for k in ('v1', 'v2')]
        for t in ths: t.start()
        for t in ths: t.join()
    if failed:
        print(f'{start}: NOT complete, facilitators failed 5 times: {failed}', flush=True); return None
    if qs['v1'] or qs['v2']:
        print(f'{start}: deadline reached, {len(qs["v1"]) + len(qs["v2"])} facilitators left; resume later', flush=True); return None
    open(os.path.join(out, 'COMPLETE'), 'w').write(f'{b0} {b1} {round(time.time() - t0)}s\n')
    print(f'{start}: done in {round((time.time() - t0) / 60, 1)} min', flush=True)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('weeks', nargs='*'); ap.add_argument('--latest', action='store_true')
    ap.add_argument('--deadline', type=float, help='seconds')
    a = ap.parse_args()
    weeks = [dt.date.fromisoformat(w) for w in a.weeks] + ([latest_complete()] if a.latest else [])
    ref = reference_counts()
    ok = True
    for w in weeks:
        assert w.weekday() == 0, f'{w} is not a Monday'
        ok = collect(w, ref, a.deadline) is not None and ok
    sys.exit(0 if ok else 75)
