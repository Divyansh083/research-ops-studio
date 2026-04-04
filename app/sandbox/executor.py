"""
Sandbox Execution Engine — the main entry point for running code safely.

Orchestrates the full pipeline:
    Sanitise → Validate → Preamble → Execute → Collect output

This replaces the old ``run_python()`` as the primary executor while the
old function is kept as a thin wrapper for backward compatibility.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.sandbox.models import SandboxResult, ValidationResult
from app.sandbox.policy import STANDARD_POLICY, SecurityPolicy, get_policy
from app.sandbox.sanitizer import inject_safe_preamble, sanitize_code
from app.sandbox.validators import validate_code

from app.sandbox.environment import (
    _build_sandbox_env,
    get_sandbox_python,
    get_sandbox_workspace,
    sandbox_ready,
    setup_sandbox,
    get_sandbox_root,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute_code(
    code: str,
    *,
    policy: SecurityPolicy | str | None = None,
    inputs: dict[str, Any] | None = None,
    timeout_override: int | None = None,
    skip_validation: bool = False,
) -> SandboxResult:
    """
    Execute Python *code* inside the sandbox with full security pipeline.

    Parameters
    ----------
    code : str
        Raw Python source (may include markdown fences).
    policy : SecurityPolicy | str | None
        Security policy to apply. Accepts a ``SecurityPolicy`` instance,
        a policy level name (``"strict"``, ``"standard"``, ``"permissive"``),
        or ``None`` for the default (``STANDARD_POLICY``).
    inputs : dict | None
        Optional name→value mapping injected as environment variables
        prefixed with ``SANDBOX_INPUT_`` into the subprocess.
    timeout_override : int | None
        Override the policy's max execution time (seconds).
    skip_validation : bool
        If *True*, skip AST validation (use only when code is trusted,
        e.g. schema-aware analysis scripts built by the system itself).

    Returns
    -------
    SandboxResult
    """
    # ── Resolve policy ──────────────────────────────────────────────────
    if policy is None:
        resolved_policy = _resolve_default_policy()
    elif isinstance(policy, str):
        resolved_policy = get_policy(policy)
    else:
        resolved_policy = policy

    timeout = timeout_override or resolved_policy.max_execution_time_seconds

    # ── Layer 1: Sanitise code ──────────────────────────────────────────
    clean_code, sanitize_warnings = sanitize_code(
        code, max_length=resolved_policy.max_code_length,
    )

    if not clean_code.strip():
        return SandboxResult(
            blocked=True,
            blocked_reason="Submitted code is empty after sanitisation",
            validation=ValidationResult(),
        )

    # ── Layer 2: AST Security Validation ────────────────────────────────
    if skip_validation:
        validation = ValidationResult()
    else:
        validation = validate_code(clean_code, resolved_policy)

    if not validation.is_safe:
        block_details = "; ".join(v.detail for v in validation.blocking_violations)
        logger.warning("Sandbox BLOCKED code execution: %s", block_details)
        if resolved_policy.audit_log:
            _audit_log("BLOCKED", clean_code, block_details)
        return SandboxResult(
            blocked=True,
            blocked_reason=f"Security policy violation: {block_details}",
            validation=validation,
        )

    # Log warnings (but continue)
    for w in validation.warnings:
        logger.info("Sandbox validation warning: %s", w.detail)

    # ── Layer 3: Inject safe preamble ───────────────────────────────────
    final_code = inject_safe_preamble(clean_code)

    # Append os._exit(0) to prevent Windows access violations with matplotlib
    final_code += "\nimport os\nos._exit(0)\n"

    # ── Layer 4: Process Isolation — execute in sandbox subprocess ──────
    if not sandbox_ready():
        try:
            setup_sandbox()
        except Exception as exc:
            return SandboxResult(
                blocked=True,
                blocked_reason=(
                    f"Sandbox auto-setup failed: {exc}. "
                    "Run `python -m app.tools.python_repl --setup-sandbox` manually."
                ),
                validation=validation,
            )

    workspace = get_sandbox_workspace()

    # Snapshot files before execution
    before_files = {
        p.name: p.stat().st_mtime
        for p in workspace.glob("*")
        if p.is_file()
    }

    # Write script
    script_path = workspace / "code_exec_latest.py"
    script_path.write_text(final_code, encoding="utf-8")

    # Build environment
    env = _build_sandbox_env()

    # Inject user inputs as env vars
    if inputs:
        for key, value in inputs.items():
            safe_key = f"SANDBOX_INPUT_{key.upper()}"
            env[safe_key] = str(value)

    # Execute
    start_time = time.perf_counter()
    try:
        completed = subprocess.run(
            [str(get_sandbox_python()), str(script_path)],
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if resolved_policy.audit_log:
            _audit_log("TIMEOUT", clean_code, f"Timed out after {timeout}s")
        return SandboxResult(
            stdout="",
            stderr=f"Execution timed out after {timeout}s",
            return_code=-1,
            execution_time_ms=elapsed_ms,
            validation=validation,
        )

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # ── Layer 5: Output Processing ──────────────────────────────────────
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    # Truncate output if too large
    if len(stdout) > resolved_policy.max_output_bytes:
        stdout = stdout[: resolved_policy.max_output_bytes] + "\n... [output truncated]"
    if len(stderr) > resolved_policy.max_output_bytes:
        stderr = stderr[: resolved_policy.max_output_bytes] + "\n... [stderr truncated]"

    # Detect new/modified artifacts
    after_files = {
        p.name: p.stat().st_mtime
        for p in workspace.glob("*")
        if p.is_file()
    }
    artifact_names: list[str] = []
    for name, mtime in after_files.items():
        if name == "code_exec_latest.py":
            continue
        if name not in before_files or mtime > before_files[name]:
            artifact_names.append(name)
    artifact_names.sort()

    # Enforce max files limit
    if len(artifact_names) > resolved_policy.max_files_created:
        artifact_names = artifact_names[: resolved_policy.max_files_created]
        logger.warning(
            "Sandbox capped artifacts to %d files",
            resolved_policy.max_files_created,
        )

    # Enforce max file size
    for art_name in list(artifact_names):
        art_path = workspace / art_name
        if art_path.exists() and art_path.stat().st_size > resolved_policy.max_file_size_bytes:
            logger.warning("Artifact '%s' exceeds max file size — removed", art_name)
            artifact_names.remove(art_name)

    if resolved_policy.audit_log:
        status = "SUCCESS" if completed.returncode == 0 else "ERROR"
        _audit_log(status, clean_code, stdout[:200] if stdout else stderr[:200])

    return SandboxResult(
        stdout=stdout,
        stderr=stderr,
        return_code=completed.returncode if completed.returncode is not None else -1,
        artifacts=artifact_names,
        execution_time_ms=elapsed_ms,
        validation=validation,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_default_policy() -> SecurityPolicy:
    """Read the policy level from app config, falling back to STANDARD."""
    try:
        from app.core.config import settings
        return get_policy(settings.code_sandbox_policy)
    except Exception:
        return STANDARD_POLICY


def _audit_log(status: str, code: str, detail: str) -> None:
    """Append a line to the sandbox audit log."""
    try:
        log_path = get_sandbox_root() / "audit.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        code_preview = code[:120].replace("\n", "\\n")
        detail_preview = detail[:200].replace("\n", "\\n")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {status} | {code_preview} | {detail_preview}\n")
    except Exception:
        pass  # audit logging must never break execution
