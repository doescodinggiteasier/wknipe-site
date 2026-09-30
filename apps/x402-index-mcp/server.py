#!/usr/bin/env python3
"""x402 Clean Index MCP server (ORDER_011 Module A). stdio transport, official MCP Python SDK 2.x (`MCPServer`).

Why Python: the index pipeline (scripts/x402_index/) and its outputs are Python/stdlib CSV + JSON, so the server
reads them with no extra parsing layer, and the official SDK ships on PyPI (`mcp==2.2.0`).

Data source (environment):
  X402_INDEX_DATA  local folder with weekly.csv, prices_weekly.csv, payees_weekly.csv, headline.json
                   (default: ../../data/x402_index next to this file)
  X402_INDEX_API   optional base URL of the public API (e.g. https://api.wknipe.com). When set, latest_week()
                   and method() read the API's free routes. The other tools stay local: their API routes cost
                   $0.001 per call over x402, and this server holds no wallet.
"""
import csv, json, os, urllib.request

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('X402_INDEX_DATA') or os.path.join(HERE, '..', '..', 'data', 'x402_index')
API = (os.environ.get('X402_INDEX_API') or '').rstrip('/')
METHOD_DOC = os.path.join(HERE, '..', '..', 'docs', 'X402_INDEX_METHOD.md')
STAGES = ('raw', 'd05', 'clean')
CATEGORIES = ('content', 'data', 'search', 'compute', 'other', 'large_ticket', 'unclassed', 'all')
UA = 'x402-index-mcp/0.1 (github.com/doescodinggiteasier/wknipe-site)'

server = MCPServer(
    name='x402-index', version='0.1.0',
    instructions='Weekly, demand-cleaned index of x402 agent payments on Base: USD and payments by filter stage and '
                 'category, prices per call, top sellers. Call method() before quoting numbers; cleaned figures are '
                 'an upper bound on genuine demand.')


def _rows(name):
    with open(os.path.join(DATA, name), newline='') as f:
        return list(csv.DictReader(f))


def _api(path):
    req = urllib.request.Request(API + path, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() and 'e' not in str(v) and '.' not in str(v) else f
    except (TypeError, ValueError):
        return v


@server.tool()
def latest_week() -> dict:
    """Headline numbers for the latest complete week: raw, after the manufacture filter, and demand-cleaned USD;
    cleaned USD by category; the content+data tripwire with its 4-week growth."""
    if API:
        return _api('/v1/latest')
    h = json.load(open(os.path.join(DATA, 'headline.json')))
    keep = ('latest_week', 'weeks_available', 'raw_usd', 'raw_payments', 'd05_usd', 'clean_usd', 'clean_payments',
            'clean_payees', 'clean_by_category_usd', 'tripwire_content_plus_data_clean_usd', 'tripwire_4week_growth',
            'tripwire_4week_base_week', 'tripwire_loglinear_monthly_growth_last_5_weeks')
    return {k: h.get(k) for k in keep}


@server.tool()
def weekly_series(stage: str = 'clean', category: str = 'all') -> list[dict]:
    """Weekly series of payments, USD, sellers and buyers for one filter stage (raw | d05 | clean) and one category
    (content | data | search | compute | other | large_ticket | unclassed | all)."""
    if stage not in STAGES: raise ToolError(f'stage must be one of {STAGES}')
    if category not in CATEGORIES: raise ToolError(f'category must be one of {CATEGORIES}')
    return [{k: _num(v) for k, v in r.items() if k not in ('stage', 'category')}
            for r in _rows('weekly.csv') if r['stage'] == stage and r['category'] == category]


@server.tool()
def top_sellers(category: str = 'all', n: int = 10) -> list[dict]:
    """Top cleaned sellers (payee addresses) by USD in the latest week, optionally within one category."""
    if category not in CATEGORIES: raise ToolError(f'category must be one of {CATEGORIES}')
    rows = _rows('payees_weekly.csv')
    last = max(r['week_start'] for r in rows)
    sel = [r for r in rows if r['week_start'] == last and (category == 'all' or r['category'] == category)]
    sel.sort(key=lambda r: -float(r['usd']))
    return [{k: _num(v) for k, v in r.items()} for r in sel[:max(1, min(n, 100))]]


@server.tool()
def price_stats(category: str = 'all') -> list[dict]:
    """Price per call by week for one category: posted (Bazaar listing) and transacted (cleaned payments) median,
    interquartile range, item count and chain-linked Jevons index (first week = 100) with basket churn."""
    if category not in CATEGORIES: raise ToolError(f'category must be one of {CATEGORIES}')
    return [{k: _num(v) for k, v in r.items() if k != 'category'} for r in _rows('prices_weekly.csv') if r['category'] == category]


MARKET = os.path.join(HERE, '..', '..', 'data', 'x402_market')
MARKET_METRICS = ('waterfall', 'category_mix', 'concentration', 'buyers_weekly', 'retention', 'buyer_spend_histogram',
                  'sellers_per_buyer', 'buyer_tiers', 'tickets', 'facilitators', 'tripwire', 'movers')


@server.tool()
def market_series(metric: str, week: str = '', category: str = '') -> list[dict]:
    """ORDER_013 market statistics behind wknipe.com/x402/ (one of: waterfall = USD each filter removes;
    category_mix; concentration = top-1/top-10 share and HHI; buyers_weekly = new/returning genuine buyers;
    retention; buyer_spend_histogram; sellers_per_buyer; buyer_tiers; tickets = payment size p10/median/p90;
    facilitators = raw vs clean per facilitator; tripwire; movers). Optional week (YYYY-MM-DD) and category filters."""
    if metric not in MARKET_METRICS: raise ToolError(f'metric must be one of {MARKET_METRICS}')
    if API:
        q = f'/v1/series?metric={metric}' + (f'&week={week}' if week else '') + (f'&category={category}' if category else '')
        return _api(q)['rows']
    with open(os.path.join(MARKET, metric + '.csv'), newline='') as f:
        rows = list(csv.DictReader(f))
    if week: rows = [r for r in rows if r.get('week_start', r.get('cohort_week')) == week]
    if category: rows = [r for r in rows if r.get('category') == category]
    return [{k: _num(v) for k, v in r.items()} for r in rows]


@server.tool()
def method() -> dict:
    """Key definitions of the index: what a settlement is, the filters, the categories, and known biases."""
    if API:
        return _api('/v1/method')
    text = open(METHOD_DOC).read()
    secs = {}
    for part in text.split('\n## ')[1:]:
        title, _, body = part.partition('\n')
        secs[title.strip()] = body.strip()
    want = [k for k in secs if k.split('.')[0] in ('1', '2', '3', '6')]
    return {'source': 'docs/X402_INDEX_METHOD.md', **{k: secs[k] for k in want}}


if __name__ == '__main__':
    server.run('stdio')
