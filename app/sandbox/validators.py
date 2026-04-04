"""
AST-based pre-execution security validators.

Walks the Python AST to detect policy violations *before* the code is sent
to the sandbox subprocess.  This is Layer 2 of the defense-in-depth model.

Validators:
    1. ImportValidator       — blocked / whitelisted module imports
    2. BuiltinValidator      — blocked builtin function calls
    3. AttributeValidator    — dangerous dunder attribute access
    4. CallPatternValidator  — dangerous module.function() calls
    5. ComplexityValidator    — excessive nesting / recursion (warn only)

Usage:
    result = validate_code(source_code, policy)
    if not result.is_safe:
        ...  # refuse execution
"""

from __future__ import annotations

import ast
from typing import Sequence

from app.sandbox.models import ValidationResult, Violation, ViolationLevel
from app.sandbox.policy import SecurityPolicy


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------


def _validate_imports(
    tree: ast.Module,
    policy: SecurityPolicy,
) -> list[Violation]:
    """Check every import statement against blocked / allowed modules."""
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, node.lineno, policy, violations)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            _check_module(module, node.lineno, policy, violations)

    return violations


def _check_module(
    module_name: str,
    lineno: int,
    policy: SecurityPolicy,
    violations: list[Violation],
) -> None:
    """Test a single module name (or dotted prefix) against policy."""
    top_level = module_name.split(".")[0]

    # Hard-blocked modules
    if module_name in policy.blocked_modules or top_level in policy.blocked_modules:
        violations.append(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="blocked_import",
                detail=f"Import of '{module_name}' is blocked by security policy",
                line=lineno,
            )
        )
        return

    # Whitelist mode: if allowed_modules is set, everything not listed is blocked
    if policy.allowed_modules is not None:
        if module_name not in policy.allowed_modules and top_level not in policy.allowed_modules:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="unlisted_import",
                    detail=(
                        f"Import of '{module_name}' is not in the allowed modules whitelist"
                    ),
                    line=lineno,
                )
            )

    # Network module detection (when network is disallowed)
    if not policy.allow_network:
        network_modules = {
            "requests", "httpx", "aiohttp", "urllib", "urllib.request",
            "urllib3", "socket", "http", "http.client",
        }
        if module_name in network_modules or top_level in network_modules:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="network_import",
                    detail=(
                        f"Import of '{module_name}' requires network access which "
                        "is disabled by policy"
                    ),
                    line=lineno,
                )
            )


def _validate_builtins(
    tree: ast.Module,
    policy: SecurityPolicy,
) -> list[Violation]:
    """Detect calls to blocked builtin functions."""
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        name: str | None = None

        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr

        if name and name in policy.blocked_builtins:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="blocked_builtin",
                    detail=f"Use of builtin '{name}()' is blocked by security policy",
                    line=getattr(node, "lineno", None),
                )
            )

    return violations


def _validate_attributes(
    tree: ast.Module,
    policy: SecurityPolicy,
) -> list[Violation]:
    """Detect access to dangerous dunder attributes (sandbox escape vectors)."""
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue

        if node.attr in policy.blocked_attributes:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="blocked_attribute",
                    detail=(
                        f"Access to '{node.attr}' is blocked — "
                        "potential sandbox escape vector"
                    ),
                    line=getattr(node, "lineno", None),
                )
            )

    return violations


def _validate_call_patterns(
    tree: ast.Module,
    policy: SecurityPolicy,
) -> list[Violation]:
    """Detect dangerous module.function() call patterns like os.system()."""
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if not isinstance(func, ast.Attribute):
            continue

        # Reconstruct dotted call: e.g.  os.system(...)
        parts: list[str] = [func.attr]
        current = func.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)

        dotted = ".".join(reversed(parts))

        if dotted in policy.blocked_calls:
            violations.append(
                Violation(
                    level=ViolationLevel.BLOCK,
                    rule="blocked_call",
                    detail=f"Call to '{dotted}()' is blocked by security policy",
                    line=getattr(node, "lineno", None),
                )
            )

    return violations


def _validate_string_patterns(
    source: str,
    policy: SecurityPolicy,
) -> list[Violation]:
    """Catch bypass attempts that hide inside string literals or comments."""
    violations: list[Violation] = []

    # Detect common code-injection via string eval patterns
    danger_fragments = [
        ("__import__", "blocked_string_import", "String contains '__import__' which may bypass import blocks"),
        ("os.system", "blocked_string_call", "String contains 'os.system' — possible eval-based bypass"),
        ("subprocess", "blocked_string_module", "String contains 'subprocess' — possible dynamic import bypass"),
    ]

    source_lower = source.lower()
    for fragment, rule, detail in danger_fragments:
        if fragment in source_lower:
            # Only warn — the AST validators already block actual usage.
            # String occurrences might be in comments or docstrings.
            violations.append(
                Violation(
                    level=ViolationLevel.WARN,
                    rule=rule,
                    detail=detail,
                )
            )

    return violations


_MAX_NESTING = 8


def _validate_complexity(
    tree: ast.Module,
    _policy: SecurityPolicy,
) -> list[Violation]:
    """Warn on code that is excessively nested (potential DoS via deep loops)."""
    violations: list[Violation] = []

    def _walk_depth(node: ast.AST, depth: int = 0) -> None:
        if isinstance(node, (ast.For, ast.While, ast.If, ast.With, ast.Try)):
            depth += 1
            if depth > _MAX_NESTING:
                violations.append(
                    Violation(
                        level=ViolationLevel.WARN,
                        rule="high_complexity",
                        detail=(
                            f"Code has nesting depth >{_MAX_NESTING} at line "
                            f"{getattr(node, 'lineno', '?')} — potential DoS risk"
                        ),
                        line=getattr(node, "lineno", None),
                    )
                )
                return  # stop descending

        for child in ast.iter_child_nodes(node):
            _walk_depth(child, depth)

    _walk_depth(tree)
    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_VALIDATORS = [
    _validate_imports,
    _validate_builtins,
    _validate_attributes,
    _validate_call_patterns,
    _validate_complexity,
]


def validate_code(
    source: str,
    policy: SecurityPolicy,
) -> ValidationResult:
    """
    Run all security validators against *source* under *policy*.

    Returns a ``ValidationResult`` whose ``.is_safe`` property is ``False``
    when any blocking violation was found.
    """
    result = ValidationResult()

    # 0. Parse the source to AST
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result.add(
            Violation(
                level=ViolationLevel.BLOCK,
                rule="syntax_error",
                detail=f"Code has a syntax error and cannot be validated: {exc}",
                line=getattr(exc, "lineno", None),
            )
        )
        return result

    # 1. Run AST validators
    for validator in _VALIDATORS:
        for violation in validator(tree, policy):
            result.add(violation)

    # 2. Run string-level checks (supplementary)
    for violation in _validate_string_patterns(source, policy):
        result.add(violation)

    return result
