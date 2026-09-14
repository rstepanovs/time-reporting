"""Root API router; every route lives under ``/api/v1``."""

from fastapi import APIRouter

from time_reporting.api.routes import health
from time_reporting.modules.admin.router import router as admin_router
from time_reporting.modules.auth.router import router as auth_router
from time_reporting.modules.customers.router import router as customers_router
from time_reporting.modules.projects.router import router as projects_router
from time_reporting.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(customers_router)
api_router.include_router(projects_router)
api_router.include_router(admin_router)
