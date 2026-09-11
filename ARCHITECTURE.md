# Architecture & Roadmap Status

Living document. Update this whenever a phase moves from "not started" to "in progress" to "done," and whenever a real architectural decision gets made. This is how a cold read of the repo in a month tells you what's actually true, not just what was planned.

## Roadmap status

| Phase | What it is | Status |
|---|---|---|
| 0 | Repo scaffolding (structure, README, tests, env setup) | **Done** |
| 1 | Data pipeline (market data, news, SEC filings, economic calendar, company events, options data — all timestamped) | Not started |
| 2 | Event normalization (raw news/events → standardized categories) | Not started |
| 3 | Event-response database (event → price before → 5m/15m/30m/1h/4h/1d/3d/5d returns → abnormal return → max favorable/adverse excursion) | Not started |
| 4 | Historical analysis (success rate, avg/median return, distribution, reaction speed, volatility response, relative performance) | Not started |
| 5 | Baseline model (historical similarity + base rates, no ML yet) | Not started |
| 6 | Machine learning (XGBoost/LightGBM etc. — only after Phase 5 is validated and more complexity is justified by measured improvement) | Not started |
| 7 | Options layer (translate stock-movement predictions into option-specific probabilities) | Not started |
| 8 | Market-wide scanner (rank the full liquid universe) | Not started |
| 9 | Live monitoring (continuously process new info, update scores) | Not started |
| 10 | Out-of-sample validation (only after this should predictive performance be taken seriously) | Not started |

## Non-negotiable domain rules (enforced everywhere, not just where convenient)

1. Never output a bare verdict ("buy", "bullish"). Always show the evidence: comparable historical events, base rate/win %, avg/median return, max favorable/adverse excursion, confidence.
2. Direction, magnitude, and speed are always separate outputs — never blended into one score.
3. Use abnormal/relative returns (vs. QQQ or the relevant index), not raw price moves.
4. Every analysis or backtest must be actively checked for look-ahead bias (only use information actually available at the time) and survivorship bias (the historical universe must reflect what was actually tradable at each point in time, including delisted/acquired/bankrupt companies).
5. Respect option expiration — a catalyst that happens after an option's expiration is not a driver for that option.
6. Start simple (historical similarity + base rates, Phase 5) before ML (Phase 6); any added complexity must be justified by a demonstrated out-of-sample improvement.
7. Event importance is ticker/industry-specific — never assume "good news = bullish" as a generic rule; let the data say which events matter for which tickers.
8. Every module states which of the 10 phases above it belongs to.

## Prior work (context, not code we're reusing directly)

Kenny built pieces of this system before, across six separate repos on his laptop (Trading Bot, Options Project, ReadNewsV2, Read News Bot, BustingHeadline, RobinhoodTrading — full detail in the Claude project doc `claude/existing-assets-audit.md`). We're rebuilding clean rather than merging those repos, but keeping them connected as reference: when we reach a phase one of them already attempted, we check what's there and rewrite the useful parts to fit this repo's structure and rules, rather than starting purely from scratch each time. Two findings from that prior work are worth carrying forward as motivation, not as validated conclusions:

- Trading Bot's 1000-ticker 2025 backtest: equity PnL +1.92R but options PnL -16.21R on the same signals — a real example of why Phase 7 (options layer) has to be its own model, not a pass-through of the stock-direction prediction.
- ReadNewsV2's `pattern_learner.py` already computed win-rate/avg-return by (sector, news_type) — the right idea (Phase 4/5), but on raw returns rather than abnormal returns (violates rule 3 above) and mostly on sample sizes too small to trust (many news types had n=1). A useful shape to rebuild correctly, not numbers to trust as-is.

## Decisions log

- **2026-09-11** — Chose a clean rebuild over merging the six prior repos. Reason: they don't share a schema, don't consistently follow the domain rules above, and one of them (RobinhoodTrading) was already wired to place live trades on top of research components that were never validated — execution got ahead of validation. Rebuilding phase-by-phase, in order, with rules enforced from the start, avoids repeating that.
- **2026-09-11** — `src/`-layout Python package (`stock_scanner`), not a flat script folder. Reason: makes `pip install -e .` and imports unambiguous as the codebase grows past a handful of files, and matches the one prior repo (Options Project) that had the cleanest structure of the six.
