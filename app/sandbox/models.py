"""Data models for sandbox input, output, and validation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Violation & Validation
# ---------------------------------------------------------------------------


class ViolationLevel(enum.Enum):
    """Severity of a security violation detected during AST analysis."""

    BLOCK = "block"      # Hard stop — code will NOT execute
    WARN = "warn"        # Logged but execution proceeds


@dataclass(frozen=True)
class Violation:
    """A single policy violation found during code validation."""

    level: ViolationLevel
    rule: str            # e.g. "blocked_import", "dangerous_builtin"
    detail: str          # human-readable description
    line: int | None = None  # source line number (1-indexed), if known


@dataclass
class ValidationResult:
    """Aggregate result of all AST validators run against submitted code."""

    is_safe: bool = True
    violations: list[Violation] = field(default_factory=list)

    # Convenience helpers ------------------------------------------------

    @property
    def blocking_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.level is ViolationLevel.BLOCK]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.level is ViolationLevel.WARN]

    def add(self, violation: Violation) -> None:
        self.violations.append(violation)
        if violation.level is ViolationLevel.BLOCK:
            self.is_safe = False

    def summary(self) -> str:
        """One-line human-readable summary."""
        blocks = len(self.blocking_violations)
        warns = len(self.warnings)
        if blocks == 0 and warns == 0:
            return "Code passed all security checks"
        parts: list[str] = []
        if blocks:
            parts.append(f"{blocks} blocked")
        if warns:
            parts.append(f"{warns} warning(s)")
        return "Validation: " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Sandbox Execution Result
# ---------------------------------------------------------------------------


@dataclass
class SandboxResult:
    """Structured result from a sandbox code execution."""

    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    artifacts: list[str] = field(default_factory=list)
    execution_time_ms: int = 0
    validation: ValidationResult = field(default_factory=ValidationResult)
    blocked: bool = False
    blocked_reason: str | None = None

    # Backward-compatible dict conversion --------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to the dict format expected by the existing code_exec agent."""
        if self.blocked:
            output = self.blocked_reason or "Blocked by security policy"
        elif self.return_code != 0:
            output = self.stderr or self.stdout or (
                f"Sandbox process exited with code {self.return_code}"
            )
        else:
            output = self.stdout or "Code executed successfully with no stdout."
        return {
            "output": output,
            "artifacts": list(self.artifacts),
        }

    @property
    def success(self) -> bool:
        return not self.blocked and self.return_code == 0

    @property
    def combined_output(self) -> str:
        parts = [p for p in (self.stdout, self.stderr) if p]
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Input Specification
# ---------------------------------------------------------------------------


class InputType(enum.Enum):
    """Supported input types for sandbox code execution."""

    STRING = "string"
    NUMBER = "number"
    LIST = "list"
    JSON = "json"
    DATASET_PATH = "dataset_path"
    BOOLEAN = "boolean"
