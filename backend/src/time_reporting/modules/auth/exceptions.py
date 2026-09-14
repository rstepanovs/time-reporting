class InvalidCredentialsError(Exception):
    """Unknown email, wrong password or inactive account — deliberately indistinguishable."""


class InvalidTokenError(Exception):
    """The access token is malformed, expired, badly signed or lacks required claims."""
