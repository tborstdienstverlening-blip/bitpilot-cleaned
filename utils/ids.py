# utils/ids.py
from __future__ import annotations


def key(prefix: str) -> str:
    """
    Stabiele key-generator. Om geen gedrag te wijzigen t.o.v. 07d
    houden we de key gelijk aan de opgegeven prefix.
    """
    return prefix
