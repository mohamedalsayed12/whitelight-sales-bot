from datetime import datetime

SALESMAN = {
    "email": "ada@example.com",
    "password": "password123",
    "full_name": "Ada Yusuf",
}


def test_register_creates_a_salesman(client):
    response = client.post("/auth/register", json=SALESMAN)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Yusuf"
    assert body["role"] == "salesman"
    assert "password" not in body
    assert "hashed_password" not in body
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.tzinfo is not None


def test_register_rejects_a_role_field(client):
    response = client.post("/auth/register", json={**SALESMAN, "role": "admin"})

    assert response.status_code == 422


def test_register_rejects_a_short_password(client):
    response = client.post(
        "/auth/register",
        json={**SALESMAN, "password": "short"},
    )

    assert response.status_code == 422


def test_register_rejects_a_password_over_72_bytes(client):
    # "é" is 2 bytes, so this is 80 bytes but only 40 characters.
    response = client.post(
        "/auth/register",
        json={**SALESMAN, "password": "é" * 40},
    )

    assert response.status_code == 422


def test_register_rejects_a_blank_name(client):
    response = client.post(
        "/auth/register",
        json={**SALESMAN, "full_name": "   "},
    )

    assert response.status_code == 422


def test_register_rejects_missing_password(client):
    response = client.post(
        "/auth/register",
        json={"email": SALESMAN["email"], "full_name": SALESMAN["full_name"]},
    )

    assert response.status_code == 422


def test_register_rejects_an_invalid_email(client):
    response = client.post(
        "/auth/register",
        json={**SALESMAN, "email": "not-an-email"},
    )

    assert response.status_code == 422


def test_register_rejects_a_duplicate_email(client):
    first = client.post("/auth/register", json=SALESMAN)
    second = client.post("/auth/register", json=SALESMAN)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "Email already registered"


def test_register_treats_email_case_as_the_same_user(client):
    first = client.post(
        "/auth/register",
        json={**SALESMAN, "email": "Ada@Example.com"},
    )
    second = client.post("/auth/register", json=SALESMAN)
    login = client.post(
        "/auth/login",
        json={"email": "ADA@example.com", "password": SALESMAN["password"]},
    )

    assert first.status_code == 201
    assert first.json()["email"] == "ada@example.com"
    assert second.status_code == 409
    assert login.status_code == 200


def test_login_returns_a_token(client):
    client.post("/auth/register", json=SALESMAN)

    response = client.post(
        "/auth/login",
        json={"email": SALESMAN["email"], "password": SALESMAN["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_failure_does_not_reveal_whether_the_email_exists(client):
    client.post("/auth/register", json=SALESMAN)
    wrong_password = client.post(
        "/auth/login",
        json={"email": SALESMAN["email"], "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == "Incorrect email or password"


def test_login_rejects_an_invalid_email(client):
    response = client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "password123"},
    )

    assert response.status_code == 422


def test_me_requires_a_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_rejects_a_bad_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401


def test_me_returns_the_token_owner(client):
    client.post("/auth/register", json=SALESMAN)
    client.post(
        "/auth/register",
        json={
            "email": "ben@example.com",
            "password": "password123",
            "full_name": "Ben Ali",
        },
    )
    ada_login = client.post(
        "/auth/login",
        json={"email": SALESMAN["email"], "password": SALESMAN["password"]},
    )
    ben_login = client.post(
        "/auth/login",
        json={"email": "ben@example.com", "password": "password123"},
    )

    ada = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {ada_login.json()['access_token']}"},
    )
    ben = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {ben_login.json()['access_token']}"},
    )

    assert ada.status_code == 200
    assert ada.json()["email"] == "ada@example.com"
    assert ada.json()["role"] == "salesman"
    assert ben.status_code == 200
    assert ben.json()["email"] == "ben@example.com"
