#!/usr/bin/env python3
"""ORDER_013 Phase 3: classify every CDP Bazaar listing (resource) and write a short normalised "what it does".

Same five categories and definitions as the seller classifier (scripts/x402_index/classify.py SYSTEM), applied to one
listing at a time, plus a 3-8 word plain description used by the Price comps search. Cached by the sha1 of the listing
text in data/x402_prices/listing_classes.jsonl, so a rerun or a new snapshot only asks about text never seen before.
Budget: OR_CAP (default $10 for ORDER_013); every call's cost goes to the ledger.

  python3 scripts/x402_prices/classify_listings.py --pilot MODEL [MODEL ...]  # score vs hand-labelled sellers' listings
  python3 scripts/x402_prices/classify_listings.py --model MODEL [--limit N]  # classify the latest snapshot
"""
import argparse, hashlib, json, os, random, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
import common  # noqa: E402
from classify import SYSTEM as SELLER_SYSTEM  # noqa: E402

OUT = os.path.join(common.ROOT, 'data', 'x402_prices')
CACHE = os.path.join(OUT, 'listing_classes.jsonl')
LEDGER = os.environ.get('OR_LEDGER') or os.path.join(common.STATE, 'o13_or_ledger.jsonl')
CAP = float(os.environ.get('OR_CAP') or 10.0)
UA = "wknipe-x402-index/0.1 (github.com/doescodinggiteasier/wknipe-site)"
LOCK = threading.Lock()
SYSTEM = SELLER_SYSTEM.replace('You classify sellers on the x402 agent-payment network by what a buyer\'s agent pays them for.',
                               'You classify one paid API listing on the x402 agent-payment network by what a buyer\'s agent pays for.') + """
Also write `what`: 3 to 8 lowercase words naming what one paid call returns or does, generic and without brand names,
e.g. "token price lookup", "web page scrape to markdown", "image generation from prompt", "news article full text"."""
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['category', 'what', 'confidence'],
          'properties': {'category': {'type': 'string', 'enum': ['content', 'data', 'search', 'compute', 'other']},
                         'what': {'type': 'string'},
                         'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']}}}


def listing_text(it):
    bz = (it.get('extensions') or {}).get('bazaar') or {}
    info = bz.get('info') or {}
    parts = [it.get('resource', ''), it.get('serviceName') or info.get('name') or '', bz.get('category') or '',
             ' '.join(it.get('tags') or []) if isinstance(it.get('tags'), list) else str(it.get('tags') or ''),
             (it.get('description') or info.get('description') or '')[:600]]
    return '\n'.join(p for p in parts if p).strip()


def key(text):
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def latest_snapshot():
    """The newest weekly snapshot (STATE/bazaar/<date>.json.gz): the same file locally and in CI, so both build the
    same numbers. Snapshots taken before 2026-09-30 13:00 UTC hold Base listings only (the compact format then)."""
    d, p = common.bazaar_snapshots()[-1]
    return d, common.jload(p)


def load_cache():
    out = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line); out[r['k']] = r
    return out


_spent = None


def spent():
    return sum(json.loads(l).get('cost') or 0 for l in open(LEDGER)) if os.path.exists(LEDGER) else 0.0


def chat(model, text, tag):
    global _spent
    with LOCK:
        if _spent is None: _spent = spent()
        if _spent >= CAP: raise RuntimeError(f'cap ${CAP} reached')
    body = {'model': model, 'temperature': 0, 'max_tokens': 80, 'usage': {'include': True},
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': 'Listing:\n' + text[:1200]}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'out', 'strict': True, 'schema': SCHEMA}},
            'provider': {'sort': 'price'}}
    if not model.startswith('anthropic/'):
        body['seed'] = 0; body['reasoning'] = {'enabled': False}
    err = None
    for i in range(4):
        try:
            req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                                         headers={'Authorization': f'Bearer {os.environ["OPENROUTER_API_KEY"]}',
                                                  'Content-Type': 'application/json', 'User-Agent': UA,
                                                  'HTTP-Referer': 'https://github.com/doescodinggiteasier/wknipe-site'})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read())
            u = d.get('usage') or {}
            with LOCK:
                _spent += float(u.get('cost') or 0)
                open(LEDGER, 'a').write(json.dumps({'ts': time.time(), 'model': model, 'tag': tag, 'pt': u.get('prompt_tokens'),
                                                    'ct': u.get('completion_tokens'), 'cost': u.get('cost')}) + '\n')
            txt = d['choices'][0]['message']['content'].strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            out = json.loads(txt)
            if out.get('category') in SCHEMA['properties']['category']['enum'] and out.get('what'):
                out['what'] = ' '.join(out['what'].lower().split()[:10])[:80]
                return out
            err = f'bad output {txt[:80]}'
        except Exception as e:
            err = str(e)[:200]
            if 'cap $' in err: break
        time.sleep(2 * (i + 1))
    return {'category': None, 'what': None, 'confidence': None, 'error': err}


def pilot(models, n=150):
    """Agreement with hand-labelled sellers (ORDER_002/010) on content / data / neither, one listing per seller."""
    _, items = latest_snapshot()
    hand = common.hand_classes()
    by = {}
    for it in items:
        for acc in it.get('accepts') or []:
            q = (acc.get('payTo') or '').lower()
            if q in hand and q not in by: by[q] = it
    sample = sorted(by.items()); random.Random(13).shuffle(sample); sample = sample[:n]
    coarse = lambda c: c if c in ('content', 'data') else 'not'
    truth = [coarse(common.HAND_MAP.get(hand[q][1], hand[q][1] if hand[q][0] == 'o10' else 'not')) for q, _ in sample]
    res = {}
    for m in models:
        t0 = time.time(); before = spent()
        with ThreadPoolExecutor(32) as ex:
            outs = list(ex.map(lambda qi: chat(m, listing_text(qi[1]), 'pilot'), sample))
        pred = [coarse(o['category'] or 'none') for o in outs]
        res[m] = {'n': len(sample), 'agree_3way': round(sum(a == b for a, b in zip(truth, pred)) / len(sample), 3),
                  'errors': sum(o['category'] is None for o in outs), 'cost': round(spent() - before, 4), 'secs': round(time.time() - t0),
                  'examples': [o.get('what') for o in outs[:8]]}
        print(m, res[m], flush=True)
    json.dump(res, open(os.path.join(common.STATE, 'o13_listing_pilot.json'), 'w'), indent=1)


def run(model, limit=None):
    d, items = latest_snapshot()
    cache = load_cache()
    texts = {}
    for it in items:
        t = listing_text(it)
        texts.setdefault(key(t), t)
    todo = [k for k in texts if k not in cache][:limit]
    print(f'snapshot {d}: {len(items)} listings, {len(texts)} distinct texts, {len(todo)} to classify', flush=True)
    os.makedirs(OUT, exist_ok=True)
    done = 0
    with open(CACHE, 'a') as f, ThreadPoolExecutor(48) as ex:
        for k, o in zip(todo, ex.map(lambda k: chat(model, texts[k], 'listing'), todo)):
            if o.get('category'):
                f.write(json.dumps({'k': k, 'category': o['category'], 'what': o['what'], 'confidence': o['confidence'], 'model': model}) + '\n')
                done += 1
    print(f'classified {done}/{len(todo)}; ledger total ${spent():.4f}', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--pilot', nargs='*'); ap.add_argument('--model'); ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    if a.pilot: pilot(a.pilot)
    elif a.model: run(a.model, a.limit)
