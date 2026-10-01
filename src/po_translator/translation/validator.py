"""Deterministic validators for verifying translation correctness and structural integrity."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from po_translator.po.placeholder import validate_placeholders


class ValidationSeverity(str, Enum):
    """Severity of a validation issue."""
    ERROR = "error"      # Blocks acceptance, requires retry or repair
    WARNING = "warning"  # Non-blocking advisory or flag for manual review


@dataclass
class ValidationIssue:
    """Detailed record of a validation finding."""
    severity: ValidationSeverity
    category: str        # e.g., "placeholder", "empty", "length", "glossary"
    message: str
    details: str | None = None


@dataclass
class ValidationResult:
    """Consolidated outcome of one or multiple validators."""
    is_valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        if issue.severity == ValidationSeverity.ERROR:
            self.errors.append(issue)
            self.is_valid = False
        else:
            self.warnings.append(issue)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class ValidationContext:
    """Contextual metadata passed to validators during evaluation."""
    entry_id: str | None = None
    msgctxt: str | None = None
    custom_patterns: list[str] | None = None
    glossary_terms: list[tuple[str, str]] | None = None


class Validator(Protocol):
    """Protocol implemented by deterministic validators."""

    def validate(
        self,
        source: str,
        translation: str,
        context: ValidationContext | None = None,
    ) -> ValidationResult:
        """Validate candidate translation against source text."""
        ...


class PlaceholderValidator:
    """Enforces strict equivalence and count preservation for all placeholders and variables."""

    def validate(
        self,
        source: str,
        translation: str,
        context: ValidationContext | None = None,
    ) -> ValidationResult:
        custom_patterns = context.custom_patterns if context else None
        ph_res = validate_placeholders(source, translation, custom_patterns=custom_patterns)

        errors: list[ValidationIssue] = []
        for issue in ph_res.issues:
            errors.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="placeholder",
                    message=issue.message,
                    details=issue.placeholder,
                )
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )


class EmptyTranslationValidator:
    """Ensures non-empty source text receives non-empty translation."""

    def validate(
        self,
        source: str,
        translation: str,
        context: ValidationContext | None = None,
    ) -> ValidationResult:
        res = ValidationResult(is_valid=True)
        if source.strip() and not translation.strip():
            res.add_issue(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="empty",
                    message="Translation cannot be empty when source contains text.",
                )
            )
        return res


class LengthRatioValidator:
    """Issues warnings if translation length is anomalously different from source."""

    def __init__(self, max_ratio: float = 4.0, min_chars: int = 15) -> None:
        self.max_ratio = max_ratio
        self.min_chars = min_chars

    def validate(
        self,
        source: str,
        translation: str,
        context: ValidationContext | None = None,
    ) -> ValidationResult:
        res = ValidationResult(is_valid=True)
        src_len = len(source.strip())
        trans_len = len(translation.strip())

        if src_len >= self.min_chars and trans_len > src_len * self.max_ratio:
            res.add_issue(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="length",
                    message=f"Translation is unusually long ({trans_len} chars vs {src_len} source chars).",
                )
            )
        return res


class CompositeValidator:
    """Executes a pipeline of validators and aggregates their results."""

    def __init__(self, validators: list[Validator] | None = None) -> None:
        self.validators = validators or [
            EmptyTranslationValidator(),
            PlaceholderValidator(),
            LengthRatioValidator(),
        ]

    def validate(
        self,
        source: str,
        translation: str,
        context: ValidationContext | None = None,
    ) -> ValidationResult:
        combined = ValidationResult(is_valid=True)
        for val in self.validators:
            res = val.validate(source, translation, context)
            if not res.is_valid:
                combined.is_valid = False
            combined.errors.extend(res.errors)
            combined.warnings.extend(res.warnings)
        return combined
