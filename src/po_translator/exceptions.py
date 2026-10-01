"""Core exceptions for PO LLM Translator."""

class POTranslatorError(Exception):
    """Base exception for all PO Translator errors."""

class POParseError(POTranslatorError):
    """Raised when parsing a PO/POT file fails."""

class POWriteError(POTranslatorError):
    """Raised when writing to a PO/POT file fails."""

class ValidationError(POTranslatorError):
    """Raised when validation fails."""

class LLMError(POTranslatorError):
    """Base exception for LLM-related failures."""

class LLMNetworkError(LLMError):
    """Network-related issues (timeout, connection reset, 5xx)."""

class LLMAuthenticationError(LLMError):
    """Authentication or authorization failure (401, 403)."""

class LLMRateLimitError(LLMError):
    """Rate limit exceeded (HTTP 429)."""

class LLMResponseError(LLMError):
    """Invalid LLM response content or schema violation."""

class StorageError(POTranslatorError):
    """Raised when database or file storage operations fail."""
