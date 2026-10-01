#!/usr/bin/env python3
"""ORDER_013 Phase 4: x402 endpoint status monitor (wknipe.com/x402/status/). Unpaid: it never sends a payment.

One request per endpoint per check, with an honest user agent, the listing's declared HTTP method (POST gets an empty
JSON body), no payment header, 10 s timeout, at most 64 KB read, at most 3 redirects, one request at a time per host
with >= 1 s between requests to the same host. Checks:
  responds (any HTTP status) · valid 402 (status 402 and a parseable `accepts` list, x402 v2 PAYMENT-REQUIRED header or
  v1 JSON body) · posted amount matches the Bazaar listing · payTo matches the listing · latency to first byte.
Scope per day: sellers whose Base payTo had >= 1 genuine buyer in the latest index week get up to PER_SELLER (5)
endpoints checked every day (a different rotation each day); every other listing is checked once a week (a stable
1/7 slice per weekday). Caps: PER_HOST (60) requests per host per day and CAP (4,000) requests per day, priority first.

Writes state/x402_status/checks_<date>.jsonl.gz, data/x402_status/{status_daily.csv, status_latest.csv,
seller_uptime.csv, status.json}.
Usage: python3 scripts/x402_status/monitor.py [--listing PATH.json[.gz]] [--cap 4000] [--date YYYY-MM-DD]
"""
import argparse, base64, collections, csv, datetime as dt, gzip, hashlib, json, os, statistics, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
import common  # noqa: E402

UA = 'wknipe-x402-status/1.0 (+https://wknipe.com/x402/status/; one unpaid request per endpoint per day)'
OUT = os.path.join(common.ROOT, 'data', 'x402_status')
ST = os.path.join(common.STATE, 'x402_status')
TIMEOUT, MAXB = 10, 64 * 1024
PER_SELLER, PER_HOST = 5, 60


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if getattr(req, '_hops', 0) >= 3: return None
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new: new._hops = getattr(req, '_hops', 0) + 1
        return new


OPENER = urllib.request.build_opener(NoRedirect)


def parse_accepts(status, headers, body):
    """-> (version, accepts list) from a 402 response, or (None, [])."""
    h = {k.lower(): v for k, v in headers.items()}
    pr = h.get('payment-required')
    if pr:
        try:
            j = json.loads(base64.b64decode(pr + '=' * (-len(pr) % 4)).decode('utf-8', 'replace'))
            return j.get('x402Version', 2), j.get('accepts') or []
        except Exception:
            pass
    try:
        j = json.loads(body.decode('utf-8', 'replace'))
        if isinstance(j, dict) and isinstance(j.get('accepts'), list):
            return j.get('x402Version', 1), j['accepts']
    except Exception:
        pass
    return None, []


def valid_accept(a):
    return isinstance(a, dict) and a.get('scheme') and a.get('network') and a.get('payTo') and (a.get('amount') or a.get('maxAmountRequired'))


def check(ep):
    url, method = ep['resource'], ep['method'] or 'GET'
    data = b'{}' if method in ('POST', 'PUT', 'PATCH') else None
    req = urllib.request.Request(url, data=data, method=method, headers={'User-Agent': UA, 'Accept': 'application/json',
                                                                       **({'Content-Type': 'application/json'} if data else {})})
    t0 = time.time(); r = {'resource': url, 'host': ep['host'], 'method': method, 'pay_to': ep['pay_to'], 'priority': ep['priority']}
    try:
        with OPENER.open(req, timeout=TIMEOUT) as resp:
            r['latency_ms'] = round((time.time() - t0) * 1000); status, headers, body = resp.status, dict(resp.headers), resp.read(MAXB)
    except urllib.error.HTTPError as e:
        r['latency_ms'] = round((time.time() - t0) * 1000); status, headers = e.code, dict(e.headers or {})
        try: body = e.read(MAXB)
        except Exception: body = b''
    except Exception as e:
        r.update({'status': 0, 'error': type(e).__name__ + (': ' + str(e)[:80] if str(e) else '')}); r['responds'] = False
        return r
    r['status'] = status; r['responds'] = True
    ver, acc = parse_accepts(status, headers, body) if status == 402 else (None, [])
    good = [a for a in acc if valid_accept(a)]
    r['valid_402'] = status == 402 and bool(good)
    r['x402_version'] = ver
    if good:
        amts = {str(a.get('amount') or a.get('maxAmountRequired')) for a in good if (a.get('network') in common.BASE_NETS) and a.get('scheme') == 'exact'}
        payto = {str(a.get('payTo')).lower() for a in good}
        r['price_match'] = (ep['amount'] in amts) if ep['amount'] else None
        r['payto_match'] = (ep['pay_to'] in payto) if ep['pay_to'] else None
    return r


