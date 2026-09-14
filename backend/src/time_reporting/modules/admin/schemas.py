"""HTTP request/response models of the admin API."""

from pydantic import BaseModel, ConfigDict

from time_reporting.modules.admin.contracts import (
    RemovalBlockerKind,
    RemovalEffectKind,
    RemovalOutcome,
)


class RemovalCountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: RemovalBlockerKind | RemovalEffectKind
    count: int


class RemovalImpactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_active: bool
    can_delete_permanently: bool
    blockers: list[RemovalCountResponse]
    effects: list[RemovalCountResponse]


class RemovalResponse(BaseModel):
    outcome: RemovalOutcome
