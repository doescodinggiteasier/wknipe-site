#!/usr/bin/env python3
"""Seed the board with the ORDER_008 main run (2026-09-29): the same instrument, bank (seed 8008, n = 48), cells and
settings, so no model is re-run. Keeps family I, condition C0, labels none / A / D / B; drops the prose `raw` field.
Reads local/o8/main_raw.jsonl (private working file). Writes data/agentbuy/runs/<model>.jsonl.
Usage: python3 scripts/agentbuy/import_o8.py"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import CELLS, RUNS, slug  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(ROOT, 'local', 'o8', 'main_raw.jsonl')
# Routing and reasoning exactly as ORDER_008 ran them (scripts/o8/run.py MODELS).
O8 = {
    'openai/gpt-6.1-sol': {'provider_order': ['openai/flex'], 'reasoning': 'low'},
    'google/gemini-3.8-flash': {'provider_order': ['google-ai-studio/flex', 'google-vertex/global/flex'], 'reasoning': 'low'},
    'deepseek/deepseek-v4-pro': {'provider_order': ['baidu/fp8', 'gmicloud/fp8'], 'reasoning': 'low'},
    'anthropic/claude-sonnet-5.5': {'provider_order': 'OpenRouter default', 'reasoning': 'low'},
    'mistralai/mistral-small-3.2-24b-instruct': {'provider_order': 'OpenRouter default', 'reasoning': 'none (not supported)'},
}


def main():
    keep = {}
    for l in open(SRC):
        r = json.loads(l)
        if r['family'] != 'I' or r['cond'] != 'C0' or r.get('label') not in CELLS or r['model'] not in O8: continue
        keep[(r['model'], r['sid'], r.get('label'), r['rep'])] = r  # last record per trial (a resumed run re-ran api errors)
    by = {}
    for (m, sid, lab, rep), r in keep.items():
        s = {**O8[m], 'max_tokens': 8000, 'temperature': 'provider default', 'response_format': 'json_schema (strict)',
             'condition': 'C0', 'family': 'I'}
        by.setdefault(m, []).append({
            'model': m, 'sid': sid, 'label': lab, 'rep': rep, 'choice': r['choice'], 'parse': r['parse'],
            'reason': (r.get('reason') or '')[:400], 'provider': r.get('provider'), 'model_served': r.get('model_served'),
            'finish': r.get('finish'), 'usage': r.get('usage') or {}, 'optimal': r['optimal'], 'regret_share_V': r['regret_share_V'],
            'is_optimal': r['is_optimal'], 'bought': r['bought'], 'buy_optimal': r['buy_optimal'],
            'optimal_bonded': r['optimal_bonded'], 'V': r['V'], 'date': '2026-09-29', 'settings': s, 'source': 'ORDER_008 main run'})
    os.makedirs(RUNS, exist_ok=True)
    for m, rows in by.items():
        rows.sort(key=lambda r: (str(r['label']), r['sid'], r['rep']))
        with open(os.path.join(RUNS, slug(m) + '.jsonl'), 'w') as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(m, len(rows))


if __name__ == '__main__':
    main()
