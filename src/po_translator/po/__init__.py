"""PO manipulation package."""

from po_translator.po.mapper import POMapper
from po_translator.po.placeholder import (
    Placeholder,
    PlaceholderIssue,
    PlaceholderType,
    PlaceholderValidationResult,
    extract_placeholders,
    validate_placeholders,
)
from po_translator.po.reader import POReader
from po_translator.po.writer import POWriter

__all__ = [
    "POMapper",
    "POReader",
    "POWriter",
    "Placeholder",
    "PlaceholderIssue",
    "PlaceholderType",
    "PlaceholderValidationResult",
    "extract_placeholders",
    "validate_placeholders",
]
