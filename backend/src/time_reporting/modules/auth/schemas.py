"""HTTP request/response models of the auth API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from time_reporting.core.passwords import PASSWORD_MAX_LENGTH


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Not validated as an email: any malformed value must fail exactly like wrong credentials.
    email: Annotated[str, Field(max_length=320)]
    password: Annotated[str, Field(max_length=PASSWORD_MAX_LENGTH)]


class SessionResponse(BaseModel):
    expires_in: int = Field(description="Session lifetime in seconds")
