"""Feature modules.

Modules talk to each other only through the CQRS bus (``core.cqrs``) and the messages/DTOs
published in each module's ``contracts.py``. ``registry.build_registry()`` is the composition root.
"""
