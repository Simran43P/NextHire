"""
Accounts: registration, sign-in, sign-out, reset, and the guest carryover.

The behaviours worth protecting are mostly about what the API refuses to tell
you - whether an email is registered, whether a password was merely wrong -
because those disclosures are how account lists get built.
"""

import config
from auth import hash_password, hash_token, password_problem, verify_password

PASSWORD = "correct-horse-battery"


class TestPasswordHashing:
    def test_a_hash_does_not_contain_the_password(self):
        digest = hash_password(PASSWORD)
        assert PASSWORD not in digest
        assert digest.startswith("$argon2")

    def test_verification_round_trips(self):
        assert verify_password(hash_password(PASSWORD), PASSWORD) is True

    def test_the_wrong_password_fails(self):
        assert verify_password(hash_password(PASSWORD), "something else") is False

    def test_the_same_password_hashes_differently_each_time(self):
        # Per-hash salting: two users with the same password must not share a hash.
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_a_corrupt_stored_hash_fails_closed(self):
        assert verify_password("not-a-hash", PASSWORD) is False

    def test_short_passwords_are_rejected(self):
        assert password_problem("short") is not None
        assert password_problem("x" * config.MIN_PASSWORD_LENGTH) is None


class TestTokenStorage:
    def test_tokens_are_stored_only_as_hashes(self):
        # A leaked database must not hand out live sessions.
        raw = "some-session-token"
        assert hash_token(raw) != raw
        assert len(hash_token(raw)) == 64


class TestRegistration:
    def test_registering_signs_you_in(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "asha@example.com", "password": PASSWORD}
        )
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "asha@example.com"
        assert config.SESSION_COOKIE_NAME in response.cookies

    def test_the_email_is_normalised(self, client):
        client.post(
            "/api/auth/register", json={"email": "  ASHA@Example.COM ", "password": PASSWORD}
        )
        assert client.get("/api/auth/me").json()["user"]["email"] == "asha@example.com"

    def test_a_duplicate_email_is_refused(self, client, register):
        register()
        response = client.post(
            "/api/auth/register", json={"email": "asha@example.com", "password": PASSWORD}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "email_taken"

    def test_a_weak_password_is_refused(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "asha@example.com", "password": "short"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "weak_password"

    def test_a_malformed_email_is_refused(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": PASSWORD}
        )
        assert response.status_code == 422


class TestGuestCarryover:
    def test_work_done_before_registering_is_kept(self, client, sample_profile):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "asha@example.com",
                "password": PASSWORD,
                "carryover": {
                    "profile": sample_profile,
                    "gaps": [],
                    "raw_text": "the original resume text",
                    "filename": "asha.pdf",
                },
            },
        )
        assert response.status_code == 201
        carried = response.json()["carried"]
        assert carried is not None

        stored = client.get(f"/api/profiles/{carried['profile_id']}").json()
        assert stored["profile"]["name"] == "Asha Menon"

    def test_registering_without_carryover_is_fine(self, client, register):
        assert register()["carried"] is None


class TestLogin:
    def test_signing_in_works(self, client, register):
        register()
        client.post("/api/auth/logout")
        response = client.post(
            "/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert client.get("/api/auth/me").json()["user"] is not None

    def test_an_unknown_email_and_a_wrong_password_are_indistinguishable(
        self, client, register
    ):
        register()
        unknown = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
        )
        wrong = client.post(
            "/api/auth/login", json={"email": "asha@example.com", "password": "wrong-password"}
        )
        # Telling these apart hands out a list of which emails have accounts.
        assert unknown.status_code == wrong.status_code == 400
        assert unknown.json() == wrong.json()

    def test_signing_out_ends_the_session(self, client, register):
        register()
        assert client.get("/api/auth/me").json()["user"] is not None
        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").json()["user"] is None


class TestMe:
    def test_a_guest_gets_a_null_user_not_an_error(self, client):
        response = client.get("/api/auth/me")
        # "Nobody is signed in" is an answer to this question, not a failure.
        assert response.status_code == 200
        assert response.json()["user"] is None

    def test_a_signed_in_user_sees_their_profile_count(self, client, register):
        register()
        assert client.get("/api/auth/me").json()["profile_count"] == 0


class TestPasswordReset:
    def _request_reset(self, client, monkeypatch, email="asha@example.com"):
        captured = {}

        async def _capture(to_address, token):
            captured["to"] = to_address
            captured["token"] = token
            return False

        monkeypatch.setattr("routers.auth.mailer.send_password_reset", _capture)
        response = client.post("/api/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        return captured

    def test_an_unknown_email_reports_success_anyway(self, client, monkeypatch):
        captured = self._request_reset(client, monkeypatch, "nobody@example.com")
        # No email was sent, but the response must not say so.
        assert captured == {}

    def test_a_reset_token_changes_the_password(self, client, register, monkeypatch):
        register()
        client.post("/api/auth/logout")

        token = self._request_reset(client, monkeypatch)["token"]
        response = client.post(
            "/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}
        )
        assert response.status_code == 200

        client.post("/api/auth/logout")
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "asha@example.com", "password": "a-brand-new-password"},
            ).status_code
            == 200
        )

    def test_a_token_works_only_once(self, client, register, monkeypatch):
        register()
        token = self._request_reset(client, monkeypatch)["token"]
        client.post("/api/auth/reset-password", json={"token": token, "password": "first-new-password"})
        second = client.post(
            "/api/auth/reset-password", json={"token": token, "password": "second-new-password"}
        )
        assert second.status_code == 400
        assert second.json()["detail"]["code"] == "invalid_reset_token"

    def test_an_unknown_token_is_refused(self, client, register):
        register()
        response = client.post(
            "/api/auth/reset-password", json={"token": "made-up", "password": "a-new-password"}
        )
        assert response.status_code == 400

    def test_resetting_revokes_existing_sessions(self, client, register, monkeypatch):
        """A reset often follows a suspected compromise; the intruder must be evicted."""
        register()
        token = self._request_reset(client, monkeypatch)["token"]

        # A second client holding the pre-reset cookie.
        stolen = dict(client.cookies)
        client.post("/api/auth/reset-password", json={"token": token, "password": "a-new-password"})

        client.cookies.clear()
        client.cookies.update(stolen)
        assert client.get("/api/auth/me").json()["user"] is None

    def test_a_weak_new_password_is_refused(self, client, register, monkeypatch):
        register()
        token = self._request_reset(client, monkeypatch)["token"]
        response = client.post(
            "/api/auth/reset-password", json={"token": token, "password": "short"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "weak_password"
