from dataclasses import dataclass
from typing import assert_type, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.core.cqrs import (
    Bus,
    Command,
    CommandInQueryError,
    DuplicateHandlerError,
    HandlerNotFoundError,
    HandlerRegistry,
    Query,
    RegistryFrozenError,
)


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass(frozen=True)
class Echo(Query[str]):
    text: str


@dataclass(frozen=True)
class ExecuteFromQuery(Query[None]):
    pass


@dataclass(frozen=True)
class Increment(Command[int]):
    value: int


@dataclass(frozen=True)
class IncrementTwice(Command[int]):
    value: int


@dataclass(frozen=True)
class Explode(Command[None]):
    pass


class EchoHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, query: Echo) -> str:
        return query.text


class ExecuteFromQueryHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, query: ExecuteFromQuery) -> None:
        await self._bus.execute(Increment(value=0))


class IncrementHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, command: Increment) -> int:
        return command.value + 1


class IncrementTwiceHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, command: IncrementTwice) -> int:
        once = await self._bus.execute(Increment(value=command.value))
        return await self._bus.execute(Increment(value=once))


class ExplodeHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, command: Explode) -> None:
        raise RuntimeError("boom")


def make_bus() -> tuple[Bus, FakeSession]:
    registry = HandlerRegistry()
    registry.query(Echo, EchoHandler)
    registry.query(ExecuteFromQuery, ExecuteFromQueryHandler)
    registry.command(Increment, IncrementHandler)
    registry.command(IncrementTwice, IncrementTwiceHandler)
    registry.command(Explode, ExplodeHandler)
    registry.freeze()
    session = FakeSession()
    return Bus(registry, cast(AsyncSession, session)), session


async def test_query_returns_typed_result_without_committing() -> None:
    bus, session = make_bus()

    result = await bus.query(Echo(text="hello"))

    assert_type(result, str)
    assert result == "hello"
    assert (session.commits, session.rollbacks) == (0, 0)


async def test_only_outermost_command_commits() -> None:
    bus, session = make_bus()

    result = await bus.execute(IncrementTwice(value=1))

    assert_type(result, int)
    assert result == 3
    assert (session.commits, session.rollbacks) == (1, 0)


async def test_failed_command_rolls_back_and_bus_stays_usable() -> None:
    bus, session = make_bus()

    with pytest.raises(RuntimeError, match="boom"):
        await bus.execute(Explode())
    assert (session.commits, session.rollbacks) == (0, 1)

    assert await bus.execute(Increment(value=1)) == 2
    assert (session.commits, session.rollbacks) == (1, 1)


async def test_query_handler_cannot_execute_commands() -> None:
    bus, session = make_bus()

    with pytest.raises(CommandInQueryError):
        await bus.query(ExecuteFromQuery())
    assert session.commits == 0

    # The query depth is restored after the failure.
    assert await bus.execute(Increment(value=1)) == 2


async def test_unregistered_message_raises() -> None:
    bus = Bus(HandlerRegistry(), cast(AsyncSession, FakeSession()))

    with pytest.raises(HandlerNotFoundError):
        await bus.query(Echo(text="hello"))


async def test_message_kind_is_checked() -> None:
    bus, _ = make_bus()

    with pytest.raises(TypeError):
        await bus.execute(cast(Command[str], Echo(text="hello")))
    with pytest.raises(TypeError):
        await bus.query(cast(Query[int], Increment(value=1)))


def test_duplicate_registration_is_rejected() -> None:
    registry = HandlerRegistry()
    registry.query(Echo, EchoHandler)

    with pytest.raises(DuplicateHandlerError):
        registry.query(Echo, EchoHandler)


def test_frozen_registry_rejects_registration() -> None:
    registry = HandlerRegistry()
    registry.freeze()

    with pytest.raises(RegistryFrozenError):
        registry.command(Increment, IncrementHandler)
