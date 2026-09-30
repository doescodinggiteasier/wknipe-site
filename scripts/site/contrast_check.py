#!/usr/bin/env python3
"""ORDER_013: WCAG 2.2 contrast check for every text/background pair the site uses, read from the one palette in
site/theme-base.scss ($wk-palette). Exit 1 if any required pair fails.

Text needs 4.5:1 (AA normal text); large text (>= 24px, or >= 18.66px bold: KPI numbers, headings) and UI parts
(focus rings, chart marks, input borders that identify a control) need 3:1. Decorative rules (gold underlines) are
reported but not required. Usage: python3 scripts/site/contrast_check.py [--md]"""
import os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def palette():
    s = open(os.path.join(ROOT, 'site', 'theme-base.scss')).read()
    out = {}
    for mode in ('light', 'dark'):
        m = re.search(mode + r':\s*\((.*?)\n\s*\)', s, re.S)
        body = re.sub(r'//[^\n]*', '', m.group(1))
        out[mode] = dict(re.findall(r'([\w-]+):\s*(#[0-9A-Fa-f]{6})', body))
    return out


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, required ratio or None for decorative, what it is)
PAIRS = [
    ('ink', 'bg', 4.5, 'body text'), ('ink', 'surface', 4.5, 'text on cards'),
    ('muted', 'bg', 4.5, 'secondary text'), ('muted', 'surface', 4.5, 'secondary text on cards'),
    ('purple', 'bg', 4.5, 'links, nav active'), ('purple', 'surface', 4.5, 'links on cards'),
    ('purple', 'purple-tint', 4.5, 'selected menu item'), ('ink', 'purple-tint', 4.5, 'row hover text'),
    ('surface', 'purple', 4.5, 'button / selected chip text'),
    ('gold-text', 'bg', 4.5, 'gold text (eyebrows, sort arrows)'), ('gold-text', 'surface', 4.5, 'gold text on cards'),
    ('gold-text', 'gold-tint', 4.5, 'gold pill text'),
    ('pos', 'surface', 4.5, 'WoW delta up'), ('neg', 'surface', 4.5, 'WoW delta down'),
    ('bg', 'ink', 4.5, 'tooltip text'),
    ('purple', 'bg', 3.0, 'focus ring (UI)'), ('series-primary', 'surface', 3.0, 'primary chart series'),
    ('series-clean', 'surface', 3.0, 'clean chart series'),
    *[(f'c-{c}', 'surface', 3.0, f'category colour: {c}') for c in ('content', 'data', 'search', 'compute', 'other', 'large_ticket')],
    ('c-unclassed', 'surface', None, 'unclassed (neutral, always labelled)'), ('series-raw', 'surface', None, 'raw series (recessive, labelled)'),
    ('gold', 'bg', None, 'gold rules / KPI underline (decorative)'), ('gold', 'surface', None, 'gold rules on cards (decorative)'),
    ('line', 'surface', None, 'hairlines (decorative)'),
]


def main():
    pal = palette(); fails = 0; rows = []
    for mode in ('light', 'dark'):
        P = pal[mode]
        for fg, bg, need, what in PAIRS:
            r = ratio(P[fg], P[bg])
            ok = None if need is None else r >= need
            fails += ok is False
            rows.append((mode, fg, P[fg], bg, P[bg], r, need, ok, what))
    if '--md' in sys.argv:
        print('| Mode | Foreground | Background | Ratio | Needs | Result | Use |\n|---|---|---|--:|--:|---|---|')
        for m, fg, f, bg, b, r, need, ok, what in rows:
            print(f"| {m} | {fg} `{f}` | {bg} `{b}` | {r:.2f} | {need or '–'} | {'pass' if ok else 'FAIL' if ok is False else 'decorative'} | {what} |")
    else:
        for m, fg, f, bg, b, r, need, ok, what in rows:
            print(f"{m:5} {fg:15} {f} on {bg:12} {b}  {r:5.2f}  {'>= ' + str(need) if need else 'decor':7} {'PASS' if ok else 'FAIL' if ok is False else '-':5} {what}")
    print(f'{len(rows)} pairs, {fails} failing')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
