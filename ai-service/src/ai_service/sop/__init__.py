"""SOP (Standard Operating Procedure) module for Sentinel.

This module provides:
- SOPLoader: Load full policy files from data/sops/
- SOPValidator: Validate and parse SOPs into structured rules
- SOPRule: Dataclass representing a parsed rule

Key Principles:
- Compliance = Full Context, not fuzzy search
- Vector store is for "Past Precedent" only, not active rules
- SOPs must be machine-readable (Rule-Condition-Action structure)
"""

from .loader import SOPLoader, get_sop_loader
from .validator import SOPRule, SOPValidationError, validate_sop

__all__ = [
    "SOPLoader",
    "SOPRule",
    "SOPValidationError",
    "get_sop_loader",
    "validate_sop",
]
