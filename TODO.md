# Portfolio Tracker — backlog

Future ideas / deferred work, roughly in priority order. Tick off as done.

- [x] **"Fetching prices…" indicator** — initial load shows a spinner +
      "Fetching live prices…"; refreshes show "updating prices…" in the header.
- [ ] **Manual price override** — set a current price per ticker for instruments
      yfinance can't reach (e.g. delisted funds, new Cboe-AU codes).
- [x] **Total-return benchmarking** — comparison now uses dividend-adjusted
      (accumulation) series on both sides.
- [x] **Actual performance over time** — Performance tab: daily value from the
      ledger, TWR + XIRR vs benchmarks. (Dividend income uses yfinance ex-date
      data, assumed taken as cash.)
- [ ] **Cache full price histories** — /portfolio/performance re-downloads
      ~max-period history for every ticker on each request (parallel, so a few
      seconds, but a short-TTL cache would make period switching instant).
- [ ] **Reconcile dividends against the CMC export** — the export has the
      actually-received dividend rows (incl. DRP); use them instead of/alongside
      yfinance ex-date estimates, and add franking-credit tracking. Also fold
      received distributions into Holdings/Summary gain-loss.
- [ ] **Risk metrics on actual history** (Phase 2) — volatility, max drawdown,
      tracking error, information ratio, beta on the daily TWR series.
- [ ] **Per-person / household CGT split** — currently treated as one tax entity.
- [ ] **Per-trade-date FX** for exact AUD CGT on foreign-currency trades.
- [ ] **CGT indexation method** — the 50% discount is expected to be replaced by
      an inflation/indexation approach; add the alternate calc when it lands.
- [ ] **Dock app (.app)** — wrap the launcher so there's no terminal window.
