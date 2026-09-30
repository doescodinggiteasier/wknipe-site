#!/usr/bin/env python3
"""Which models buy well: a repeatable purchase-decision benchmark for AI agents (ORDER_012 Build 3).

The ORDER_008 instrument, unchanged (task.py; scenario bank seed 8008, n = 48, sha256 printed by --info):
an agent with authority to spend a client's money on information must pick one option (skip, buy one document, buy all 3,
read teasers then buy one, or buy an evaluator's certificate then the top pick). Payoffs are exact, so the optimum is
computed, not judged. Family I: prices in the seller's own units with conversions stated, track records as counts.
Condition C0: the agent alone, one call, reasoning on at effort "low" where the model supports it.

Cells per model (48 scenarios x 3 repeats each = 576 decisions):
  -  no label                          -> optimal %, regret, flip rate, discrimination, $ per decision
  A  evaluator's record verified        \\
  D  decorative "Popular" badge          > badge-vs-verified gap (A - D) and badge effect (D - none)
  B  bond: document refunded if pick fails -> bond responsiveness (observed B - A shift in P(certificate) vs the rational shift)

Usage:
  export OPENROUTER_API_KEY=$(security find-generic-password -s openrouter -w)
  python3 scripts/agentbuy/run.py --model deepseek/deepseek-v4.1-flash --pilot     # 16 decisions: validity + cost estimate
  python3 scripts/agentbuy/run.py --model deepseek/deepseek-v4.1-flash --cap 5     # the 576-decision run (resumes)
  python3 scripts/agentbuy/analyze.py                                             # rebuild data/agentbuy/board.json
  python3 scripts/agentbuy/run.py --info                                          # bank sha, prompts, settings
Options: --provider a,b (OpenRouter provider order; default: cheapest), --reasoning low|none|default, --workers N.
Spend: every call is appended to AGENTBUY_LEDGER (default local/agentbuy_or_ledger.jsonl); --cap stops this invocation.
"""
import argparse, concurrent.futures as cf, datetime as dt, json, os, re, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import task as T  # noqa: E402  (frozen ORDER_008 instrument)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
RUNS = os.path.join(ROOT, 'data', 'agentbuy', 'runs')
LEDGER = os.environ.get('AGENTBUY_LEDGER') or os.path.join(ROOT, 'local', 'agentbuy_or_ledger.jsonl')
UA = 'wknipe-agentbuy/1.0 (github.com/doescodinggiteasier/wknipe-site)'
SEED, N, REPS = 8008, 48, 3
PILOT_SEED, PILOT_N, PILOT_REPS = 8001, 8, 2
CELLS = [None, 'A', 'D', 'B']
LOCK = threading.Lock()


class CapReached(Exception):
    pass


