"""
app/collectors/raw_document.py — Backward-compatibility re-export shim.

The canonical definition of ``RawDocument`` has moved to
``app.models.raw_document`` so it can be shared across the collection
layer and the normalization pipeline without either layer depending on
the other.

All existing imports of the form::

    from app.collectors.raw_document import RawDocument

continue to work unchanged.  New code should prefer::

    from app.models.raw_document import RawDocument
    # or
    from app.models import RawDocument
"""

from app.models.raw_document import RawDocument  # noqa: F401 — re-exported

__all__ = ["RawDocument"]
