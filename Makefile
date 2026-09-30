# wknipe.com convenience targets. Python 3.12 (stdlib), Node 22, Quarto 1.10.

.PHONY: index sellers site agents agents-pilot test

index:            ## rebuild the x402 Clean Index from committed state (no keys, no network)
	X402_STATE=state python3 scripts/x402_index/run.py

sellers:          ## rebuild the seller leaderboard data
	X402_STATE=state python3 scripts/sellers/build.py

site:             ## render the website into site/_site
	cd site && quarto render

test:             ## unit tests for the AI-policy checker
	node --experimental-strip-types apps/x402-index-api/scripts/check.test.mjs

agents-pilot:     ## 16-decision pilot for one model: make agents-pilot MODEL=openrouter/id (needs OPENROUTER_API_KEY)
	python3 scripts/agentbuy/run.py --model $(MODEL) --pilot

agents:           ## full 576-decision run for one model, then rebuild the board: make agents MODEL=openrouter/id [CAP=5]
	python3 scripts/agentbuy/run.py --model $(MODEL) --cap $(or $(CAP),5)
	python3 scripts/agentbuy/analyze.py
