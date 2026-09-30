"""Listing topics for the gap map (/x402/gaps/): a fixed keyword taxonomy over each Bazaar listing's normalised
"what it does" text (from the listing classifier) plus its name. First matching rule wins; order goes from specific to
general. Deterministic and readable on purpose: anyone can see why a listing landed in a topic."""
import re

TOPICS = [
    # key, label, regex over "what + name" (lower case)
    ('llm', 'LLM inference & chat', r'\b(llm|chat ?completion|completions?|gpt|claude|gemini|inference|prompt|language model|embedding)'),
    ('image', 'Image & media generation', r'\b(image|video|audio|speech|tts|text to speech|music|avatar|meme|nft art|paint)'),
    ('scrape', 'Web scraping & page extraction', r'\b(scrap\w*|crawl\w*|web ?page|html|markdown|url (content|fetch|extract)|page (fetch|content|extract)|screenshot|website content)'),
    ('websearch', 'Web & news search', r'\b(web search|search results|serp|news|headlines|articles?)\b'),
    ('predmkt', 'Prediction markets', r'\b(prediction market|polymarket|kalshi|odds|betting)'),
    ('signals', 'Trading signals & analytics', r'\b(trading|signals?|open interest|funding rates?|liquidations?|whale|alpha|backtest|leveraged|sentiment|order ?book)'),
    ('tokenrisk', 'Token & contract security', r'\b(rug|honeypot|audit|security|contract risk|token risk|scam|phishing|exploit|vulnerab)'),
    ('cryptoprice', 'Crypto prices & market data', r'\b(crypto|token|coin|defi|dex|swap|pool|tvl|gas price|price feed|ohlc)'),
    ('onchain', 'Wallets & on-chain lookups', r'\b(wallet|address|balance|transaction|block height|blocks?\b|chain|evm|solana|ethereum|base|erc20|ens|onchain|on-chain)'),
    ('stocks', 'Stocks, filings & macro', r'\b(stock|equit|sec|filing|earnings|etf|fund|macro|economic|inflation|treasury|fred)'),
    ('fx', 'FX & currency conversion', r'\b(forex|fx|exchange rates?|currency|conversion rate)'),
    ('company', 'Company & people enrichment', r'\b(company|companies|business|people|person|profile|lead|linkedin|enrich|contact|email finder|registry|employee)'),
    ('social', 'Social media data', r'\b(twitter|tweet|x\.com|reddit|tiktok|instagram|youtube|social|farcaster)'),
    ('domains', 'Domains, DNS & network', r'\b(dns|domain (registration|lookup|availability|whois)|whois|ssl|ip address|ip geo|srv record|mx record|subdomain|http header|uptime)'),
    ('validate', 'Validation & verification', r'\b(validat\w*|verif\w*|iban|vat|phone|email (check|valid)|kyc|captcha)'),
    ('weather', 'Weather & climate', r'\b(weather|forecast|climate|air quality|temperature|rain)'),
    ('travel', 'Travel, flights & places', r'\b(flight|aircraft|airport|hotel|travel|restaurant|reservation|transit|train|places?)\b'),
    ('geo', 'Maps, land & geospatial', r'\b(geocod\w*|geospatial|geolocation|maps?\b|land|soil|elevation|terrain|satellite|surface|gradient|nautical|postal|zip code)'),
    ('docs', 'Documents, PDF & text tools', r'\b(pdf|document|ocr|translat\w*|summar\w*|text|slug|digest|hash|hex|json|csv|convert|format)'),
    ('books', 'Books & public-domain content', r'\b(public domain|e?books? (download|text|search|metadata|lookup)|gutenberg|novels?|poems?|poetry)'),
    ('nft', 'NFTs & onchain media', r'\b(nfts?|erc721|mint\w*|collectibles?)\b'),
    ('storage', 'Storage, files & hosting', r'\b(storage|upload|file|ipfs|arweave|pin\w*|hosting|deploy)'),
    ('sports', 'Sports & games', r'\b(sports?|nba|nfl|soccer|football|game|games|esports|chess|lottery)'),
    ('agents', 'Agent services & payments infra', r'\b(agents?|x402|payment|invoice|receipt|facilitator|escrow|attestation|reputation)'),
    ('code', 'Code & developer tools', r'\b(code|github|repo|package|npm|lint|regex|api test|sandbox|compile|execute)'),
    ('calc', 'Calculators & scores', r'\b(calculat\w*|score|risk|estimate|compute)'),
]
_RX = [(k, lab, re.compile(rx)) for k, lab, rx in TOPICS]
LABEL = {k: lab for k, lab, _ in TOPICS} | {'other': 'Everything else'}


def topic(what, name=''):
    s = f'{what or ""} {name or ""}'.lower()
    for k, _, rx in _RX:
        if rx.search(s): return k
    return 'other'
