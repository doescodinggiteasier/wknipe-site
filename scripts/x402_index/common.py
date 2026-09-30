"""ORDER_010 shared helpers: listing snapshots, posted prices, categories."""
import csv, glob, gzip, json, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'data', 'x402_index')
# Pipeline state (listing snapshots, per-week filter caches, Blockscout link cache, raw collected weeks).
# Private repo: local/ (gitignored). Public repo (wknipe-site): X402_STATE=state, a compact, committed copy
# (raw weeks stay out of git; CI keeps an unfinished one in the Actions cache).
STATE = os.path.abspath(os.environ.get('X402_STATE') or os.path.join(ROOT, 'local'))
USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
BASE_NETS = {'eip155:8453', 'base'}
CATEGORIES = ['content', 'data', 'search', 'compute', 'other', 'large_ticket', 'unclassed']
# Our own addresses (ORDER_011 dogfooding): payments to or from these are never demand.
OURS = {'0x6ac87b6a48e329e2557c7f6054ed1518be76fbf9',  # index API payTo (Wes, ORDER_011)
        '0x5917dcea021336e5b13d228f7ed784732c57c013'}  # our agent test wallet (ORDER_001/002 purchases)
# ORDER_002 hand classes (data/o2_payees_reviewed.csv) -> ORDER_010 categories. 'not content/data' is split by the model.
HAND_MAP = {'publisher content': 'content', 'other content': 'content', 'market/crypto data': 'data', 'other data': 'data'}


def jload(p):
    """json.load for .json or .json.gz."""
    with (gzip.open(p, 'rt') if p.endswith('.gz') else open(p)) as f:
        return json.load(f)


def jdump(obj, p, **kw):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with (gzip.open(p, 'wt', compresslevel=9) if p.endswith('.gz') else open(p, 'w')) as f:
        json.dump(obj, f, **kw)


def first(*paths):
    """The first path that exists, else the last one (the preferred write location)."""
    for p in paths:
        if os.path.exists(p): return p
    return paths[-1]


def compact_listing(items):
    """Keep only what the pipelines read from a Bazaar/x402scan listing: text fields, the HTTP method, and payment offers.
    Base offers keep every field the index uses; offers on other networks keep network/asset/scheme/amount/payTo, so the
    Price comps and listing counts see every listing (ORDER_013). Reads identically through item_text() and
    base_usdc_price(), which only ever use Base offers. Items with no offer at all are dropped."""
    out = []
    for it in items:
        acc = [{k: a[k] for k in ('network', 'asset', 'scheme', 'amount', 'maxAmountRequired', 'payTo') if k in a}
               for a in it.get('accepts') or [] if isinstance(a, dict)]
        if not acc: continue
        bz = (it.get('extensions') or {}).get('bazaar') or {}
        info = bz.get('info') or {}
        c = {k: it[k] for k in ('resource', 'serviceName', 'description', 'tags') if it.get(k)}
        b = {k: bz[k] for k in ('category',) if bz.get(k)}
        i = {k: info[k] for k in ('name', 'description') if info.get(k)}
        m = (info.get('input') or {}).get('method') if isinstance(info.get('input'), dict) else None
        if m: i['input'] = {'method': m}
        if i: b['info'] = i
        if b: c['extensions'] = {'bazaar': b}
        c['accepts'] = acc
        out.append(c)
    return out


def bazaar_snapshots():
    """[(date, path)] of CDP Bazaar snapshots, oldest first: compact STATE/bazaar/<date>.json.gz, else the full
    STATE/bazaar_all_<date>.json (ORDER_001/010 format). One per date; compact wins."""
    out = {}
    for p in glob.glob(os.path.join(STATE, 'bazaar_all_*.json')):
        out[os.path.basename(p)[len('bazaar_all_'):-5]] = p
    for p in glob.glob(os.path.join(STATE, 'bazaar', '*.json.gz')):
        out[os.path.basename(p)[:-8]] = p
    return sorted(out.items())


def base_usdc_price(acc):
    """Posted USD price per call for one `accepts` entry, or None if it is not an exact-scheme Base USDC offer."""
    if acc.get('network') not in BASE_NETS or (acc.get('asset') or '').lower() != USDC or acc.get('scheme') != 'exact':
        return None
    amt = acc.get('amount', acc.get('maxAmountRequired'))
    try:
        return int(amt) / 1e6
    except (TypeError, ValueError):
        return None


def item_text(it):
    bz = (it.get('extensions') or {}).get('bazaar') or {}
    info = bz.get('info') or {}
    parts = [it.get('resource', ''), it.get('serviceName') or info.get('name') or '', bz.get('category') or '',
             ' '.join(it.get('tags') or []), it.get('description') or info.get('description') or '']
    return ' | '.join(p for p in parts if p)


def payee_texts():
    """payee (lower) -> list of distinct listing texts, from every Bazaar snapshot plus the ORDER_001 x402scan pull."""
    ev = {}
    paths = [p for _, p in bazaar_snapshots()]
    merged = first(os.path.join(STATE, 'listings_merged_2026-09-28.json.gz'), os.path.join(STATE, 'listings_merged_2026-09-28.json'))
    for p in paths + ([merged] if os.path.exists(merged) else []):
        for it in jload(p):
            t = item_text(it)
            for acc in it.get('accepts') or []:
                if acc.get('network') in BASE_NETS and acc.get('payTo'):
                    s = ev.setdefault(acc['payTo'].lower(), [])
                    if t not in s: s.append(t)
    return ev


def hand_classes():
    """ORDER_002 hand classes plus ORDER_010 hand checks (the latter win)."""
    out = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'o2_payees_reviewed.csv'))):
        out[r['payee'].lower()] = ('o2', r['hand_class'])
    for name in ('handcheck_30.csv', 'content_audit.csv'):  # ORDER_010 hand check; full hand audit of 'content' sellers
        p = os.path.join(OUT, name)
        if os.path.exists(p):
            for r in csv.DictReader(open(p)):
                if r.get('hand_category'):
                    out[r['payee'].lower()] = ('o10', r['hand_category'])
    return out
