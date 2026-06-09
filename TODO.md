# Portfolio Tracker — backlog

Future ideas / deferred work, roughly in priority order. Tick off as done.

- [ ] **"Fetching prices…" indicator** — the first load after a restart/import
      fetches live prices for all tickers (a few seconds). Show a clear loading
      state so it never looks stuck.
- [ ] **Manual price override** — set a current price per ticker for instruments
      yfinance can't reach (e.g. delisted funds, new Cboe-AU codes).
- [ ] **Dividends / total return** — the CMC export already contains dividend &
      distribution rows; use them for total-return performance and franking.
- [ ] **Per-person / household CGT split** — currently treated as one tax entity.
- [ ] **Per-trade-date FX** for exact AUD CGT on foreign-currency trades.
- [ ] **CGT indexation method** — the 50% discount is expected to be replaced by
      an inflation/indexation approach; add the alternate calc when it lands.
- [ ] **Dock app (.app)** — wrap the launcher so there's no terminal window.
