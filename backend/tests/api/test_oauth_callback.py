from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.oauth_pkce import start_login


def test_callback_invalid_state(client: TestClient) -> None:
    """Test that callback rejects invalid state."""
    response = client.get("/api/auth/callback?code=fake_code&state=invalid_state")
    assert response.status_code == 401


def test_callback_missing_code(client: TestClient, db: Session) -> None:
    """Test that callback rejects missing code."""
    state, _ = start_login(db)
    response = client.get(f"/api/auth/callback?state={state}")
    assert response.status_code == 422


def test_callback_missing_state(client: TestClient) -> None:
    """Test that callback rejects missing state."""
    response = client.get("/api/auth/callback?code=fake_code")
    assert response.status_code == 422
