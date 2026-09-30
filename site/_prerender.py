#!/usr/bin/env python3
"""Quarto pre-render: copy the index data (data/x402_index) into site/x402/data so pages chart it at render time."""
import glob, os, shutil
here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, '..', 'data', 'x402_index')
dst = os.path.join(here, 'x402', 'data')
os.makedirs(dst, exist_ok=True)
for f in ('weekly.csv', 'prices_weekly.csv', 'payees_weekly.csv', 'headline.json'):
    shutil.copy(os.path.join(src, f), dst)
print('copied index data ->', dst)
