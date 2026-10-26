"""Research-only ambiguous-write obligation shield; not a package release."""

from .certificates import check_certificate, describe_request, recompute_decision

__all__ = ["NativeObligationPolicy", "ObligationShield", "make_policy",
           "check_certificate", "describe_request", "recompute_decision"]


def __getattr__(name):
    if name in ("NativeObligationPolicy", "ObligationShield", "make_policy"):
        from . import policy
        return getattr(policy, name)
    raise AttributeError(name)
