import io

import pandas as pd
import pytest

from tests.conftest import make_scada

GET_ENDPOINTS = [
    "/api/health", "/api/turbines", "/api/turbines/status", "/api/turbines/WTG01", "/api/scada",
    "/api/metrics/summary", "/api/metrics/daily", "/api/metrics/monthly", "/api/metrics/availability",
    "/api/metrics/capacity-factor", "/api/metrics/power-curve", "/api/metrics/performance-deviation",
    "/api/metrics/temperature", "/api/anomalies", "/api/downtime", "/api/reports/monthly", "/api/reports/months",
    "/api/data/quality", "/api/data/imports",
]


@pytest.mark.parametrize("url", GET_ENDPOINTS)
def test_get_endpoints_ok(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["turbines"] == 4 and h["data_source"] == "SIMULATED"
    assert h["data_start"] == "2026-04-25" and h["data_end"] == "2026-05-14"


def test_summary_filters_change_results(client):
    all_ = client.get("/api/metrics/summary").json()
    one = client.get("/api/metrics/summary", params={"turbine_id": "WTG01"}).json()
    week = client.get("/api/metrics/summary", params={"start_date": "2026-05-01", "end_date": "2026-05-07"}).json()
    assert one["energy_mwh"] < all_["energy_mwh"] and one["total_turbines"] == 1
    assert week["energy_mwh"] < all_["energy_mwh"]
    assert 80 < all_["availability_pct"] <= 100 and 0 < all_["capacity_factor_pct"] < 100


def test_daily_sums_to_summary(client):
    p = {"start_date": "2026-05-01", "end_date": "2026-05-10"}
    daily = client.get("/api/metrics/daily", params=p).json()
    s = client.get("/api/metrics/summary", params=p).json()
    assert len(daily) == 10
    assert sum(d["energy_mwh"] for d in daily) == pytest.approx(s["energy_mwh"], rel=1e-3)
    by_t = client.get("/api/metrics/daily", params={**p, "by_turbine": True}).json()
    assert len(by_t) == 40


def test_availability_basis(client):
    t = client.get("/api/metrics/availability", params={"basis": "technical"}).json()
    c = client.get("/api/metrics/availability", params={"basis": "contractual"}).json()
    assert c["fleet_availability_pct"] >= t["fleet_availability_pct"]
    assert client.get("/api/metrics/availability", params={"basis": "bogus"}).status_code == 422


def test_power_curve_payload(client):
    r = client.get("/api/metrics/power-curve", params={"turbine_id": "WTG02", "scatter_points": 200}).json()
    assert r["records_used"] > 0 and len(r["scatter"]) == 200 and len(r["bins"]) > 10
    assert {s["turbine_id"] for s in r["scatter"]} == {"WTG02"}
    assert len(r["reference_curve"]) > 40


def test_pagination(client):
    p1 = client.get("/api/scada", params={"page_size": 5, "page": 1}).json()
    p2 = client.get("/api/scada", params={"page_size": 5, "page": 2}).json()
    assert len(p1["items"]) == 5 and p1["total"] > 1000 and p1["pages"] == -(-p1["total"] // 5)
    assert p1["items"][0] != p2["items"][0]
    assert client.get("/api/scada", params={"page_size": 5000}).status_code == 422


def test_anomaly_filters(client):
    all_ = client.get("/api/anomalies", params={"page_size": 1000}).json()
    assert all_["total"] == sum(all_["by_severity"].values())
    for sev in ("High", "Medium", "Low"):
        r = client.get("/api/anomalies", params={"severity": sev, "page_size": 1000}).json()
        assert r["total"] == all_["by_severity"].get(sev, 0)
        assert all(a["severity"] == sev for a in r["items"])
    assert client.get("/api/anomalies", params={"severity": "Critical"}).status_code == 422


@pytest.mark.parametrize("params,code", [
    ({"turbine_id": "WTG99"}, 404),
    ({"start_date": "2026-05-10", "end_date": "2026-05-01"}, 422),
    ({"start_date": "not-a-date"}, 422),
    ({"turbine_id": "bad id!"}, 422),
])
def test_validation_errors(client, params, code):
    assert client.get("/api/metrics/summary", params=params).status_code == code


def test_turbine_404(client):
    assert client.get("/api/turbines/NOPE").status_code == 404


def test_reports_and_exports(client):
    m = client.get("/api/reports/monthly", params={"month": "2026-05"}).json()
    assert m["kpis"]["energy_mwh"] > 0 and m["key_findings"] and m["recommended_investigations"]
    assert "SIMULATED" in m["disclaimer"]
    assert client.get("/api/reports/monthly", params={"month": "2025-01"}).status_code == 404
    assert client.get("/api/reports/monthly", params={"month": "May"}).status_code == 422
    x = client.get("/api/export/excel", params={"month": "2026-05"})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    pdf = client.get("/api/reports/pdf", params={"month": "2026-05"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    for ds in ("daily", "monthly", "turbine_summary", "anomalies", "scada"):
        r = client.get("/api/export/csv", params={"dataset": ds, "turbine_id": "WTG01",
                                                   "start_date": "2026-05-01", "end_date": "2026-05-02"})
        assert r.status_code in (200, 404), ds
        if r.status_code == 200:
            assert "attachment" in r.headers["content-disposition"]
            assert len(pd.read_csv(io.StringIO(r.text))) > 0


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def test_upload_new_rows_duplicates_and_bad_rows(client):
    before = client.get("/api/health").json()["scada_records"]
    new = make_scada(12, turbine="WTG01", start="2026-05-15 00:00:00")       # after the data period
    dup = make_scada(3, turbine="WTG01", start="2026-05-01 00:00:00")        # already in DB
    bad = make_scada(2, turbine="WTG01", start="2026-05-16 00:00:00")
    bad.loc[0, "timestamp"] = "2026-02-31 00:00:00"
    bad.loc[1, "turbine_id"] = "XYZ01"
    payload = pd.concat([new, dup, bad], ignore_index=True)
    r = client.post("/api/data/upload", files={"file": ("batch.csv", _csv_bytes(payload), "text/csv")})
    assert r.status_code == 202, r.text
    v = r.json()["validation"]
    assert v == {"rows_received": 17, "inserted": 12, "already_in_database": 3, "quarantined": 2, "flagged": 0}
    batch_id = r.json()["batch"]["id"]
    # TestClient runs the background recompute before returning control
    status = client.get(f"/api/data/imports/{batch_id}").json()
    assert status["status"] == "completed", status
    after = client.get("/api/health").json()
    assert after["scada_records"] == before + 12 and after["data_end"] == "2026-05-15"
    # uploading the same file again inserts nothing
    again = client.post("/api/data/upload", files={"file": ("batch.csv", _csv_bytes(payload), "text/csv")}).json()
    assert again["validation"]["inserted"] == 0 and again["recompute"] == "not needed"


def test_upload_rejects_bad_files(client):
    df = make_scada(3).drop(columns=["active_power_kw"])
    r = client.post("/api/data/upload", files={"file": ("x.csv", _csv_bytes(df), "text/csv")})
    assert r.status_code == 422 and "active_power_kw" in r.json()["detail"]["missing_columns"]
    assert client.post("/api/data/upload", files={"file": ("x.txt", b"a,b", "text/plain")}).status_code == 415
    assert client.post("/api/data/upload", files={"file": ("x.csv", b"", "text/csv")}).status_code == 400
