#!/usr/bin/env python3
"""ORDER_010: classify every listed Base x402 payee into content / data / search / compute / other.

Fixes the F1 resolution bug (new payees fell into 'unclassed'): every payee with listing text is classified, and
the result is cached in data/x402_index/payee_classes.csv so later weeks only classify payees not seen before.
Evidence = the payee's resources in every Bazaar snapshot in STATE plus the ORDER_001 x402scan pull.
CI (weekly workflow): OR_LEDGER points at a fresh per-run ledger and OR_CAP=0.50, so one run can never spend more
than $0.50; --strict exits 1 if any listed payee is still unclassified (the run goes red and nothing deploys).
Payees with no listing evidence stay 'unclassed'. Hand labels (ORDER_002, ORDER_010 hand check) override in build.py.

  python3 scripts/x402_index/classify.py --pilot MODEL [MODEL ...]   # score models against the 355 ORDER_002 hand labels
  python3 scripts/x402_index/classify.py --model MODEL               # classify every uncached payee (the weekly step)
Needs OPENROUTER_API_KEY only when there are uncached payees.
"""
import argparse, csv, hashlib, json, os, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
import common

LEDGER = os.environ.get('OR_LEDGER') or os.path.join(common.STATE, 'o10_or_ledger.jsonl')
CACHE = os.path.join(common.OUT, 'payee_classes.csv')
CAP = float(os.environ.get('OR_CAP') or 5.0)  # ORDER_010 cap, USD; CI sets 0.50 per run
UA = "wknipe-x402-index/0.1 (github.com/doescodinggiteasier/wknipe-site)"
LOCK = threading.Lock()
SYSTEM = """You classify sellers on the x402 agent-payment network by what a buyer's agent pays them for.
Categories (pick exactly one):
- content: editorial or creative works people read, watch or hear: news, articles, blogs, books, research reports, newsletters, courses, podcasts, music, stock media, paywalled publisher pages.
- data: structured facts or records looked up from a dataset or feed: market, token or crypto prices, on-chain/wallet data, trading signals, company or people enrichment, weather, sports, maps/geo, registries, analytics, public records.
- search: web search, SERP, scraping, crawling, or fetching/extracting arbitrary web pages on request.
- compute: the seller runs a computation or tool on the buyer's input: LLM chat or inference, image/video/audio generation, transcription, translation, summarization, embeddings, OCR, code execution, rendering, file conversion, storage/hosting, validation or utility tools (DNS, email checks, QR codes).
- other: anything else: token mints, memes, games, lotteries, gift cards, merchandise, payments, swaps, agent infrastructure (attestation, verification, trust scores, payment guards, registries of services), tests and demos.
If the evidence is too thin to tell, choose the most likely category anyway and set confidence low."""
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['category', 'confidence'],
          'properties': {'category': {'type': 'string', 'enum': ['content', 'data', 'search', 'compute', 'other']},
                         'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']}}}


def evidence(texts, limit=1800):
    s, out = 0, []
    for t in texts:
        t = t[:400]
        if s + len(t) > limit: break
        out.append('- ' + t); s += len(t)
    return f'{len(texts)} listed resources; first {len(out)}:\n' + '\n'.join(out)


def spent():
    return sum(json.loads(l).get('cost', 0) for l in open(LEDGER)) if os.path.exists(LEDGER) else 0.0


_spent = None


