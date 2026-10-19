"""Typed exceptions raised by ConseqaX.

Every error the package raises on purpose derives from ``ConsequaError``. Each
class also derives from ``ValueError`` or ``TypeError``, so callers written for
the untyped 1.x errors keep working while new callers can be precise.
"""


class ConsequaError(Exception):
    """Base class for every error ConseqaX raises on purpose."""


class ConsequaTypeError(ConsequaError, TypeError):
    """An argument or record field has the wrong Python type."""


class ValidationError(ConsequaError, ValueError):
    """A record, a trace, a relationship between records or a setting is invalid."""


class SchemaVersionError(ValidationError):
    """A trace uses a schema version this package cannot read."""


class ContractError(ConsequaError, ValueError):
    """A verifier cannot evaluate this action's outcome contract."""


class ReceiptError(ConsequaError, ValueError):
    """A verifier or target matcher returned a result outside its identity boundary,
    or recorded evidence cannot support the interpretation asked of it."""


class RecorderError(ConsequaError, ValueError):
    """``TraceRecorder`` was used out of order or with conflicting identities."""
