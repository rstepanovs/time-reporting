"""Shared query helpers used by more than one module's repository."""

_LIKE_SPECIAL_CHARS = ("\\", "%", "_")


def escape_like(term: str) -> str:
    """Escape ``\\``, ``%`` and ``_`` in ``term`` so it can be used as a literal ``ILIKE`` operand.

    Callers must pass ``escape="\\"`` to ``ilike()``/``like()`` alongside the escaped term.
    """
    for char in _LIKE_SPECIAL_CHARS:
        term = term.replace(char, f"\\{char}")
    return term
