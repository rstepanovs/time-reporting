"""Authentication use cases. User data is reached only through the bus and users contracts."""

from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import verify_dummy, verify_password
from time_reporting.modules.auth.exceptions import InvalidCredentialsError
from time_reporting.modules.auth.jwt import AccessToken, create_access_token
from time_reporting.modules.users.contracts import GetUserCredentialsByEmail, RecordSuccessfulLogin


class AuthService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def login(self, email: str, password: str) -> AccessToken:
        credentials = await self._bus.query(GetUserCredentialsByEmail(email=email))
        if credentials is None:
            await verify_dummy(password)
            raise InvalidCredentialsError()

        is_valid, rehashed = await verify_password(password, credentials.password_hash)
        if not is_valid or not credentials.is_active:
            raise InvalidCredentialsError()

        await self._bus.execute(
            RecordSuccessfulLogin(user_id=credentials.id, rehashed_password_hash=rehashed)
        )
        return create_access_token(credentials.id, token_version=credentials.token_version)