def endpoints(items, buyers):
    out = []
    for it in items:
        res = it.get('resource') or ''
        u = urllib.parse.urlparse(res)
        if u.scheme not in ('http', 'https') or not u.hostname: continue
        payto = amount = None
        for a in it.get('accepts') or []:
            if a.get('network') in common.BASE_NETS and a.get('payTo'):
                payto = payto or a['payTo'].lower()
                if common.base_usdc_price(a) is not None and amount is None: amount = str(a.get('amount', a.get('maxAmountRequired')))
        info = ((it.get('extensions') or {}).get('bazaar') or {}).get('info') or {}
        method = ((info.get('input') or {}).get('method') or it.get('method') or 'GET').upper()
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'HEAD'): method = 'GET'
        out.append({'resource': res, 'host': u.hostname.lower(), 'method': method, 'pay_to': payto, 'amount': amount,
                    'priority': bool(payto and buyers.get(payto, 0) >= 1),
                    'slice': int(hashlib.sha1(res.encode()).hexdigest(), 16) % 7})
    return out


def run(items, day, cap):
    pw = list(csv.DictReader(open(os.path.join(common.OUT, 'payees_weekly.csv'))))
    lw = max(r['week_start'] for r in pw)
    buyers = {r['payee']: int(r['payers']) for r in pw if r['week_start'] == lw}
    eps = endpoints(items, buyers)
    dedup = {}
    for e in eps: dedup.setdefault((e['resource'], e['method']), e)
    eps = list(dedup.values())
    wd = dt.date.fromisoformat(day).weekday()
    rot = lambda e: hashlib.sha1((e['resource'] + day).encode()).hexdigest()
    per = collections.defaultdict(list)
    for e in eps:
        if e['priority']: per[e['pay_to']].append(e)
    pri = [e for q in sorted(per) for e in sorted(per[q], key=rot)[:PER_SELLER]]
    rest = [e for e in eps if not e['priority'] and e['slice'] == wd]
    hostn, todo = collections.Counter(), []
    for e in pri + rest:
        if hostn[e['host']] >= PER_HOST or len(todo) >= cap: continue
        hostn[e['host']] += 1; todo.append(e)
    scope = {'endpoints_listed': len(eps), 'sellers_with_buyers_listed': len(per), 'endpoints_of_sellers_with_buyers': sum(len(v) for v in per.values()),
             'priority_checked_today': sum(1 for e in todo if e['priority']), 'rotating_checked_today': sum(1 for e in todo if not e['priority']),
             'caps': {'per_seller_daily': PER_SELLER, 'per_host_daily': PER_HOST, 'per_day': cap}}
    by_host = collections.defaultdict(list)
    for e in todo: by_host[e['host']].append(e)
    results, lock = [], threading.Lock()

    def host_worker(h):
        for i, e in enumerate(by_host[h]):
            if i: time.sleep(1.0)
            r = check(e)
            with lock: results.append(r)
    t0 = time.time()
    with ThreadPoolExecutor(32) as ex:
        list(ex.map(host_worker, list(by_host)))
    print(f'{day}: {len(results)} requests to {len(by_host)} hosts in {time.time() - t0:.0f} s; scope {scope}', flush=True)
    os.makedirs(ST, exist_ok=True)
    with gzip.open(os.path.join(ST, f'checks_{day}.jsonl.gz'), 'wt') as f:
        for r in results: f.write(json.dumps({**r, 'date': day}) + '\n')
    summarise(day, scope)


