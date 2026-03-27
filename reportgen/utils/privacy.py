"""
Privacy utilities (masking/sanitization).

This repo generates medical reports; even in local development we should reduce
the chance of leaking patient identifiers in artifacts or logs.
"""

from __future__ import annotations

from typing import Any, Mapping, Set


def mask_text(value: Any) -> str:
    """Mask a sensitive value to a stable but non-identifying string."""
    if value is None:
        return ""
    s = str(value)
    if s == "":
        return ""
    if len(s) <= 2:
        return "*" * len(s)
    if len(s) <= 6:
        return s[0] + ("*" * (len(s) - 2)) + s[-1]
    return s[:2] + ("*" * (len(s) - 4)) + s[-2:]


def mask_sensitive_data(obj: Any, *, sensitive_keys: Set[str]) -> Any:
    """Recursively mask values under keys in `sensitive_keys`.

    - Dict: masks values where key in sensitive_keys, otherwise recurse.
    - List/Tuple: recurse into items.
    - Other types: returned as-is.
    """
    if obj is None:
        return None

    if isinstance(obj, Mapping):
        out: dict = {}
        for k, v in obj.items():
            key = str(k)
            if key in sensitive_keys:
                out[key] = mask_text(v)
            else:
                out[key] = mask_sensitive_data(v, sensitive_keys=sensitive_keys)
        return out

    if isinstance(obj, (list, tuple)):
        return [mask_sensitive_data(v, sensitive_keys=sensitive_keys) for v in obj]

    return obj
