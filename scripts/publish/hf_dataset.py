#!/usr/bin/env python3
"""ORDER_013 Phase 5: mirror the weekly CSVs to a Hugging Face dataset (needs HF_TOKEN; Wes creates it).

  python3 scripts/publish/hf_dataset.py --build            # assemble local/hf_dataset/ (card + CSVs), no network
  HF_TOKEN=... python3 scripts/publish/hf_dataset.py --push [--repo OWNER/x402-clean-index]
The token is HF_TOKEN or HF_DATASET_MIRROR_TOKEN (the GitHub Actions secret). Without --repo the dataset goes to
<token owner>/x402-clean-index.
Upload uses huggingface_hub (pip install huggingface_hub) with a write token scoped to that one dataset repo.
"""
import argparse, datetime as dt, glob, json, os, shutil, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'local', 'hf_dataset')
FILES = {'x402_index': ['weekly.csv', 'prices_weekly.csv', 'payees_weekly.csv'],
         'x402_market': ['waterfall.csv', 'category_mix.csv', 'concentration.csv', 'buyers_weekly.csv', 'retention.csv', 'buyer_tiers.csv',
                         'tickets.csv', 'ticket_histogram.csv', 'facilitators.csv', 'tripwire.csv', 'movers.csv'],
         'x402_prices': ['posted_by_category.csv', 'posted_vs_paid.csv'], 'x402_status': ['status_daily.csv'],
         'ai_access': ['access_weekly.csv'], 'bazaar_daily': ['counts.csv', 'price_changes.csv']}


def build():
    if os.path.isdir(OUT): shutil.rmtree(OUT)
    configs = []
    for sub, names in FILES.items():
        for n in names:
            src = os.path.join(ROOT, 'data', sub, n)
            if not os.path.exists(src): continue
            os.makedirs(os.path.join(OUT, sub), exist_ok=True); shutil.copy(src, os.path.join(OUT, sub, n))
            configs.append((f'{sub}__{n[:-4]}', f'{sub}/{n}'))
    head = json.load(open(os.path.join(ROOT, 'data', 'x402_index', 'headline.json')))
    yaml_cfg = '\n'.join(f'- config_name: {c}\n  data_files: "{p}"' for c, p in configs)
    card = f'''---
license: cc-by-4.0
pretty_name: x402 Clean Index (wknipe.com)
tags: [x402, agent-payments, stablecoins, base, ai-agents, economics]
configs:
{yaml_cfg}
---
# x402 Clean Index

Weekly, demand-cleaned statistics for the x402 agent-payment protocol on Base: what survives after removing
manufactured (loops, shared funding, fan-out), single-buyer and test payments; buyers, sellers, prices, facilitators;
plus a daily endpoint monitor and a weekly census of AI-crawler access on the top 1,000 sites.

- Latest week: {head['latest_week']} · weeks: {', '.join(head['weeks_available'])} · built {dt.date.today()}
- Dashboard: https://wknipe.com/x402/ · API: https://api.wknipe.com/v1/metrics · Method: https://github.com/doescodinggiteasier/wknipe-site/blob/main/docs/X402_INDEX_METHOD.md
- Licence: CC BY 4.0. Cite: Wes Knipe, *x402 Clean Index*, wknipe.com.
- Cleaned figures are an upper bound on genuine demand (the manufacture filters are lower bounds).
'''
    open(os.path.join(OUT, 'README.md'), 'w').write(card)
    print(f'{len(configs)} files -> {OUT}')


def push(repo):
    tok = os.environ.get('HF_TOKEN') or os.environ.get('HF_DATASET_MIRROR_TOKEN')
    if not tok: sys.exit('HF_TOKEN / HF_DATASET_MIRROR_TOKEN is not set')
    from huggingface_hub import HfApi
    api = HfApi(token=tok)
    repo = repo or f"{api.whoami()['name']}/x402-clean-index"
    api.create_repo(repo, repo_type='dataset', exist_ok=True)
    api.upload_folder(folder_path=OUT, repo_id=repo, repo_type='dataset', commit_message=f'weekly update {dt.date.today()}')
    print(f'pushed to https://huggingface.co/datasets/{repo}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--build', action='store_true'); ap.add_argument('--push', action='store_true')
    ap.add_argument('--repo')
    a = ap.parse_args()
    if a.build or a.push: build()
    if a.push: push(a.repo)
