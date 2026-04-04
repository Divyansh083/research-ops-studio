"""
Input sanitisation and code pre-processing.

Layer 1 of the defense model — cleans and validates everything
*before* it reaches the AST validators.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from app.sandbox.models import InputType, Violation, ViolationLevel


# ---------------------------------------------------------------------------
# Code sanitisation
# ---------------------------------------------------------------------------


def sanitize_code(raw: str, *, max_length: int = 100_000) -> tuple[str, list[str]]:
    """
    Clean up raw code text before AST validation.

    Returns ``(cleaned_code, warnings_list)``.
    """
    warnings: list[str] = []

    # 1. Strip markdown code fences
    text = _strip_code_fences(raw)

    # 2. Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Remove null bytes (common injection vector)
    if "\x00" in text:
        text = text.replace("\x00", "")
        warnings.append("Removed null bytes from code input")

    # 4. Length limit
    if len(text) > max_length:
        text = text[:max_length]
        warnings.append(
            f"Code truncated to {max_length:,} characters (was {len(raw):,})"
        )

    # 5. Ensure trailing newline (Python's parser expects it)
    if text and not text.endswith("\n"):
        text += "\n"

    return text, warnings


def _strip_code_fences(raw: str) -> str:
    """Remove markdown ``` fences wrapping the code."""
    text = raw.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    # Drop first fence line
    if lines:
        lines = lines[1:]
    # Drop last fence line
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------


def sanitize_input(
    value: Any,
    expected_type: InputType,
    *,
    max_string_length: int = 10_000,
    max_list_length: int = 1_000,
    max_json_depth: int = 10,
    max_json_size: int = 100_000,
    number_range: tuple[float, float] | None = None,
) -> tuple[Any, list[Violation]]:
    """
    Validate and coerce a single input value.

    Returns ``(sanitized_value, list_of_violations)``.
    An empty violations list means the input is clean.
    """
    violations: list[Violation] = []

    if expected_type is InputType.STRING:
        return _sanitize_string(value, max_string_length, violations)

    if expected_type is InputType.NUMBER:
        return _sanitize_number(value, number_range, violations)

    if expected_type is InputType.LIST:
        return _sanitize_list(value, max_list_length, violations)

    if expected_type is InputType.JSON:
        return _sanitize_json(value, max_json_depth, max_json_size, violations)

    if expected_type is InputType.DATASET_PATH:
        return _sanitize_dataset_path(value, violations)

    if expected_type is InputType.BOOLEAN:
        return _sanitize_boolean(value, violations)

    violations.append(
        Violation(
            level=ViolationLevel.BLOCK,
            rule="unknown_input_type",
            detail=f"Unknown input type: {expected_type}",
        )
    )
    return value, violations


# ---------------------------------------------------------------------------
# Type-specific sanitisers
# ---------------------------------------------------------------------------


def _sanitize_string(
    value: Any, max_length: int, violations: list[Violation]
) -> tuple[str, list[Violation]]:
    if not isinstance(value, str):
        try:
            value = str(value)
            violations.append(
                Violation(
                    level=ViolationLevel.WARN,
                    rule="input_coerced",
                    detail=f"Non-string input coerced to string: {type(value).__name__}",
                )
            )
        except Exception:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_invalid",
                    detail="Input cannot be converted to string",
                )
            )
            return "", violations

    if len(value) > max_length:
        value = value[:max_length]
        violations.append(
            Violation(
                level=ViolationLevel.WARN,
                rule="input_truncated",
                detail=f"String input truncated to {max_length:,} characters",
            )
        )

    # Remove null bytes
    if "\x00" in value:
        value = value.replace("\x00", "")
        violations.append(
            Violation(
                level=ViolationLevel.WARN,
                rule="input_sanitized",
                detail="Null bytes removed from string input",
            )
        )

    return value, violations


def _sanitize_number(
    value: Any,
    allowed_range: tuple[float, float] | None,
    violations: list[Violation],
) -> tuple[float | int, list[Violation]]:
    if isinstance(value, bool):
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_invalid",
                detail="Boolean is not accepted as a number",
            )
        )
        return 0, violations

    if isinstance(value, (int, float)):
        num = value
    elif isinstance(value, str):
        try:
            num = int(value) if "." not in value else float(value)
        except ValueError:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_invalid",
                    detail=f"Cannot parse '{value}' as a number",
                )
            )
            return 0, violations
    else:
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_invalid",
                detail=f"Expected number, got {type(value).__name__}",
            )
        )
        return 0, violations

    if isinstance(num, float) and (math.isnan(num) or math.isinf(num)):
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_invalid",
                detail="NaN and Infinity are not accepted as input numbers",
            )
        )
        return 0, violations

    if allowed_range is not None:
        lo, hi = allowed_range
        if not (lo <= num <= hi):
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_out_of_range",
                    detail=f"Number {num} is outside allowed range [{lo}, {hi}]",
                )
            )
            return 0, violations

    return num, violations


def _sanitize_list(
    value: Any, max_length: int, violations: list[Violation]
) -> tuple[list, list[Violation]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_invalid",
                    detail="String input could not be parsed as a JSON list",
                )
            )
            return [], violations

    if not isinstance(value, list):
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_invalid",
                detail=f"Expected list, got {type(value).__name__}",
            )
        )
        return [], violations

    if len(value) > max_length:
        value = value[:max_length]
        violations.append(
            Violation(
                level=ViolationLevel.WARN,
                rule="input_truncated",
                detail=f"List truncated to {max_length:,} elements",
            )
        )

    return value, violations


def _sanitize_json(
    value: Any,
    max_depth: int,
    max_size: int,
    violations: list[Violation],
) -> tuple[Any, list[Violation]]:
    if isinstance(value, str):
        if len(value) > max_size:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_too_large",
                    detail=f"JSON string exceeds max size ({len(value):,} > {max_size:,})",
                )
            )
            return None, violations
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="input_invalid",
                    detail=f"Invalid JSON: {exc}",
                )
            )
            return None, violations

    # Check depth
    depth = _json_depth(value)
    if depth > max_depth:
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_too_deep",
                detail=f"JSON nesting depth {depth} exceeds max {max_depth}",
            )
        )
        return None, violations

    return value, violations


def _json_depth(obj: Any, current: int = 1) -> int:
    if isinstance(obj, dict):
        if not obj:
            return current
        return max(_json_depth(v, current + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return current
        return max(_json_depth(v, current + 1) for v in obj)
    return current


def _sanitize_dataset_path(
    value: Any, violations: list[Violation]
) -> tuple[str, list[Violation]]:
    if not isinstance(value, str):
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="input_invalid",
                detail=f"Dataset path must be a string, got {type(value).__name__}",
            )
        )
        return "", violations

    # Path traversal prevention
    normalized = value.replace("\\", "/")
    if ".." in normalized.split("/"):
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="path_traversal",
                detail="Dataset path contains '..' — path traversal blocked",
            )
        )
        return "", violations

    # Path boundary enforcement
    path = Path(value).resolve()
    try:
        from app.core.config import settings
        dataset_root = Path(settings.dataset_root_dir).resolve()
        if not path.is_relative_to(dataset_root):
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="path_traversal",
                    detail="Dataset path resides outside the allowed dataset root directory",
                )
            )
            return "", violations
    except ImportError:
        pass

    # Existence check
    if not path.exists():
        violations.append(
            Violation(
                level=ViolationLevel.WARN,
                rule="path_not_found",
                detail=f"Dataset path does not exist: {value}",
            )
        )

    return str(path), violations


def _sanitize_boolean(
    value: Any, violations: list[Violation]
) -> tuple[bool, list[Violation]]:
    if isinstance(value, bool):
        return value, violations
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True, violations
        if value.lower() in ("false", "0", "no"):
            return False, violations
    if isinstance(value, (int, float)):
        return bool(value), violations

    violations.append(
        Violation(
            level=ViolationLevel.BLOCK,
            rule="input_invalid",
            detail=f"Cannot interpret '{value}' as boolean",
        )
    )
    return False, violations


# ---------------------------------------------------------------------------
# Safe preamble injection
# ---------------------------------------------------------------------------


_SAFE_PREAMBLE = '''\
# ── Sandbox Safe Preamble (auto-injected) ──────────────────────────────
import os as _sandbox_os
import sys as _sandbox_sys

# Force non-interactive matplotlib backend
_sandbox_os.environ.setdefault("PYTHONNOUSERSITE", "1")
_sandbox_os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
_sandbox_os.environ.setdefault("MPLBACKEND", "Agg")

try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as _sandbox_plt

    _sandbox_plot_dir = _sandbox_os.getenv("CODE_EXEC_PLOT_DIR", _sandbox_os.getcwd())
    _sandbox_os.makedirs(_sandbox_plot_dir, exist_ok=True)
    _sandbox_orig_show = _sandbox_plt.show

    def _sandbox_capture_show(*args, **kwargs):
        for _i, _num in enumerate(_sandbox_plt.get_fignums(), 1):
            _sandbox_plt.figure(_num).savefig(
                _sandbox_os.path.join(_sandbox_plot_dir, f"figure_{_i}.png"),
                dpi=150, bbox_inches="tight",
            )
        _sandbox_plt.close("all")

    _sandbox_plt.show = _sandbox_capture_show
except ImportError:
    pass

# ── End Preamble ───────────────────────────────────────────────────────
'''


def inject_safe_preamble(code: str) -> str:
    """Prepend the safe preamble to user code."""
    # Don't double-inject
    if "Sandbox Safe Preamble" in code:
        return code
    return _SAFE_PREAMBLE + "\n" + code
