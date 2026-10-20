import pytest

from app.models import UserRole

PASSWORD = "password123"


def _user(email: str, role: str) -> dict:
    return {
        "email": email,
        "password": PASSWORD,
        "full_name": "New User",
        "role": role,
    }


def test_create_user_requires_a_token(client):
    response = client.post("/users", json=_user("new@example.com", "manager"))

    assert response.status_code == 401


def test_create_user_rejects_a_bad_token(client):
    response = client.post(
        "/users",
        json=_user("new@example.com", "manager"),
        headers={"Authorization": "Bearer not-a-token"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("role", [UserRole.salesman, UserRole.manager])
def test_non_admin_cannot_create_a_user(client, add_user, login, role):
    actor_email = f"{role.value}@example.com"
    add_user(email=actor_email, role=role, full_name=role.value.title())
    token = login(actor_email)

    response = client.post(
        "/users",
        json=_user("new@example.com", "admin"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only an admin can create users"
    leftover = client.post(
        "/auth/login",
        json={"email": "new@example.com", "password": PASSWORD},
    )
    assert leftover.status_code == 401


@pytest.mark.parametrize("role", ["admin", "manager", "salesman"])
def test_admin_can_create_each_role(client, add_user, login, role):
    add_user(email="admin@example.com", role=UserRole.admin, full_name="Ada Admin")
    token = login("admin@example.com")

    response = client.post(
        "/users",
        json=_user(f"new-{role}@example.com", role),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == role
    assert body["email"] == f"new-{role}@example.com"
    assert "hashed_password" not in body


def test_admin_cannot_create_a_duplicate_email(client, add_user, login):
    add_user(email="admin@example.com", role=UserRole.admin, full_name="Ada Admin")
    add_user(email="ada@example.com", role=UserRole.salesman, full_name="Ada Yusuf")
    token = login("admin@example.com")

    response = client.post(
        "/users",
        json=_user("Ada@Example.com", "manager"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_admin_rejects_an_unknown_role(client, add_user, login):
    add_user(email="admin@example.com", role=UserRole.admin, full_name="Ada Admin")
    token = login("admin@example.com")

    response = client.post(
        "/users",
        json=_user("new@example.com", "driver"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
