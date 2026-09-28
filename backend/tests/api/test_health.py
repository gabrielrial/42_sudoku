from datetime import date

from app.clock import today


def test_health_is_ok_without_a_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_the_berlin_date(client):
    assert client.get("/api/health").json()["date"] == today().isoformat()
    assert date.fromisoformat(client.get("/api/health").json()["date"])


def test_unknown_route_is_a_404(client):
    assert client.get("/api/nope").status_code == 404