class Runner:
    def __init__(self, model, provider, reasoning, cap):
        self.model, self.provider, self.reasoning, self.cap, self.spent = model, provider, reasoning, cap, 0.0

    def settings(self):
        return {'reasoning': self.reasoning, 'provider_order': self.provider or 'price-sorted', 'max_tokens': 8000,
                'temperature': 'provider default', 'response_format': 'json_schema (strict)', 'condition': 'C0', 'family': 'I'}

    def post(self, messages):
        with LOCK:
            if self.spent >= self.cap: raise CapReached(f'cap ${self.cap} reached (${self.spent:.4f})')
        body = {'model': self.model, 'messages': messages, 'max_tokens': 8000, 'usage': {'include': True},
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'choice', 'strict': True, 'schema': T.CHOICE_SCHEMA}}}
        if self.reasoning in ('low', 'medium', 'high'): body['reasoning'] = {'effort': self.reasoning}
        body['provider'] = {'order': self.provider, 'allow_fallbacks': True} if self.provider else {'sort': 'price'}
        err = None
        for i in range(4):
            try:
                req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                                             headers={'Authorization': f'Bearer {os.environ["OPENROUTER_API_KEY"]}',
                                                      'Content-Type': 'application/json', 'User-Agent': UA,
                                                      'HTTP-Referer': 'https://wknipe.com/agents/', 'X-Title': 'wknipe agentbuy'})
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=600) as r:
                    d = json.loads(r.read())
                if 'choices' not in d: raise RuntimeError(str(d)[:300])
                u = d.get('usage') or {}
                cost = float(u.get('cost') or 0)
                with LOCK:
                    self.spent += cost
                    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
                    with open(LEDGER, 'a') as f:
                        f.write(json.dumps({'ts': time.time(), 'model': self.model, 'tag': 'agentbuy', 'pt': u.get('prompt_tokens'),
                                            'ct': u.get('completion_tokens'), 'cost': cost, 'provider': d.get('provider')}) + '\n')
                return d, {'pt': u.get('prompt_tokens') or 0, 'ct': u.get('completion_tokens') or 0,
                           'rt': (u.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0, 'cost': cost,
                           'secs': round(time.time() - t0, 2)}, None
            except urllib.error.HTTPError as e:
                err = f'HTTP {e.code}: {e.read()[:300]!r}'
                if e.code in (400, 401, 403, 404): break
                time.sleep(3 * (i + 1))
            except Exception as e:
                err = str(e)[:300]; time.sleep(3 * (i + 1))
        return None, {}, err

    def trial(self, s, label, rep):
        d, u, err = self.post(T.messages(s, 'I', 'C0', label))
        if d is None:
            r = {'choice': 'NO_CHOICE', 'parse': 'api_error', 'error': err}
        else:
            txt = d['choices'][0]['message'].get('content') or ''
            t = txt.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            out, how = None, 'error'
            try: out, how = json.loads(t), 'json'
            except Exception:
                m = re.search(r'\{.*\}', t, re.S)
                if m:
                    try: out, how = json.loads(m.group(0)), 'json_embedded'
                    except Exception: pass
            ch = (out or {}).get('choice')
            if ch not in T.ACTIONS:
                m = re.search(r'"choice"\s*:\s*"([a-z_]+)"', txt)
                ch, how = (m.group(1), 'salvaged') if m and m.group(1) in T.ACTIONS else ('NO_CHOICE', 'error')
            r = {'choice': ch, 'parse': how, 'reason': ((out or {}).get('reason') or '')[:400], 'provider': d.get('provider'),
                 'model_served': d.get('model'), 'finish': d['choices'][0].get('finish_reason')}
        return {'model': self.model, 'sid': s['sid'], 'label': label, 'rep': rep, **r, 'usage': u,
                **T.score(s, r['choice'], label), 'optimal_bonded': s['optimal_bonded'], 'V': s['V'],
                'date': dt.date.today().isoformat(), 'settings': self.settings(), 'source': 'agentbuy'}


def slug(model):
    return model.replace('/', '__').replace(':', '_')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model'); ap.add_argument('--pilot', action='store_true'); ap.add_argument('--info', action='store_true')
    ap.add_argument('--provider'); ap.add_argument('--reasoning', default='low', choices=['low', 'medium', 'high', 'none', 'default'])
    ap.add_argument('--cap', type=float, default=5.0); ap.add_argument('--workers', type=int, default=24)
    a = ap.parse_args()
    if a.info:
        b = T.make_bank(N, SEED)
        print(json.dumps({'bank_seed': SEED, 'n_scenarios': N, 'reps': REPS, 'bank_sha256': T.bank_sha(b), 'cells': CELLS,
                          'system_prompt': T.SYS, 'example_prompt': T.messages(b[0], 'I', 'C0')[1]['content']}, indent=1))
        return
    if not a.model: ap.error('--model is required')
    run = Runner(a.model, a.provider.split(',') if a.provider else None, a.reasoning, a.cap)
    if a.pilot:
        bank = T.make_bank(PILOT_N, PILOT_SEED)
        jobs = [(s, None, r) for s in bank for r in range(PILOT_REPS)]
        with cf.ThreadPoolExecutor(a.workers) as ex:
            recs = list(ex.map(lambda j: run.trial(*j), jobs))
        ok = [r for r in recs if r['parse'] != 'api_error']
        n = len(recs)
        cost = sum((r['usage'] or {}).get('cost', 0) for r in recs)
        print(json.dumps({'model': a.model, 'pilot_decisions': n, 'api_errors': n - len(ok),
                          'no_choice': sum(r['choice'] == 'NO_CHOICE' for r in recs), 'optimal': sum(r['is_optimal'] for r in recs),
                          'usd': round(cost, 5), 'usd_per_decision': round(cost / n, 6),
                          'projected_full_run_usd': round(cost / n * N * REPS * len(CELLS), 3),
                          'secs_per_decision': round(sum((r['usage'] or {}).get('secs', 0) for r in recs) / max(1, len(ok)), 1),
                          'providers': sorted({str(r.get('provider')) for r in ok}), 'served': sorted({str(r.get('model_served')) for r in ok}),
                          'errors': sorted({r.get('error', '')[:120] for r in recs if r['parse'] == 'api_error'})[:3]}, indent=1))
        os.makedirs(os.path.join(ROOT, 'local'), exist_ok=True)
        with open(os.path.join(ROOT, 'local', 'agentbuy_pilots.jsonl'), 'a') as f:
            for r in recs: f.write(json.dumps(r) + '\n')
        return
    out = os.path.join(RUNS, slug(a.model) + '.jsonl')
    os.makedirs(RUNS, exist_ok=True)
    done = set()
    if os.path.exists(out):
        for l in open(out):
            r = json.loads(l)
            if r['parse'] != 'api_error': done.add((r['sid'], r['label'], r['rep']))
    bank = T.make_bank(N, SEED)
    jobs = [(s, lab, rep) for lab in CELLS for s in bank for rep in range(REPS) if (s['sid'], lab, rep) not in done]
    print(f'{a.model}: {len(jobs)} decisions to run ({len(done)} done); cap ${a.cap}', flush=True)
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run.trial, *j) for j in jobs]
        for i, f in enumerate(cf.as_completed(futs)):
            try:
                rec = f.result()
            except CapReached as e:
                print('CAP', e, flush=True); ex.shutdown(cancel_futures=True); break
            with LOCK:
                with open(out, 'a') as fh: fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if i % 100 == 0: print(i, f'${run.spent:.4f}', flush=True)
    print(f'done: ${run.spent:.4f} this run -> {out}', flush=True)


if __name__ == '__main__':
    main()
