"""Domain exceptions for contract validation."""

from __future__ import annotations


class ContractValidationError(Exception):
    """Raised when cross-object validation detects a contract error."""


__all__ = ["ContractValidationError"]
