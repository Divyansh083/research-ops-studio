"""Comprehensive tests for the sandbox execution system.

Covers:
    - AST validation (blocked imports, builtins, attributes, call patterns)
    - Input sanitisation (all types + edge cases)
    - Code sanitisation (fences, null bytes, length)
    - Security policy presets
    - Executor integration (mocked subprocess)
    - Backward-compatible run_python wrapper
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
from app.sandbox.sanitizer import inject_safe_preamble, sanitize_code, sanitize_input
from app.sandbox.validators import validate_code


# =========================================================================
# Policy tests
# =========================================================================


class TestSecurityPolicy:
    def test_get_policy_standard(self):
        policy = get_policy("standard")
        assert policy.name == "standard"
        assert "subprocess" in policy.blocked_modules

    def test_get_policy_strict(self):
        policy = get_policy("strict")
        assert policy.allowed_modules is not None  # whitelist mode
        assert "pandas" in policy.allowed_modules

    def test_get_policy_permissive(self):
        policy = get_policy("permissive")
        assert policy.allow_network is True

    def test_get_policy_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown policy"):
            get_policy("nonexistent")

    def test_standard_blocks_subprocess(self):
        assert "subprocess" in STANDARD_POLICY.blocked_modules

    def test_standard_blocks_eval(self):
        assert "eval" in STANDARD_POLICY.blocked_builtins

    def test_standard_blocks_dunder_subclasses(self):
        assert "__subclasses__" in STANDARD_POLICY.blocked_attributes


# =========================================================================
# Validator tests
# =========================================================================


class TestValidateCode:
    """Tests for AST-based security validation."""

    def test_safe_pandas_code_passes(self):
        code = "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())\n"
        result = validate_code(code, STANDARD_POLICY)
        assert result.is_safe
        assert len(result.blocking_violations) == 0

    def test_safe_math_code_passes(self):
        code = "x = 2 + 3\nprint(x)\n"
        result = validate_code(code, STANDARD_POLICY)
        assert result.is_safe

    def test_blocks_subprocess_import(self):
        code = "import subprocess\nsubprocess.run(['ls'])\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe
        assert any(v.rule == "blocked_import" for v in result.blocking_violations)

    def test_blocks_os_system_call(self):
        code = "import os\nos.system('rm -rf /')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe
        assert any(v.rule == "blocked_call" for v in result.blocking_violations)

    def test_blocks_eval_builtin(self):
        code = "result = eval('2 + 2')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe
        assert any(v.rule == "blocked_builtin" for v in result.blocking_violations)

    def test_blocks_exec_builtin(self):
        code = "exec('print(1)')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_dunder_subclasses(self):
        code = "x = ''.__class__.__subclasses__()\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe
        assert any(v.rule == "blocked_attribute" for v in result.blocking_violations)

    def test_blocks_dunder_globals(self):
        code = "f = lambda: None\nf.__globals__\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_shutil_rmtree(self):
        code = "import shutil\nshutil.rmtree('/important')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_socket_import(self):
        code = "import socket\ns = socket.socket()\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_pickle_import(self):
        code = "import pickle\npickle.loads(data)\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_ctypes_import(self):
        code = "import ctypes\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_network_imports_when_no_network(self):
        code = "import requests\nrequests.get('http://evil.com')\n"
        policy = SecurityPolicy(allow_network=False)
        result = validate_code(code, policy)
        assert not result.is_safe
        assert any(v.rule == "network_import" for v in result.blocking_violations)

    def test_allows_network_imports_when_network_enabled(self):
        code = "import requests\nrequests.get('http://api.com')\n"
        result = validate_code(code, PERMISSIVE_POLICY)
        # Permissive allows network
        network_blocks = [
            v for v in result.blocking_violations if v.rule == "network_import"
        ]
        assert len(network_blocks) == 0

    def test_strict_blocks_unlisted_import(self):
        code = "import some_unknown_lib\n"
        result = validate_code(code, STRICT_POLICY)
        assert not result.is_safe
        assert any(v.rule == "unlisted_import" for v in result.blocking_violations)

    def test_warns_on_string_containing_import(self):
        code = "x = 'use __import__ to load'\nprint(x)\n"
        result = validate_code(code, STANDARD_POLICY)
        # Should warn but not block (the string itself isn't executable)
        assert any(v.rule == "blocked_string_import" for v in result.warnings)

    def test_syntax_error_blocks(self):
        code = "def f(\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe
        assert any(v.rule == "syntax_error" for v in result.blocking_violations)

    def test_high_nesting_warns(self):
        # Build deeply nested code
        code = ""
        for i in range(10):
            code += "    " * i + f"if True:\n"
        code += "    " * 10 + "pass\n"
        result = validate_code(code, STANDARD_POLICY)
        warns = [v for v in result.warnings if v.rule == "high_complexity"]
        assert len(warns) > 0

    def test_blocks_os_remove(self):
        code = "import os\nos.remove('file.txt')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_blocks_os_popen(self):
        code = "import os\nos.popen('whoami')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe

    def test_allows_os_path_join(self):
        """os.path operations should be safe."""
        code = "import os.path\nresult = os.path.join('a', 'b')\nprint(result)\n"
        result = validate_code(code, STANDARD_POLICY)
        # os.path.join is not in blocked_calls
        call_blocks = [v for v in result.blocking_violations if v.rule == "blocked_call"]
        assert len(call_blocks) == 0

    def test_blocks_compile_builtin(self):
        code = "c = compile('print(1)', '<string>', 'exec')\n"
        result = validate_code(code, STANDARD_POLICY)
        assert not result.is_safe


# =========================================================================
# Sanitiser tests
# =========================================================================


class TestSanitizeCode:
    def test_strips_markdown_fences(self):
        raw = "```python\nprint('hi')\n```"
        clean, warnings = sanitize_code(raw)
        assert "```" not in clean
        assert "print('hi')" in clean

    def test_removes_null_bytes(self):
        raw = "print('hi')\x00"
        clean, warnings = sanitize_code(raw)
        assert "\x00" not in clean
        assert len(warnings) == 1

    def test_truncates_long_code(self):
        raw = "x = 1\n" * 50_000
        clean, warnings = sanitize_code(raw, max_length=100)
        assert len(clean) <= 101  # 100 + trailing newline
        assert any("truncated" in w.lower() for w in warnings)

    def test_adds_trailing_newline(self):
        raw = "x = 1"
        clean, _ = sanitize_code(raw)
        assert clean.endswith("\n")

    def test_normalises_line_endings(self):
        raw = "a = 1\r\nb = 2\r"
        clean, _ = sanitize_code(raw)
        assert "\r" not in clean

    def test_empty_after_strip(self):
        raw = "```python\n```"
        clean, _ = sanitize_code(raw)
        assert clean.strip() == ""


class TestSanitizeInput:
    # -- STRING --
    def test_string_passthrough(self):
        val, viols = sanitize_input("hello", InputType.STRING)
        assert val == "hello"
        assert len(viols) == 0

    def test_string_truncation(self):
        val, viols = sanitize_input("a" * 200, InputType.STRING, max_string_length=50)
        assert len(val) == 50
        assert any(v.rule == "input_truncated" for v in viols)

    def test_string_null_byte_removal(self):
        val, viols = sanitize_input("he\x00llo", InputType.STRING)
        assert "\x00" not in val
        assert any(v.rule == "input_sanitized" for v in viols)

    # -- NUMBER --
    def test_number_int(self):
        val, viols = sanitize_input(42, InputType.NUMBER)
        assert val == 42
        assert len(viols) == 0

    def test_number_float(self):
        val, viols = sanitize_input(3.14, InputType.NUMBER)
        assert val == 3.14

    def test_number_string_parse(self):
        val, viols = sanitize_input("42", InputType.NUMBER)
        assert val == 42

    def test_number_nan_blocked(self):
        val, viols = sanitize_input(float("nan"), InputType.NUMBER)
        assert any(v.level == ViolationLevel.BLOCK for v in viols)

    def test_number_inf_blocked(self):
        val, viols = sanitize_input(float("inf"), InputType.NUMBER)
        assert any(v.level == ViolationLevel.BLOCK for v in viols)

    def test_number_range_check(self):
        val, viols = sanitize_input(999, InputType.NUMBER, number_range=(0, 100))
        assert any(v.rule == "input_out_of_range" for v in viols)

    def test_number_bool_rejected(self):
        val, viols = sanitize_input(True, InputType.NUMBER)
        assert any(v.level == ViolationLevel.BLOCK for v in viols)

    # -- LIST --
    def test_list_passthrough(self):
        val, viols = sanitize_input([1, 2, 3], InputType.LIST)
        assert val == [1, 2, 3]

    def test_list_from_json_string(self):
        val, viols = sanitize_input("[1, 2, 3]", InputType.LIST)
        assert val == [1, 2, 3]

    def test_list_truncation(self):
        val, viols = sanitize_input(list(range(100)), InputType.LIST, max_list_length=10)
        assert len(val) == 10

    def test_list_invalid_string(self):
        val, viols = sanitize_input("not a list", InputType.LIST)
        assert any(v.level == ViolationLevel.BLOCK for v in viols)

    # -- JSON --
    def test_json_dict(self):
        val, viols = sanitize_input({"key": "value"}, InputType.JSON)
        assert val == {"key": "value"}

    def test_json_string_parse(self):
        val, viols = sanitize_input('{"a": 1}', InputType.JSON)
        assert val == {"a": 1}

    def test_json_too_deep(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": 1}}}}}}}}}}}
        val, viols = sanitize_input(deep, InputType.JSON, max_json_depth=5)
        assert any(v.rule == "input_too_deep" for v in viols)

    def test_json_too_large(self):
        val, viols = sanitize_input("x" * 200_000, InputType.JSON, max_json_size=100)
        assert any(v.rule == "input_too_large" for v in viols)

    # -- DATASET_PATH --
    def test_dataset_path_traversal_blocked(self):
        val, viols = sanitize_input("../../etc/passwd", InputType.DATASET_PATH)
        assert any(v.rule == "path_traversal" for v in viols)

    def test_dataset_path_nonexistent_warns(self, tmp_path):
        from app.core.config import settings
        valid_root = Path(settings.dataset_root_dir).resolve()
        val, viols = sanitize_input(
            str(valid_root / "nonexistent.csv"), InputType.DATASET_PATH
        )
        assert any(v.rule == "path_not_found" for v in viols)
        # Warns, not blocks
        assert all(v.level != ViolationLevel.BLOCK for v in viols)

    # -- BOOLEAN --
    def test_boolean_true(self):
        val, viols = sanitize_input(True, InputType.BOOLEAN)
        assert val is True

    def test_boolean_string_yes(self):
        val, viols = sanitize_input("yes", InputType.BOOLEAN)
        assert val is True

    def test_boolean_string_false(self):
        val, viols = sanitize_input("false", InputType.BOOLEAN)
        assert val is False


class TestSafePreamble:
    def test_inject_preamble(self):
        code = "import pandas\ndf = pd.read_csv('data.csv')\n"
        result = inject_safe_preamble(code)
        assert "Sandbox Safe Preamble" in result
        assert "matplotlib.use" in result
        assert code in result

    def test_no_double_inject(self):
        code = "# Sandbox Safe Preamble\nimport pandas\n"
        result = inject_safe_preamble(code)
        assert result.count("Sandbox Safe Preamble") == 1


# =========================================================================
# Model tests
# =========================================================================


class TestModels:
    def test_validation_result_summary_clean(self):
        vr = ValidationResult()
        assert "passed" in vr.summary().lower()

    def test_validation_result_summary_with_blocks(self):
        vr = ValidationResult()
        vr.add(Violation(ViolationLevel.BLOCK, "test", "blocked something"))
        assert "1 blocked" in vr.summary()
        assert not vr.is_safe

    def test_validation_result_summary_with_warnings(self):
        vr = ValidationResult()
        vr.add(Violation(ViolationLevel.WARN, "test", "warning"))
        assert "1 warning" in vr.summary()
        assert vr.is_safe  # warnings don't block

    def test_sandbox_result_to_dict_success(self):
        sr = SandboxResult(stdout="hello", return_code=0)
        d = sr.to_dict()
        assert d["output"] == "hello"
        assert sr.success

    def test_sandbox_result_to_dict_error(self):
        sr = SandboxResult(stderr="error msg", return_code=1)
        d = sr.to_dict()
        assert "error msg" in d["output"]
        assert not sr.success

    def test_sandbox_result_to_dict_blocked(self):
        sr = SandboxResult(blocked=True, blocked_reason="unsafe code")
        d = sr.to_dict()
        assert "unsafe code" in d["output"]
        assert not sr.success


# =========================================================================
# Executor integration tests (mocked subprocess)
# =========================================================================


class TestExecutor:
    @patch("app.sandbox.executor.setup_sandbox")
    @patch("app.sandbox.executor.sandbox_ready", return_value=True)
    @patch("app.sandbox.executor.get_sandbox_workspace")
    @patch("app.sandbox.executor.get_sandbox_python")
    @patch("app.sandbox.executor._build_sandbox_env")
    def test_execute_safe_code(self, mock_build, mock_python, mock_workspace, mock_ready, mock_setup, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mock_workspace.return_value = workspace
        mock_python.return_value = tmp_path / "python.exe"
        mock_build.return_value = {"PATH": "", "MPLBACKEND": "Agg"}

        with patch("app.sandbox.executor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="hello world",
                stderr="",
            )
            from app.sandbox.executor import execute_code

            result = execute_code("print('hello world')\n")
            assert result.success
            assert result.stdout == "hello world"

    @patch("app.sandbox.executor._build_sandbox_env")
    def test_execute_blocked_code(self, mock_env):
        from app.sandbox.executor import execute_code

        result = execute_code("import subprocess\nsubprocess.run(['ls'])\n")
        assert result.blocked
        assert "security policy" in result.blocked_reason.lower()

    @patch("app.sandbox.executor._build_sandbox_env")
    def test_execute_empty_code(self, mock_env):
        from app.sandbox.executor import execute_code

        result = execute_code("")
        assert result.blocked
        assert "empty" in result.blocked_reason.lower()

    @patch("app.sandbox.executor.setup_sandbox")
    @patch("app.sandbox.executor.sandbox_ready", return_value=True)
    @patch("app.sandbox.executor.get_sandbox_workspace")
    @patch("app.sandbox.executor.get_sandbox_python")
    @patch("app.sandbox.executor._build_sandbox_env")
    def test_execute_timeout(self, mock_build, mock_python, mock_workspace, mock_ready, mock_setup, tmp_path):
        import subprocess as real_subprocess

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mock_workspace.return_value = workspace
        mock_python.return_value = tmp_path / "python.exe"
        mock_build.return_value = {"PATH": "", "MPLBACKEND": "Agg"}

        with patch("app.sandbox.executor.subprocess.run") as mock_run:
            mock_run.side_effect = real_subprocess.TimeoutExpired(
                cmd="python", timeout=10
            )
            from app.sandbox.executor import execute_code

            result = execute_code("import time\ntime.sleep(999)\n", timeout_override=10)
            assert not result.success
            assert "timed out" in result.stderr.lower()

    @patch("app.sandbox.executor.setup_sandbox")
    @patch("app.sandbox.executor.sandbox_ready", return_value=True)
    @patch("app.sandbox.executor.get_sandbox_workspace")
    @patch("app.sandbox.executor.get_sandbox_python")
    @patch("app.sandbox.executor._build_sandbox_env")
    def test_skip_validation_flag(self, mock_build, mock_python, mock_workspace, mock_ready, mock_setup, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mock_workspace.return_value = workspace
        mock_python.return_value = tmp_path / "python.exe"
        mock_build.return_value = {"PATH": "", "MPLBACKEND": "Agg"}

        with patch("app.sandbox.executor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            from app.sandbox.executor import execute_code

            # This code would normally be blocked, but skip_validation=True
            result = execute_code(
                "import subprocess\n",
                skip_validation=True,
            )
            assert result.success


# =========================================================================
# Environment management tests
# =========================================================================


class TestSandboxEnvironment:
    @patch("app.sandbox.environment._run_command")
    def test_sandbox_packages_ready_checks_imports(self, mock_run_command):
        from app.sandbox.environment import sandbox_packages_ready

        mock_run_command.return_value = "ok"
        assert sandbox_packages_ready() is True

    def test_build_sandbox_env_clears_python_inheritance(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", r"C:\temp\host_path")
        monkeypatch.setenv("PYTHONHOME", r"C:\Python")

        from app.sandbox.environment import _build_sandbox_env

        env = _build_sandbox_env()
        assert "PYTHONPATH" not in env
        assert "PYTHONHOME" not in env
        assert env["MPLBACKEND"] == "Agg"

    @patch("app.sandbox.environment._bootstrap_packages_from_host_python")
    @patch("app.sandbox.environment.sandbox_ready", return_value=True)
    def test_setup_sandbox_bootstraps_host_packages(
        self, mock_sandbox_ready, mock_bootstrap_packages
    ):
        from app.sandbox.environment import setup_sandbox

        message = setup_sandbox()
        assert "sandbox ready" in message.lower()
        mock_bootstrap_packages.assert_called_once()
