"""
Google sign-in.

Nothing here contacts Google; the token exchange is substituted. What is being
protected is the two things that are expensive to get wrong: matching accounts
on the provider's subject id rather than on an email address, and refusing a
callback whose state does not match.
"""

import pytest

import config
from models import User
from routers import oauth

PASSWORD = "correct-horse-battery"


@pytest.fixture
def google_enabled(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "GOOGLE_ENABLED", True)


@pytest.fixture
def fake_google(monkeypatch):
    """Substitute the whole token exchange with a canned profile."""

    def install(*, sub="google-sub-1", email="asha@example.com", name="Asha Menon", raises=None):
        async def _exchange(code):
            if raises:
                raise raises
            return {"sub": sub, "email": email, "name": name}

        monkeypatch.setattr(oauth, "_exchange", _exchange)

    return install


class TestStatus:
    def test_disabled_by_default(self, client):
        # Credentials need a Google Cloud project, which only the deployer can
        # create, so the app has to work without them.
        assert client.get("/api/auth/google/status").json()["enabled"] is False

    def test_enabled_when_configured(self, client, google_enabled):
        assert client.get("/api/auth/google/status").json()["enabled"] is True

    def test_starting_without_credentials_is_refused_clearly(self, client):
        response = client.get("/api/auth/google/start", follow_redirects=False)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "google_not_configured"


class TestStart:
    def test_it_redirects_to_google_and_sets_a_state_cookie(self, client, google_enabled):
        response = client.get("/api/auth/google/start", follow_redirects=False)
        assert response.status_code == 307
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/")
        assert "client_id=test-client-id" in location
        assert "state=" in location
        assert oauth.STATE_COOKIE in response.cookies


class TestCallback:
    def _start(self, client):
        response = client.get("/api/auth/google/start", follow_redirects=False)
        location = response.headers["location"]
        return location.split("state=")[1].split("&")[0]

    def test_a_valid_callback_signs_you_in(self, client, google_enabled, fake_google):
        fake_google()
        state = self._start(client)

        response = client.get(
            f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )
        assert response.status_code == 307
        assert "signed_in=google" in response.headers["location"]
        assert client.get("/api/auth/me").json()["user"]["email"] == "asha@example.com"

    def test_a_mismatched_state_is_refused(self, client, google_enabled, fake_google):
        # Without this check the callback accepts a code from anywhere, which is
        # how CSRF signs you into someone else's account.
        fake_google()
        self._start(client)

        response = client.get(
            "/api/auth/google/callback?code=abc&state=not-the-state",
            follow_redirects=False,
        )
        assert "oauth_error=bad_state" in response.headers["location"]
        assert client.get("/api/auth/me").json()["user"] is None

    def test_a_missing_state_cookie_fails_closed(self, client, google_enabled, fake_google):
        fake_google()
        response = client.get(
            "/api/auth/google/callback?code=abc&state=anything", follow_redirects=False
        )
        assert "oauth_error=bad_state" in response.headers["location"]

    def test_a_cancelled_sign_in_is_not_an_error_page(self, client, google_enabled):
        state = self._start(client)
        response = client.get(
            f"/api/auth/google/callback?error=access_denied&state={state}",
            follow_redirects=False,
        )
        assert "oauth_error=cancelled" in response.headers["location"]

    def test_an_exchange_failure_redirects_rather_than_500s(
        self, client, google_enabled, fake_google
    ):
        fake_google(raises=ValueError("no token"))
        state = self._start(client)
        response = client.get(
            f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
        )
        # The user is mid-journey in a browser; a JSON error body is not a
        # useful thing to land on.
        assert "oauth_error=exchange_failed" in response.headers["location"]


class TestAccountMatching:
    def _sign_in(self, client, state=None, code="abc"):
        response = client.get("/api/auth/google/start", follow_redirects=False)
        state = state or response.headers["location"].split("state=")[1].split("&")[0]
        return client.get(
            f"/api/auth/google/callback?code={code}&state={state}", follow_redirects=False
        )

    def test_signing_in_twice_reuses_one_account(self, client, google_enabled, fake_google):
        fake_google()
        self._sign_in(client)
        first = client.get("/api/auth/me").json()["user"]["id"]

        client.post("/api/auth/logout")
        self._sign_in(client)
        assert client.get("/api/auth/me").json()["user"]["id"] == first

    def test_a_changed_google_address_keeps_the_account(
        self, client, google_enabled, fake_google
    ):
        """
        Matched on the provider's subject id, not the address.

        Matching on email would split one person into two accounts when they
        change it - or hand their account to whoever later acquires it.
        """
        fake_google(sub="stable-sub", email="old@example.com")
        self._sign_in(client)
        original = client.get("/api/auth/me").json()["user"]["id"]

        client.post("/api/auth/logout")
        fake_google(sub="stable-sub", email="new@example.com")
        self._sign_in(client)

        user = client.get("/api/auth/me").json()["user"]
        assert user["id"] == original
        assert user["email"] == "new@example.com"

    def test_an_existing_password_account_is_linked_not_duplicated(
        self, client, google_enabled, fake_google
    ):
        client.post(
            "/api/auth/register", json={"email": "asha@example.com", "password": PASSWORD}
        )
        existing = client.get("/api/auth/me").json()["user"]["id"]
        client.post("/api/auth/logout")

        fake_google(email="asha@example.com")
        self._sign_in(client)

        user = client.get("/api/auth/me").json()["user"]
        assert user["id"] == existing
        # Linking must not remove the password they already had.
        assert user["has_password"] is True

    def test_a_google_only_account_has_no_password(self, client, google_enabled, fake_google):
        fake_google()
        self._sign_in(client)
        user = client.get("/api/auth/me").json()["user"]
        assert user["has_password"] is False
        assert user["oauth_provider"] == "google"

    def test_a_google_only_account_cannot_be_signed_into_with_a_password(
        self, client, google_enabled, fake_google
    ):
        fake_google()
        self._sign_in(client)
        client.post("/api/auth/logout")

        response = client.post(
            "/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}
        )
        assert response.status_code == 400


class TestDeletionWithoutAPassword:
    def _google_user(self, client, fake_google):
        fake_google()
        response = client.get("/api/auth/google/start", follow_redirects=False)
        state = response.headers["location"].split("state=")[1].split("&")[0]
        client.get(f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False)

    def test_it_confirms_by_email_instead(self, client, google_enabled, fake_google):
        self._google_user(client, fake_google)
        response = client.post(
            "/api/account/delete", json={"confirm_email": "asha@example.com"}
        )
        assert response.status_code == 200
        assert client.get("/api/auth/me").json()["user"] is None

    def test_the_wrong_email_is_refused(self, client, google_enabled, fake_google):
        self._google_user(client, fake_google)
        response = client.post(
            "/api/account/delete", json={"confirm_email": "someone@else.com"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "confirm_email_mismatch"
        assert client.get("/api/auth/me").json()["user"] is not None

    def test_a_password_account_still_needs_its_password(self, client, register):
        register()
        assert (
            client.post(
                "/api/account/delete", json={"confirm_email": "asha@example.com"}
            ).status_code
            == 400
        )
