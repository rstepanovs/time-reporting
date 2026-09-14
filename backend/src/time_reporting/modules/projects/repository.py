"""Persistence of ``Project`` and ``ProjectMember`` entities.

Flushes but never commits — the bus owns transactions.
"""

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.db.queries import escape_like
from time_reporting.modules.projects.contracts import (
    ProjectInUseError,
    ProjectMemberAlreadyExistsError,
    ProjectNameAlreadyExistsError,
)
from time_reporting.modules.projects.models import Project, ProjectMember

_NAME_UNIQUE_CONSTRAINT = "uq_projects_customer_id_name"
_MEMBER_PRIMARY_KEY = "pk_project_members"


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def get_by_customer_and_name(self, customer_id: UUID, name: str) -> Project | None:
        result = await self._session.scalars(
            select(Project).where(Project.customer_id == customer_id, Project.name == name)
        )
        return result.one_or_none()

    async def get_page(
        self,
        *,
        limit: int,
        offset: int,
        include_inactive: bool,
        customer_id: UUID | None,
        member_id: UUID | None,
        search: str | None,
    ) -> Sequence[Project]:
        statement = (
            self._filtered(
                select(Project),
                include_inactive=include_inactive,
                customer_id=customer_id,
                member_id=member_id,
                search=search,
            )
            .order_by(Project.name, Project.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(
        self,
        *,
        include_inactive: bool,
        customer_id: UUID | None,
        member_id: UUID | None,
        search: str | None,
    ) -> int:
        statement = self._filtered(
            select(func.count()).select_from(Project),
            include_inactive=include_inactive,
            customer_id=customer_id,
            member_id=member_id,
            search=search,
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self,
        statement: Select[T],
        *,
        include_inactive: bool,
        customer_id: UUID | None,
        member_id: UUID | None,
        search: str | None,
    ) -> Select[T]:
        if not include_inactive:
            statement = statement.where(Project.is_active.is_(True))
        if customer_id is not None:
            statement = statement.where(Project.customer_id == customer_id)
        if member_id is not None:
            statement = statement.where(
                Project.id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == member_id)
                )
            )
        if search:
            pattern = f"%{escape_like(search)}%"
            statement = statement.where(Project.name.ilike(pattern, escape="\\"))
        return statement

    async def save(self, project: Project) -> None:
        """Add ``project`` to the session (if new) and flush pending changes."""
        self._session.add(project)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent request may have taken the name after the service's pre-check.
            if _NAME_UNIQUE_CONSTRAINT in str(exc.orig):
                raise ProjectNameAlreadyExistsError(project.customer_id, project.name) from exc
            raise

    async def delete(self, project: Project) -> None:
        """Delete ``project``. Members cascade-delete; other data may still block this with a
        foreign-key violation, raised as ``ProjectInUseError``."""
        project_id = project.id  # read before flush: a failed flush may expire ORM attributes
        await self._session.delete(project)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "foreign key constraint" in str(exc.orig):
                raise ProjectInUseError(project_id) from exc
            raise


class ProjectMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: UUID, user_id: UUID) -> ProjectMember | None:
        return await self._session.get(ProjectMember, (project_id, user_id))

    async def list_for_project(self, project_id: UUID) -> Sequence[ProjectMember]:
        result = await self._session.scalars(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return result.all()

    async def save(self, member: ProjectMember) -> None:
        """Add ``member`` to the session and flush."""
        self._session.add(member)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _MEMBER_PRIMARY_KEY in str(exc.orig):
                raise ProjectMemberAlreadyExistsError(member.project_id, member.user_id) from exc
            raise

    async def delete(self, member: ProjectMember) -> None:
        await self._session.delete(member)
        await self._session.flush()

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete every membership of ``user_id`` and return how many rows were removed."""
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(ProjectMember).where(ProjectMember.user_id == user_id)
            ),
        )
        await self._session.flush()
        return result.rowcount
