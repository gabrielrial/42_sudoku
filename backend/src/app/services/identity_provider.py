from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx


@dataclass
class Identity:
    """Identity extracted from user provider"""

    intra_id: int
    login: str
    campus_id: int
    campus_name: str


class IdentityProvider(Protocol):
    """Protocole made for macking IdentityFake and IdentityReal easier to test"""

    def authorize_url(self, state: str) -> str:
        """Returns the URL we go for the first OAuth step"""
        ...

    def identity_from_code(self, code: str) -> Identity:
        """Exchange the authorization code for the user identity"""
        ...


class FakeIdentityProvider:
    """Fake provider for development and tets"""

    def authorize_url(self, state: str) -> str:
        return f"http://localhost:8001/api/auth/callback?code=fake_code&state={state}"

    def identity_from_code(self, code: str) -> Identity:
        return Identity(
            intra_id=42,
            login="akaufmann",
            campus_id=1,
            campus_name="Berlin",
        )


class RealIdentityProvider:
    """Real user providor"""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.authorize_url_base = "https://api.intra.42.fr/oauth/authorize"
        self.token_url = "https://api.intra.42.fr/oauth/token"
        self.user_url = "https://api.intra.42.fr/v2/me"

    def authorize_url(self, state: str) -> str:
        return (
            f"{self.authorize_url_base}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"state={state}&"
            f"response_type=code&"
            f"scope=public"
        )

    def identity_from_code(self, code: str) -> Identity:
        token_response = httpx.post(
            self.token_url,
            json={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        user_response = httpx.get(self.user_url, headers={"Authorization": f"Bearer {token}"})
        user_response.raise_for_status()
        user_data = user_response.json()

        campus = next((c for c in user_data.get("campus_users", []) if c.get("is_primary")), None)

        if not campus:
            raise ValueError("User has no primary campus")

        campus_info = next(
            (c for c in user_data.get("campus", []) if c.get("id") == campus.get("campus_id")), None
        )

        if not campus_info:
            raise ValueError("Primary campus not found in user data")

        return Identity(
            intra_id=user_data["id"],
            login=user_data["login"],
            campus_id=campus_info["comapus"],
            campus_name=campus_info["name"],
        )
