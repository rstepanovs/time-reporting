from http.cookies import Morsel, SimpleCookie

from httpx import AsyncClient, Response

from support import DEFAULT_PASSWORD, AuthHeaders, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.modules.auth.session_cookie import ACCESS_TOKEN_COOKIE, CSRF_HEADER

CSRF_HEADERS = {CSRF_HEADER: "fetch"}


async def _sign_in(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/session", json={"email": email, "password": password})


def _session_cookie(response: Response) -> Morsel[str]:
    return SimpleCookie(response.headers["set-cookie"])[ACCESS_TOKEN_COOKIE]


async def test_sign_in_sets_http_only_session_cookie(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user(email="session@example.com")

    response = await _sign_in(client, "SESSION@example.com", DEFAULT_PASSWORD)

    assert response.status_code == 200
    assert response.json() == {"expires_in": get_settings().access_token_expire_minutes * 60}
    cookie = _session_cookie(response)
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/api"
    assert cookie.value not in response.text

    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)


async def test_sign_in_failures_are_indistinguishable_and_set_no_cookie(
    client: AsyncClient, make_user: UserFactory
) -> None:
    await make_user(email="active@example.com")

    responses = [
        await _sign_in(client, "active@example.com", "wrong-password"),
        await _sign_in(client, "unknown@example.com", DEFAULT_PASSWORD),
        await _sign_in(client, "not an email", DEFAULT_PASSWORD),
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1
    assert all("set-cookie" not in r.headers for r in responses)


async def test_cookie_auth_requires_csrf_header_for_unsafe_methods(
    client: AsyncClient, make_user: UserFactory
) -> None:
    await make_user(email="csrf@example.com")
    await _sign_in(client, "csrf@example.com", DEFAULT_PASSWORD)
    body = {"current_password": DEFAULT_PASSWORD, "new_password": "rotated-password"}

    without_header = await client.post("/api/v1/users/me/password", json=body)
    with_header = await client.post("/api/v1/users/me/password", json=body, headers=CSRF_HEADERS)

    assert without_header.status_code == 403
    assert with_header.status_code == 204
    # The password change revokes the token held in the cookie.
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_bearer_header_takes_precedence_over_cookie(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    await make_user(email="cookie@example.com")
    other = await make_user(email="bearer@example.com")
    await _sign_in(client, "cookie@example.com", DEFAULT_PASSWORD)

    me = await client.get("/api/v1/users/me", headers=auth_headers(other))

    assert me.status_code == 200
    assert me.json()["id"] == str(other.id)


async def test_invalid_session_cookie_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Cookie": f"{ACCESS_TOKEN_COOKIE}=garbage"}
    )

    assert response.status_code == 401


async def test_sign_out_clears_session_cookie(client: AsyncClient, make_user: UserFactory) -> None:
    await make_user(email="logout@example.com")
    await _sign_in(client, "logout@example.com", DEFAULT_PASSWORD)

    response = await client.delete("/api/v1/auth/session")

    assert response.status_code == 204
    cookie = _session_cookie(response)
    assert cookie.value == ""
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/api"
    assert (await client.get("/api/v1/users/me")).status_code == 401
