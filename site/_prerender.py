#!/usr/bin/env python3
"""Quarto pre-render: copy the index data (data/x402_index, data/x402_sellers) into site/x402/data so pages chart it at
render time, and generate one static page per x402 seller (_sellers_pages.py)."""
import glob, os, shutil, sys
here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, '..', 'data', 'x402_index')
dst = os.path.join(here, 'x402', 'data')
os.makedirs(dst, exist_ok=True)
for f in ('weekly.csv', 'prices_weekly.csv', 'payees_weekly.csv', 'headline.json'):
    shutil.copy(os.path.join(src, f), dst)
print('copied index data ->', dst)
sellers = os.path.join(here, '..', 'data', 'x402_sellers', 'sellers.json')
if os.path.exists(sellers):
    shutil.copy(sellers, dst)
    shutil.copy(os.path.join(here, '..', 'data', 'x402_sellers', 'sellers_latest.csv'), dst)
sys.path.insert(0, here)
import _sellers_pages
print('seller pages:', _sellers_pages.build())
board = os.path.join(here, '..', 'data', 'agentbuy', 'board.json')
if os.path.exists(board):
    os.makedirs(os.path.join(here, 'agents', 'data'), exist_ok=True)
    shutil.copy(board, os.path.join(here, 'agents', 'data'))
pred = os.path.join(here, '..', 'predictions')
if os.path.exists(os.path.join(pred, 'ledger.json')):
    pd = os.path.join(here, 'predictions', 'data')
    if os.path.isdir(pd): shutil.rmtree(pd)
    os.makedirs(os.path.join(pd, 'ots'))
    shutil.copy(os.path.join(pred, 'ledger.json'), pd)
    for f in glob.glob(os.path.join(pred, 'ots', '*.ots')) + glob.glob(os.path.join(pred, 'revealed', '*')):
        shutil.copy(f, os.path.join(pd, 'ots' if f.endswith('.ots') else ''))
paper = os.path.join(here, '..', 'paper', '_output')
paper_page = open(os.path.join(here, 'paper', 'index.qmd')).read()
pfiles = os.path.join(here, 'paper', 'files')
if os.path.isdir(pfiles): shutil.rmtree(pfiles)
# The draft PDF is published only once the paper page is no longer a draft.
if os.path.exists(os.path.join(paper, 'x402_measured.pdf')) and '\ndraft: true' not in paper_page:
    os.makedirs(os.path.join(here, 'paper', 'files'), exist_ok=True)
    for f in ('x402_measured.pdf', 'x402_measured.html'):
        shutil.copy(os.path.join(paper, f), os.path.join(here, 'paper', 'files'))
import _index_pages
print('index entries:', _index_pages.build())
import _pages
print('ORDER_013 pages:', _pages.build())
