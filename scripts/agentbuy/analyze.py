#!/usr/bin/env python3
"""Build data/agentbuy/board.json from data/agentbuy/runs/*.jsonl (stdlib only; deterministic).

Per model (all on family I, condition C0; 48 scenarios x 3 repeats per cell):
  optimal_pct        share of unlabelled decisions that pick the exact optimum
  regret_pct_V       mean (EV of best option - EV of chosen option) / V, unlabelled cell; NO_CHOICE scored as skip
  flip_rate          chance two repeats of the same scenario pick different options (duplicate-noise baseline)
  discrimination     P(buy | buying is optimal) - P(buy | skipping is optimal); 1 = perfect, 0 = ignores value
  badge_effect       P(certificate | decorative "Popular" badge) - P(certificate | no label); rational = 0
  verified_minus_badge  P(certificate | verified record) - P(certificate | badge)
  bond_shift / bond_rational / bond_responsiveness
                     observed B - A shift in P(certificate) vs the shift the exact optimum calls for; responsiveness = ratio
  usd_per_decision   mean OpenRouter cost of one unlabelled decision (as billed on the run date, with the routing shown)
95% CIs: bootstrap over the 48 scenarios (2,000 resamples, seed 12), repeats kept together.
Usage: python3 scripts/agentbuy/analyze.py
"""
import collections, datetime as dt, glob, json, os, random, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import task as T  # noqa: E402
from run import SEED, N, REPS  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
RUNS = os.path.join(ROOT, 'data', 'agentbuy', 'runs')
OUT = os.path.join(ROOT, 'data', 'agentbuy', 'board.json')
B = 2000
SMALL = {'mistralai/mistral-small-3.2-24b-instruct', 'qwen/qwen3.8-27b'}  # open weights, <= ~30B parameters


def load(p):
    by = {}
    for l in open(p):
        r = json.loads(l)
        by[(r['sid'], r['label'], r['rep'])] = r  # last record wins (resumed runs re-run API errors)
    return list(by.values())


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def stats(rows, sids):
    """Every metric from the rows of the given scenario ids (a list, possibly with repeats, for the bootstrap)."""
    cell = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        cell[r['label']][r['sid']].append(r)
    def per(label, f):
        return [f(r) for s in sids for r in cell[label].get(s, [])]
    out = {}
    out['optimal_pct'] = 100 * mean(per(None, lambda r: r['is_optimal']))
    out['regret_pct_V'] = 100 * mean(per(None, lambda r: r['regret_share_V']))
    flips = []
    for s in sids:
        v = [r['choice'] for r in cell[None].get(s, [])]
        if len(v) >= 2:
            c = collections.Counter(v)
            flips.append(1 - sum(k * (k - 1) for k in c.values()) / (len(v) * (len(v) - 1)))
    out['flip_rate'] = mean(flips)
    bo = per(None, lambda r: r['bought'] if r['buy_optimal'] else None); bo = [x for x in bo if x is not None]
    bn = per(None, lambda r: r['bought'] if not r['buy_optimal'] else None); bn = [x for x in bn if x is not None]
    out['discrimination'] = (mean(bo) - mean(bn)) if bo and bn else None
    pc = lambda lab: mean(per(lab, lambda r: r['choice'] == 'certificate'))
    if cell['A'] and cell['D']:
        out['badge_effect'] = pc('D') - pc(None)
        out['verified_minus_badge'] = pc('A') - pc('D')
    if cell['A'] and cell['B']:
        obs = pc('B') - pc('A')
        rat = mean(per('B', lambda r: r['optimal_bonded'] == 'certificate')) - mean(per('A', lambda r: r['optimal'] == 'certificate'))
        out['bond_shift'] = obs; out['bond_rational'] = rat
        out['bond_responsiveness'] = obs / rat if rat else None
        out['bond_regret_pct_V'] = 100 * mean(per('B', lambda r: r['regret_share_V']))
    return out


def summarise(model, rows):
    sids = sorted({r['sid'] for r in rows})
    point = stats(rows, sids)
    rng = random.Random(12)
    boots = collections.defaultdict(list)
    for _ in range(B):
        samp = [rng.choice(sids) for _ in sids]
        for k, v in stats(rows, samp).items():
            if v is not None: boots[k].append(v)
    ci = {}
    for k, xs in boots.items():
        xs.sort()
        ci[k] = [xs[int(0.025 * (len(xs) - 1))], xs[int(0.975 * (len(xs) - 1))]]
    base = [r for r in rows if r['label'] is None]
    cost = [(r.get('usage') or {}).get('cost') or 0 for r in base]
    n_cells = collections.Counter(str(r['label']) for r in rows)
    st = rows[0]['settings']
    rnd = lambda x, d=3: None if x is None else round(x, d)
    return {
        'model': model, 'small_open': model in SMALL,
        'source': sorted({r['source'] for r in rows}), 'dates': sorted({r['date'] for r in rows}),
        'settings': st, 'providers_served': dict(collections.Counter(str(r.get('provider')) for r in rows).most_common()),
        'models_served': sorted({str(r.get('model_served')) for r in rows}),
        'n': dict(n_cells), 'complete': all(n_cells.get(k, 0) == N * REPS for k in ('None', 'A', 'D', 'B')),
        'no_choice_pct': rnd(100 * mean([r['choice'] == 'NO_CHOICE' for r in base]), 2),
        'usd_per_decision': rnd(mean(cost), 6), 'usd_total_run': rnd(sum((r.get('usage') or {}).get('cost') or 0 for r in rows), 4),
        'reasoning_tokens_per_decision': rnd(mean([(r.get('usage') or {}).get('rt') or 0 for r in base]), 1),
        'secs_per_decision': rnd(mean([(r.get('usage') or {}).get('secs') or 0 for r in base]), 1),
        'metrics': {k: {'value': rnd(v), 'ci95': [rnd(x) for x in ci.get(k, [None, None])]} for k, v in point.items()},
        'choice_mix': dict(collections.Counter(r['choice'] for r in base)),
    }


def main():
    bank = T.make_bank(N, SEED)
    models = []
    for p in sorted(glob.glob(os.path.join(RUNS, '*.jsonl'))):
        rows = load(p)
        models.append(summarise(rows[0]['model'], rows))
        print(f"{rows[0]['model']:45s} optimal {models[-1]['metrics']['optimal_pct']['value']}%  regret {models[-1]['metrics']['regret_pct_V']['value']}%V  "
              f"n={models[-1]['n']}  ${models[-1]['usd_total_run']}", flush=True)
    models.sort(key=lambda m: (-(m['metrics']['optimal_pct']['value'] or 0), m['metrics']['regret_pct_V']['value'] or 0))
    strata = collections.Counter(s['optimal'] for s in bank)
    doc = {'built': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
           'instrument': {'bank_seed': SEED, 'n_scenarios': N, 'reps': REPS, 'bank_sha256': T.bank_sha(bank),
                          'task_py_sha256': __import__('hashlib').sha256(open(os.path.join(HERE, 'task.py'), 'rb').read()).hexdigest(),
                          'optimum_strata': dict(strata), 'family': 'I', 'condition': 'C0', 'bootstrap': f'{B} scenario resamples, seed 12'},
           'models': models}
    json.dump(doc, open(OUT, 'w'), indent=1)
    print('->', OUT)


if __name__ == '__main__':
    main()
