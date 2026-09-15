from httpx import AsyncClient, Response

from support import ADMIN, DEFAULT_PASSWORD, AuthHeaders, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.users.contracts import UpdateUser


async def _login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/login", data={"username": email, "password": password})


async def test_login_returns_working_token(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(email="login@example.com")

    response = await _login(client, "LOGIN@example.com", DEFAULT_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)
    assert me.json()["last_login_at"] is not None


async def test_login_failures_are_indistinguishable(
    client: AsyncClient, bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    await make_user(email="active@example.com")
    inactive = await make_user(email="inactive@example.com")
    await bus.execute(UpdateUser(user_id=inactive.id, acting_user_id=admin.id, is_active=False))

    responses = [
        await _login(client, "active@example.com", "wrong-password"),
        await _login(client, "unknown@example.com", DEFAULT_PASSWORD),
        await _login(client, "inactive@example.com", DEFAULT_PASSWORD),
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1
    assert all(r.headers["WWW-Authenticate"] == "Bearer" for r in responses)


async def test_protected_route_requires_valid_token(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/users/me")
    garbage = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"})

    assert missing.status_code == 401
    assert garbage.status_code == 401


async def test_token_is_revoked_by_password_change(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    user = await make_user(email="rotate@example.com")
    headers = auth_headers(user)

    changed = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "rotated-password"},
    )

    assert changed.status_code == 204
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401
    assert (await _login(client, "rotate@example.com", "rotated-password")).status_code == 200


async def test_token_is_rejected_after_deactivation(
    client: AsyncClient, bus: Bus, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user()
    headers = auth_headers(user)

    await bus.execute(UpdateUser(user_id=user.id, acting_user_id=admin.id, is_active=False))

    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401
