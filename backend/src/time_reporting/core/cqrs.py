"""In-process CQRS bus — the only channel through which feature modules talk to each other.

Messages subclass ``Command[R]`` (changes state) or ``Query[R]`` (read-only), where ``R`` is the
handler's result type, so ``await bus.query(GetUserById(...))`` is typed by the message alone.
Handlers are registered once at startup in a ``HandlerRegistry``; a ``Bus`` is created per unit of
work (an HTTP request, a CLI invocation) and shares one ``AsyncSession`` with every handler it
dispatches to.

Transaction rule: the outermost ``Bus.execute`` commits on success and rolls back on error; nested
commands and all queries never commit, so handlers and services only flush. Query handlers must
not execute commands.
"""

from collections.abc import Callable
from typing import Any, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession


class Command[R]:
    """Base class for messages that change state and produce a result of type ``R``."""

    __slots__ = ()


class Query[R]:
    """Base class for read-only messages that produce a result of type ``R``."""

    __slots__ = ()


class Handler[M, R](Protocol):
    """Handles one message type; a new instance is created for every dispatch."""

    async def handle(self, message: M, /) -> R: ...


type HandlerFactory[M] = Callable[[Bus], Handler[M, Any]]


class HandlerNotFoundError(LookupError):
    def __init__(self, message_type: type) -> None:
        super().__init__(f"No handler registered for {message_type.__qualname__}")


class DuplicateHandlerError(ValueError):
    def __init__(self, message_type: type) -> None:
        super().__init__(f"A handler for {message_type.__qualname__} is already registered")


class RegistryFrozenError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Handlers cannot be registered after the registry is frozen")


class CommandInQueryError(RuntimeError):
    def __init__(self, command_type: type) -> None:
        super().__init__(
            f"Query handlers must not execute commands (attempted {command_type.__qualname__})"
        )


class HandlerRegistry:
    """Maps message types to handler factories; populated at startup, then frozen."""

    def __init__(self) -> None:
        self._factories: dict[type, HandlerFactory[Any]] = {}
        self._frozen = False

    def command[C: Command[Any]](self, message_type: type[C], factory: HandlerFactory[C]) -> None:
        self._register(message_type, factory)

    def query[Q: Query[Any]](self, message_type: type[Q], factory: HandlerFactory[Q]) -> None:
        self._register(message_type, factory)

    def freeze(self) -> None:
        self._frozen = True

    def resolve(self, message_type: type) -> HandlerFactory[Any]:
        try:
            return self._factories[message_type]
        except KeyError:
            raise HandlerNotFoundError(message_type) from None

    def _register(self, message_type: type, factory: HandlerFactory[Any]) -> None:
        if self._frozen:
            raise RegistryFrozenError()
        if message_type in self._factories:
            raise DuplicateHandlerError(message_type)
        self._factories[message_type] = factory


class Bus:
    """Dispatches messages to their handlers within one unit of work (one session)."""

    def __init__(self, registry: HandlerRegistry, session: AsyncSession) -> None:
        self.session = session
        self._registry = registry
        self._command_depth = 0
        self._query_depth = 0

    async def execute[R](self, command: Command[R]) -> R:
        if not isinstance(command, Command):
            raise TypeError(f"{type(command).__qualname__} is not a Command")
        if self._query_depth:
            raise CommandInQueryError(type(command))
        handler = self._registry.resolve(type(command))(self)
        outermost = self._command_depth == 0
        self._command_depth += 1
        try:
            result = await handler.handle(command)
            if outermost:
                await self.session.commit()
        except Exception:
            if outermost:
                await self.session.rollback()
            raise
        finally:
            self._command_depth -= 1
        return cast(R, result)

    async def query[R](self, query: Query[R]) -> R:
        if not isinstance(query, Query):
            raise TypeError(f"{type(query).__qualname__} is not a Query")
        handler = self._registry.resolve(type(query))(self)
        self._query_depth += 1
        try:
            result = await handler.handle(query)
        finally:
            self._query_depth -= 1
        return cast(R, result)
