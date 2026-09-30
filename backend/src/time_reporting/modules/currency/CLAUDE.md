# currency module

Owns `ExchangeRate` (table `exchange_rates`): a cache of published daily rates, "SEK per one unit
of `currency`". No other table; the company's base currency is a `company` setting, not stored here.

## Lookup

`GetExchangeRate(currency, on_date)` is the only bus message — a **command** despite being a read, because a cache miss stores the
fetched rates and only a command's outermost `execute()` commits (nested in another module's
command, it commits with that command):

- `SEK` → 1, no lookup (`source = "none"`).
- A cache row for exactly `on_date` → returned as is. **Only an exact hit counts**: a cached rate
  from an earlier day can't prove no later banking day (still `<= on_date`) exists, so a miss
  fetches the window `[on_date - 10 days, on_date]` from the source, stores every observation in
  it (`ON CONFLICT DO NOTHING`) and answers with the latest one on or before `on_date`. A weekend
  or holiday therefore has no exact row and is re-fetched each time — rare and cheap.
- `ExchangeRateDTO.rate_date` is the banking day the rate was really published for;
  `requested_date` echoes the input, so callers can show "rate of Friday 2026-09-25".
- Failures (nothing published in the lookback window, source down or rate-limited, malformed code)
  raise `ExchangeRateUnavailableError`; the router maps it to 502. Callers decide what to do —
  `purchases` will keep the document unconverted and ask for a manual amount.

## Riksbank source (`riksbank.py`)

`RiksbankClient` talks to the SWEA API (`settings.riksbank_api_url`, anonymous):
`GET /Observations/SEK<CCY>PMI/<from>/<to>` → `[{"date", "value"}]`, banking days only. `204` means
no observations *or* an unknown series; `429` is the anonymous rate limit (a few requests per
minute), surfaced as `RatesSourceError`. `handlers.create_rates_source()` builds the client and is
what tests monkeypatch to inject an `httpx.MockTransport`-backed one.

## HTTP API

`GET /currency/rates/{currency}?on=YYYY-MM-DD` (`AccountantDep`) — for the manual-rate UI and
debugging; 502 when unavailable.
