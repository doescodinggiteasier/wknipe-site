#!/usr/bin/env python3
"""x402 Clean Index MCP server (ORDER_011 Module A). stdio transport, official MCP Python SDK 2.x (`MCPServer`).

Why Python: the index pipeline (scripts/x402_index/) and its outputs are Python/stdlib CSV + JSON, so the server
reads them with no extra parsing layer, and the official SDK ships on PyPI (`mcp==2.2.0`).

Data source (environment):
  X402_INDEX_DATA  local folder with weekly.csv, prices_weekly.csv, payees_weekly.csv, headline.json
                   (default: ../../data/x402_index next to this file)
  X402_INDEX_API   optional base URL of the public API (e.g. https://api.wknipe.com). When set, latest_week()
                   and method() read the API's free routes. The other tools stay local: their API routes cost
                   $0.001 per call over x402.
  best_execution() always calls the API (default https://api.wknipe.com). The full ranking is the paid route
  GET /v1/route ($0.001 per call over x402) and needs a wallet:
  X402_PAYER_PRIVATE_KEY  key of a Base wallet holding a little USDC (optional; needs `pip install "x402[httpx,evm]"`)
  X402_MAX_PRICE_USD      refuse to pay more than this per call (default 0.01)
  Without a wallet the tool returns the free three-pick demo (/v1/route/demo) and says so.
  price_comps() works the same way: paid GET /v1/comps (every comparable) with a wallet, else the free /v1/comps/demo.
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


ROUTE_API = API or 'https://api.wknipe.com'


def _pay_get(url):
    """GET a paid x402 route with the configured wallet. Checks the quoted price against X402_MAX_PRICE_USD first."""
    import asyncio, base64
    import httpx
    from eth_account import Account
    from x402 import x402Client
    from x402.http.clients import wrapHttpxWithPayment
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner
    cap = float(os.environ.get('X402_MAX_PRICE_USD') or 0.01)

    async def go():
        async with httpx.AsyncClient(timeout=30, headers={'User-Agent': UA}) as h:
            pre = await h.get(url)
        if pre.status_code != 402: return pre.json()
        terms = json.loads(base64.b64decode(pre.headers['payment-required']))
        a = next((x for x in terms['accepts'] if x['network'] == 'eip155:8453'), None)
        if not a or int(a['amount']) / 1e6 > cap:
            raise ToolError(f'refusing to pay: quoted {a and int(a["amount"]) / 1e6} USDC is above X402_MAX_PRICE_USD={cap}')
        client = x402Client()
        register_exact_evm_client(client, EthAccountSigner(Account.from_key(os.environ['X402_PAYER_PRIVATE_KEY'])), networks='eip155:8453')
        async with wrapHttpxWithPayment(client, timeout=60, headers={'User-Agent': UA}) as h:
            r = await h.get(url)
        if r.status_code != 200: raise ToolError(f'paid call failed: HTTP {r.status_code}')
        return r.json()
    return asyncio.run(go())


@server.tool()
def best_execution(need: str, max_price_usd: float = 0, verified_only: bool = False, n: int = 10) -> dict:
    """Best execution for an x402 purchase: for a task (e.g. "web search", "token price"), the x402 endpoints that do
    it, ranked by relevance, whether they answered a valid 402 at their listed price in the daily check, whether
    their seller has 5+ genuine buyers, and price. Full ranking = paid route GET /v1/route ($0.001 per call in USDC
    on Base) and needs X402_PAYER_PRIVATE_KEY; without a wallet this returns the free three-pick demo."""
    from urllib.parse import urlencode
    q = {'need': need, **({'max_price': max_price_usd} if max_price_usd else {}), **({'verified': 1} if verified_only else {})}
    if os.environ.get('X402_PAYER_PRIVATE_KEY'):
        return _pay_get(f'{ROUTE_API}/v1/route?' + urlencode({**q, 'n': max(1, min(n, 40))}))
    demo = _api_at(ROUTE_API, '/v1/route/demo?' + urlencode(q))
    demo['note'] = ('Free demo: three picks only. The full ranking is GET /v1/route ($0.001 per call over x402); set '
                    'X402_PAYER_PRIVATE_KEY (a Base wallet with a little USDC) to let this tool pay for it.')
    return demo


@server.tool()
def price_comps(find: str = '', category: str = '') -> dict:
    """Price comps for an x402 API: describe what one paid call returns (e.g. "token price lookup") and/or give a
    category (content | data | search | compute | other). Returns comparable Bazaar listings (at most 3 per seller),
    their posted price distribution (p10 / median / p90 and a log histogram), how many comparables' sellers had 5+
    genuine buyers last week, and the realised median payment at those sellers. Every comparable = paid route
    GET /v1/comps ($0.001 per call in USDC on Base) and needs X402_PAYER_PRIVATE_KEY; without a wallet this returns the
    free summary with the 5 closest matches."""
    from urllib.parse import urlencode
    if category and category not in CATEGORIES[:5]: raise ToolError(f'category must be one of {CATEGORIES[:5]}')
    if not find.strip() and not category: raise ToolError('give find (a short description) and/or category')
    q = urlencode({**({'find': find.strip()} if find.strip() else {}), **({'category': category} if category else {})})
    if os.environ.get('X402_PAYER_PRIVATE_KEY'):
        return _pay_get(f'{ROUTE_API}/v1/comps?{q}')
    demo = _api_at(ROUTE_API, f'/v1/comps/demo?{q}')
    demo['note'] = ('Free summary: the 5 closest comparables only. Every comparable is GET /v1/comps ($0.001 per call over '
                    'x402); set X402_PAYER_PRIVATE_KEY (a Base wallet with a little USDC) to let this tool pay for it.')
    return demo


def _api_at(base, path):
    req = urllib.request.Request(base + path, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


if __name__ == '__main__':
    server.run('stdio')
