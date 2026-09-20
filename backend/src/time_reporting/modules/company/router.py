"""Company HTTP API: read by admin or accountant, written by admin only."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep, require_roles
from time_reporting.modules.company.contracts import (
    ALLOWED_LOGO_CONTENT_TYPES,
    ClearCompanyLogo,
    CompanyLogoTooLargeError,
    CompanyLogoTypeNotAllowedError,
    GetCompanyLogo,
    GetCompanySettings,
    SetCompanyLogo,
    UpdateCompanySettings,
)
from time_reporting.modules.company.schemas import (
    CompanySettingsResponse,
    CompanySettingsUpdateRequest,
)
from time_reporting.modules.users.contracts import UserDTO, UserRole

router = APIRouter(prefix="/company", tags=["company"])

ReaderDep = Annotated[UserDTO, Depends(require_roles(UserRole.ADMIN, UserRole.ACCOUNTANT))]


@router.get("")
async def get_company_settings(_reader: ReaderDep, bus: BusDep) -> CompanySettingsResponse:
    settings = await bus.query(GetCompanySettings())
    return CompanySettingsResponse.model_validate(settings)


@router.put("")
async def update_company_settings(
    body: CompanySettingsUpdateRequest, current_user: AdminDep, bus: BusDep
) -> CompanySettingsResponse:
    settings = await bus.execute(
        UpdateCompanySettings(
            actor_id=current_user.id,
            legal_name=body.legal_name,
            org_number=body.org_number,
            vat_number=body.vat_number,
            address=body.address.to_dto(),
            email=body.email,
            phone=body.phone,
            registered_office=body.registered_office,
            bankgiro=body.bankgiro,
            iban=body.iban,
            bic=body.bic,
            f_tax_approved=body.f_tax_approved,
            default_invoice_locale=body.default_invoice_locale,
            late_interest=body.late_interest,
            invoice_number_prefix=body.invoice_number_prefix,
            next_invoice_number=body.next_invoice_number,
            allow_self_review=body.allow_self_review,
        )
    )
    return CompanySettingsResponse.model_validate(settings)


@router.get("/logo")
async def get_company_logo(_reader: ReaderDep, bus: BusDep) -> Response:
    logo = await bus.query(GetCompanyLogo())
    if logo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo is set")
    return Response(content=logo.content, media_type=logo.content_type)


@router.put(
    "/logo",
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The logo is too large"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "The logo type isn't allowed"},
    },
)
async def set_company_logo(
    current_user: AdminDep, bus: BusDep, file: Annotated[UploadFile, File()]
) -> CompanySettingsResponse:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_LOGO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Logo type {content_type!r} is not allowed",
        )
    content = await file.read()
    try:
        settings = await bus.execute(
            SetCompanyLogo(actor_id=current_user.id, content_type=content_type, content=content)
        )
    except CompanyLogoTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except CompanyLogoTypeNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    return CompanySettingsResponse.model_validate(settings)


@router.delete("/logo")
async def clear_company_logo(current_user: AdminDep, bus: BusDep) -> CompanySettingsResponse:
    settings = await bus.execute(ClearCompanyLogo(actor_id=current_user.id))
    return CompanySettingsResponse.model_validate(settings)