def chat(model, user, tag):
    global _spent
    with LOCK:
        if _spent is None: _spent = spent()
        if _spent >= CAP: raise RuntimeError(f'cap ${CAP} reached')
    body = {'model': model, 'temperature': 0, 'max_tokens': 60, 'usage': {'include': True},
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'out', 'strict': True, 'schema': SCHEMA}}}
    if not model.startswith('anthropic/'):
        body['seed'] = 0; body['reasoning'] = {'enabled': False}
    if model.endswith(':batch') or 'qwen' in model:
        body['provider'] = {'sort': 'price'}
    err = None
    for i in range(4):
        try:
            req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                                         headers={'Authorization': f'Bearer {os.environ["OPENROUTER_API_KEY"]}',
                                                  'Content-Type': 'application/json', 'User-Agent': UA,
                                                  'HTTP-Referer': 'https://github.com/doescodinggiteasier/wknipe-site'})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            u = d.get('usage') or {}
            with LOCK:
                _spent += float(u.get('cost') or 0)
                open(LEDGER, 'a').write(json.dumps({'ts': time.time(), 'model': model, 'tag': tag, 'pt': u.get('prompt_tokens'),
                                                    'ct': u.get('completion_tokens'), 'cost': u.get('cost')}) + '\n')
            txt = d['choices'][0]['message']['content'].strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            out = json.loads(txt)
            if out.get('category') in SCHEMA['properties']['category']['enum']:
                return out
            err = f'bad output {txt[:80]}'
        except Exception as e:
            err = str(e)[:200]
        time.sleep(2 * (i + 1))
    return {'category': None, 'confidence': None, 'error': err}


def pilot(models):
    ev = common.payee_texts()
    hand = [(p, c) for p, (src, c) in common.hand_classes().items() if src == 'o2' and p in ev]
    print(f'{len(hand)} hand-labelled payees with listing text')
    coarse = lambda c: c if c in ('content', 'data') else 'not'
    res = {}
    for m in models:
        with ThreadPoolExecutor(32) as ex:
            outs = list(ex.map(lambda pc: chat(m, evidence(ev[pc[0]]), 'pilot'), hand))
        truth = [coarse(common.HAND_MAP.get(c, 'not')) for _, c in hand]
        pred = [coarse(o['category'] or 'none') for o in outs]
        acc = sum(t == p for t, p in zip(truth, pred)) / len(hand)
        cd_t = [t in ('content', 'data') for t in truth]; cd_p = [p in ('content', 'data') for p in pred]
        tp = sum(a and b for a, b in zip(cd_t, cd_p))
        res[m] = {'n': len(hand), 'acc_3way': round(acc, 3), 'cd_precision': round(tp / max(1, sum(cd_p)), 3),
                  'cd_recall': round(tp / max(1, sum(cd_t)), 3), 'errors': sum(o['category'] is None for o in outs)}
        print(m, res[m], flush=True)
        json.dump(res, open(os.path.join(common.STATE, 'o10_classifier_pilot.json'), 'w'), indent=1)
    json.dump(res, open(os.path.join(common.STATE, 'o10_classifier_pilot.json'), 'w'), indent=1)


def load_cache():
    return {r['payee']: r for r in csv.DictReader(open(CACHE))} if os.path.exists(CACHE) else {}


def run(model, strict=False):
    ev = common.payee_texts()
    cache = load_cache()
    h = lambda p: hashlib.sha1('\n'.join(ev[p]).encode()).hexdigest()[:12]
    todo = [p for p in ev if p not in cache]
    print(f'{len(ev)} listed payees; {len(todo)} not yet classified', flush=True)
    if todo:
        with ThreadPoolExecutor(32) as ex:
            outs = list(ex.map(lambda p: chat(model, evidence(ev[p]), 'classify'), todo))
        for p, o in zip(todo, outs):
            if o['category']:
                cache[p] = {'payee': p, 'category': o['category'], 'confidence': o['confidence'], 'model': model,
                            'listed_resources': len(ev[p]), 'evidence_sha1': h(p), 'example': ev[p][0][:160]}
    os.makedirs(common.OUT, exist_ok=True)
    with open(CACHE, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['payee', 'category', 'confidence', 'model', 'listed_resources', 'evidence_sha1', 'example'])
        w.writeheader()
        for p in sorted(cache): w.writerow(cache[p])
    print(f'{len(cache)} payees in {CACHE}; OpenRouter ledger total ${spent():.4f}')
    left = [p for p in ev if p not in cache]
    if strict and left:
        raise SystemExit(f'{len(left)} listed payees still unclassified after {model}: {left[:5]}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--pilot', nargs='*'); ap.add_argument('--model'); ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    if a.pilot: pilot(a.pilot)
    elif a.model: run(a.model, a.strict)
    else: print(f'{len(load_cache())} payees cached; pass --model to classify new ones')
