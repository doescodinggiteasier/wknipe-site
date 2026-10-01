#!/usr/bin/env python3
"""Spawn server.py over stdio with the official MCP client and call every tool once. Exit 0 = all passed.
Usage: .venv/bin/python test_server.py"""
import asyncio, json, os, sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
CALLS = [('latest_week', {}), ('weekly_series', {'stage': 'clean', 'category': 'all'}),
         ('top_sellers', {'category': 'all', 'n': 3}), ('price_stats', {'category': 'data'}), ('method', {}),
         ('market_series', {'metric': 'waterfall', 'week': '2026-09-21'})]
if os.environ.get('X402_INDEX_API'):  # best_execution always calls the API; test it only when one is given
    CALLS.append(('best_execution', {'need': 'web search'}))


async def main():
    params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, 'server.py')], env={**os.environ})
    failures = 0
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            print('tools:', names)
            for name, args in CALLS:
                res = await s.call_tool(name, args)
                text = ''.join(getattr(c, 'text', '') for c in res.content)
                ok = not res.is_error and len(text) > 2
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'} {name}({json.dumps(args)}) -> {text[:160].replace(chr(10), ' ')}")
            res = await s.call_tool('weekly_series', {'stage': 'bogus'})
            ok = res.is_error
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'} weekly_series(stage='bogus') is rejected")
    sys.exit(1 if failures else 0)


asyncio.run(main())