def summarise(day=None, scope=None):
    if scope is None and os.path.exists(os.path.join(OUT, 'status.json')): scope = json.load(open(os.path.join(OUT, 'status.json'))).get('scope_latest')
    import glob
    files = sorted(glob.glob(os.path.join(ST, 'checks_*.jsonl.gz')))
    days = {}
    for p in files:
        d = os.path.basename(p)[7:17]
        days[d] = [json.loads(l) for l in gzip.open(p, 'rt')]
    os.makedirs(OUT, exist_ok=True)
    daily = []
    for d, rs in sorted(days.items()):
        pr = [r for r in rs if r['priority']]
        for label, sub in (('all', rs), ('priority', pr)):
            n = len(sub)
            if not n: continue
            v = [r for r in sub if r.get('valid_402')]
            pm = [r['price_match'] for r in v if r.get('price_match') is not None]
            tm = [r['payto_match'] for r in v if r.get('payto_match') is not None]
            lat = [r['latency_ms'] for r in sub if r.get('responds') and r.get('latency_ms') is not None]
            daily.append({'date': d, 'scope': label, 'checked': n, 'hosts': len({r['host'] for r in sub}),
                          'responds': round(sum(1 for r in sub if r.get('responds')) / n, 4), 'valid_402': round(len(v) / n, 4),
                          'price_match_of_valid': round(sum(pm) / len(pm), 4) if pm else '', 'payto_match_of_valid': round(sum(tm) / len(tm), 4) if tm else '',
                          'median_latency_ms': round(statistics.median(lat)) if lat else '', 'p90_latency_ms': round(sorted(lat)[int(len(lat) * .9)]) if lat else ''})
    with open(os.path.join(OUT, 'status_daily.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0])); w.writeheader(); w.writerows(daily)
    # latest result per endpoint over the last 7 days of checks
    last = sorted(days)[-7:]
    latest = {}
    for d in last:
        for r in days[d]: latest[(r['resource'], r['method'])] = {**r, 'date': d}
    lat_rows = sorted(latest.values(), key=lambda r: (not r['priority'], r['host'], r['resource']))
    keys = ['date', 'host', 'resource', 'method', 'pay_to', 'priority', 'status', 'responds', 'valid_402', 'x402_version', 'price_match', 'payto_match', 'latency_ms', 'error']
    with open(os.path.join(OUT, 'status_latest.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore'); w.writeheader(); w.writerows(lat_rows)
    # per seller (Base payTo): endpoints checked in the last 7 days, share answering a valid 402, and daily uptime
    sel = collections.defaultdict(lambda: {'checks': 0, 'valid': 0, 'endpoints': set(), 'days': set()})
    for d in last:
        for r in days[d]:
            if not r.get('pay_to'): continue
            s = sel[r['pay_to']]; s['checks'] += 1; s['valid'] += bool(r.get('valid_402')); s['endpoints'].add(r['resource']); s['days'].add(d)
    up = [{'pay_to': q, 'checks_7d': s['checks'], 'endpoints_7d': len(s['endpoints']), 'days_checked': len(s['days']),
           'valid_402_share': round(s['valid'] / s['checks'], 4)} for q, s in sel.items()]
    up.sort(key=lambda r: (-r['checks_7d'], r['pay_to']))
    with open(os.path.join(OUT, 'seller_uptime.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(up[0])); w.writeheader(); w.writerows(up)
    fails = collections.Counter()
    for r in lat_rows:
        if r.get('valid_402'): continue
        fails['no response (' + (r.get('error') or 'error').split(':')[0] + ')' if not r.get('responds') else f"HTTP {r['status']}" if r['status'] != 402 else '402 without parseable accepts'] += 1
    doc = {'built': str(dt.date.today()), 'latest_day': sorted(days)[-1], 'days': len(days), 'user_agent': UA, 'scope_latest': scope,
           'latest': [x for x in daily if x['date'] == sorted(days)[-1]], 'endpoints_7d': len(lat_rows),
           'failure_reasons_7d': fails.most_common(12)}
    json.dump(doc, open(os.path.join(OUT, 'status.json'), 'w'), indent=1)
    print(json.dumps(doc, indent=1))


def load_listing(path):
    if path: return common.jload(path)
    d, p = common.bazaar_snapshots()[-1]
    full = os.path.join(common.STATE, f'bazaar_all_{d}.json')
    return common.jload(full if os.path.exists(full) else p)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--listing'); ap.add_argument('--cap', type=int, default=4000)
    ap.add_argument('--date', default=str(dt.datetime.now(dt.timezone.utc).date())); ap.add_argument('--summarise-only', action='store_true')
    a = ap.parse_args()
    if a.summarise_only: summarise()
    else: run(load_listing(a.listing), a.date, a.cap)
