"""
Secure Python Sandbox Execution System.

Defense-in-depth architecture for safe execution of AI-generated Python code:

    Layer 1 — Input Sanitisation  (sanitizer.py)
    Layer 2 — AST Security Validation  (validators.py)
    Layer 3 — Security Policy Engine  (policy.py)
    Layer 4 — Process Isolation & Execution  (executor.py)
    Layer 5 — Structured Output Processing  (models.py)
"""

from app.sandbox.models import (
    InputType,
    SandboxResult,
    ValidationResult,
    Violation,
    ViolationLevel,
)
from app.sandbox.policy import (
    PERMISSIVE_POLICY,
    STANDARD_POLICY,
    STRICT_POLICY,
    SecurityPolicy,
    get_policy,
)
from app.sandbox.validators import validate_code
from app.sandbox.sanitizer import sanitize_code, sanitize_input
from app.sandbox.executor import execute_code

__all__ = [
    # Models
    "InputType",
    "SandboxResult",
    "ValidationResult",
    "Violation",
    "ViolationLevel",
    # Policies
    "SecurityPolicy",
    "STRICT_POLICY",
    "STANDARD_POLICY",
    "PERMISSIVE_POLICY",
    "get_policy",
    # Core functions
    "validate_code",
    "sanitize_code",
    "sanitize_input",
    "execute_code",
]
