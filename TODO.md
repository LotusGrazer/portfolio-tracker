# Portfolio Tracker — backlog

Future ideas / deferred work, roughly in priority order. Tick off as done.

- [x] **"Fetching prices…" indicator** — initial load shows a spinner +
      "Fetching live prices…"; refreshes show "updating prices…" in the header.
- [ ] **Manual price override** — set a current price per ticker for instruments
      yfinance can't reach (e.g. delisted funds, new Cboe-AU codes).
- [x] **Total-return benchmarking** — comparison now uses dividend-adjusted
      (accumulation) series on both sides.
- [ ] **Total return of *actual* holdings** — fold the distributions you've
      actually received (in the CMC export) into Holdings/Summary gain-loss, and
      add franking-credit tracking.
- [ ] **Per-person / household CGT split** — currently treated as one tax entity.
- [ ] **Per-trade-date FX** for exact AUD CGT on foreign-currency trades.
- [ ] **CGT indexation method** — the 50% discount is expected to be replaced by
      an inflation/indexation approach; add the alternate calc when it lands.
- [ ] **Dock app (.app)** — wrap the launcher so there's no terminal window.
