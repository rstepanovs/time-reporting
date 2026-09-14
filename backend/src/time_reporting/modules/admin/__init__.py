"""Admin module: archive-or-delete orchestration for other modules' entities.

Owns no tables of its own; it only computes removal impact and runs an archive or a permanent
delete atomically, through ``users.contracts`` / ``customers.contracts`` / ``projects.contracts``.
"""
