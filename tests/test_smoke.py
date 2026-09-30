"""Smoke imports — no NAS/CIFS, no live/dev SQLite (see conftest)."""


def test_import_billing_engine():
    from nebenkostenfix import billing_engine

    assert hasattr(billing_engine, "BillingEngine")
    assert callable(billing_engine.BillingEngine.calculate_bill)


def test_import_app_health():
    import app

    assert app.app is not None
    client = app.app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
