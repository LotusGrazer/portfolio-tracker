"""HTTP-level tests for the Flask endpoints via the test client."""
import io

HOLDINGS_CSV = (
    "ticker,quantity,cost_base_per_unit,date_acquired,broker,asset_class,exchange\n"
    "VAS,10,90.00,2022-03-01,Commsec,etf,ASX\n"
    "AAPL,10,150.00,2023-09-01,IBKR,stock,US\n"
)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_holdings_empty_then_populated(client):
    assert client.get("/holdings").get_json() == []

    resp = client.post("/holdings/upload", data=HOLDINGS_CSV, content_type="text/csv")
    assert resp.status_code == 201
    assert resp.get_json()["added"] == 2

    holdings = client.get("/holdings").get_json()
    assert len(holdings) == 2
    vas = next(h for h in holdings if h["ticker"] == "VAS")
    assert vas["symbol"] == "VAS.AX"
    assert vas["market_value_base"] == 1000.0


def test_upload_via_multipart_file(client):
    data = {"file": (io.BytesIO(HOLDINGS_CSV.encode()), "holdings.csv")}
    resp = client.post("/holdings/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert resp.get_json()["added"] == 2


def test_upload_to_named_portfolio(client):
    resp = client.post(
        "/holdings/upload?portfolio=Wife",
        data="ticker,quantity\nVAS,5\n",
        content_type="text/csv",
    )
    assert resp.get_json()["portfolio"] == "Wife"


def test_upload_reports_bad_rows(client):
    resp = client.post(
        "/holdings/upload",
        data="ticker,quantity\nVAS,10\nBAD,xyz\n",
        content_type="text/csv",
    )
    body = resp.get_json()
    assert body["added"] == 1
    assert body["skipped"] == 1
    assert body["errors"][0]["row"] == 3


def test_upload_no_payload_returns_400(client):
    resp = client.post("/holdings/upload")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_upload_missing_ticker_column_returns_400(client):
    resp = client.post(
        "/holdings/upload", data="quantity\n10\n", content_type="text/csv"
    )
    assert resp.status_code == 400
    assert "ticker" in resp.get_json()["error"]


def test_summary_endpoint(client):
    client.post("/holdings/upload", data=HOLDINGS_CSV, content_type="text/csv")
    summary = client.get("/portfolio/summary").get_json()
    assert summary["total_market_value"] == 5500.0
    assert summary["base_currency"] == "AUD"
    assert {b["key"] for b in summary["by_broker"]} == {"Commsec", "IBKR"}


def test_benchmarks_via_csv_then_list(client):
    csv_data = "name,ticker,weight_pct,exchange\nASX200,VAS,100,ASX\n"
    resp = client.post("/benchmarks/create", data=csv_data, content_type="text/csv")
    assert resp.status_code == 201

    benchmarks = client.get("/benchmarks").get_json()
    assert len(benchmarks) == 1
    assert benchmarks[0]["name"] == "ASX200"


def test_benchmark_via_json(client):
    resp = client.post(
        "/benchmarks/create",
        json={"name": "Tech", "constituents": [{"ticker": "AAPL", "weight_pct": 100,
                                                "exchange": "US"}]},
    )
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "Tech"


def test_index_html_is_not_cached(client):
    # When the built frontend is served, index.html must not be cached (it
    # references content-hashed bundles). If the build isn't present, skip.
    resp = client.get("/")
    if resp.content_type.startswith("text/html"):
        assert "no-cache" in resp.headers.get("Cache-Control", "")


def test_unknown_route_returns_json_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "not found"}
