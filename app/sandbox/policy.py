"""
Security Policy Engine — single source of truth for what the sandbox allows.

Three preset policy levels:
    STRICT      — whitelist-only imports, no network, no eval
    STANDARD    — block dangerous imports, warn on unknowns (default)
    PERMISSIVE  — block only critical operations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


PolicyLevel = Literal["strict", "standard", "permissive"]


# ---------------------------------------------------------------------------
# Core policy definition
# ---------------------------------------------------------------------------


@dataclass
class SecurityPolicy:
    """Defines the rules governing sandbox code validation and execution."""

    name: str = "standard"

    # ── Import control ──────────────────────────────────────────────────
    # Modules that are ALWAYS blocked (hard deny on all policy levels).
    blocked_modules: set[str] = field(default_factory=set)

    # When non-None: ONLY these modules are allowed (whitelist mode).
    # When None: everything not in *blocked_modules* is permitted.
    allowed_modules: set[str] | None = None

    # ── Builtin control ─────────────────────────────────────────────────
    blocked_builtins: set[str] = field(default_factory=set)

    # ── Dangerous attribute access ──────────────────────────────────────
    blocked_attributes: set[str] = field(default_factory=set)

    # ── Dangerous function calls (module.function patterns) ─────────────
    blocked_calls: set[str] = field(default_factory=set)

    # ── Resource limits ─────────────────────────────────────────────────
    max_execution_time_seconds: int = 120
    max_memory_mb: int = 512
    max_output_bytes: int = 1_048_576     # 1 MB
    max_file_size_bytes: int = 52_428_800  # 50 MB
    max_files_created: int = 20
    max_code_length: int = 100_000        # characters

    # ── Network ─────────────────────────────────────────────────────────
    allow_network: bool = False

    # ── Filesystem ──────────────────────────────────────────────────────
    # Paths the sandbox can write to (resolved at runtime).
    writable_dirs: list[Path] = field(default_factory=list)
    readable_dirs: list[Path] = field(default_factory=list)

    # ── Audit ───────────────────────────────────────────────────────────
    audit_log: bool = True


# -------------------------------------------------------------------------
# Shared deny-lists
# -------------------------------------------------------------------------

_ALWAYS_BLOCKED_MODULES: set[str] = {
    # OS-level process control
    "subprocess", "multiprocessing", "ctypes", "ctypes.util",
    # Direct OS access
    "shutil", "signal", "pty", "termios",
    # Code injection / dynamic exec
    "code", "codeop", "compileall", "py_compile",
    # Networking (blocked by default, overridden in permissive)
    "socket", "http", "http.client", "http.server",
    "xmlrpc", "xmlrpc.client", "xmlrpc.server",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib",
    "socketserver",
    # Serialisation exploits
    "pickle", "shelve", "marshal",
    # System internals
    "importlib", "runpy", "pkgutil",
    "gc", "sys", "sysconfig", "syslog",
    "resource", "mmap", "fcntl",
    # Unsafe I/O
    "tempfile", "glob", "fnmatch",
    "webbrowser",
}

_BLOCKED_BUILTINS: set[str] = {
    "eval", "exec", "compile",
    "__import__",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "type",       # can construct new classes dynamically
    "classmethod", "staticmethod",  # meta-programming
    "breakpoint",
    "memoryview",
    "exit", "quit",
}

_BLOCKED_ATTRIBUTES: set[str] = {
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__globals__",
    "__code__",
    "__builtins__",
    "__import__",
    "__loader__",
    "__spec__",
    "__class__",
    "__reduce__",
    "__reduce_ex__",
}

_BLOCKED_CALLS: set[str] = {
    "os.system",
    "os.popen",
    "os.exec",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.spawn",
    "os.spawnl",
    "os.spawnle",
    "os.fork",
    "os.kill",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.rename",
    "os.chmod",
    "os.chown",
    "os.link",
    "os.symlink",
    "os.listdir",       # information leak
    "os.scandir",
    "os.walk",
    "shutil.rmtree",
    "shutil.move",
    "shutil.copy",
    "shutil.copy2",
}

# Modules that are safe for data-science work
_SAFE_MODULES: set[str] = {
    # Core data-science
    "pandas", "numpy", "matplotlib", "matplotlib.pyplot",
    # Standard lib safe subset
    "math", "statistics", "decimal", "fractions",
    "collections", "itertools", "functools", "operator",
    "string", "re", "textwrap",
    "datetime", "time", "calendar",
    "json", "csv",
    "copy", "enum", "dataclasses", "typing",
    "pathlib", "os.path",
    "io", "hashlib", "hmac", "base64",
    "random", "secrets",
    "warnings", "logging",
    "abc", "contextlib",
    "pprint", "numbers",
}


# -------------------------------------------------------------------------
# Preset policies
# -------------------------------------------------------------------------


STRICT_POLICY = SecurityPolicy(
    name="strict",
    blocked_modules=_ALWAYS_BLOCKED_MODULES,
    allowed_modules=_SAFE_MODULES,          # whitelist mode
    blocked_builtins=_BLOCKED_BUILTINS,
    blocked_attributes=_BLOCKED_ATTRIBUTES,
    blocked_calls=_BLOCKED_CALLS,
    allow_network=False,
    max_execution_time_seconds=60,
    max_memory_mb=256,
    max_output_bytes=524_288,       # 512 KB
    max_files_created=10,
)

STANDARD_POLICY = SecurityPolicy(
    name="standard",
    blocked_modules=_ALWAYS_BLOCKED_MODULES,
    allowed_modules=None,                   # no whitelist — rely on block list
    blocked_builtins=_BLOCKED_BUILTINS,
    blocked_attributes=_BLOCKED_ATTRIBUTES,
    blocked_calls=_BLOCKED_CALLS,
    allow_network=False,
    max_execution_time_seconds=120,
    max_memory_mb=512,
)

PERMISSIVE_POLICY = SecurityPolicy(
    name="permissive",
    blocked_modules={
        "subprocess", "multiprocessing", "ctypes",
        "pty", "termios",
    },
    allowed_modules=None,
    blocked_builtins={"eval", "exec", "compile", "__import__", "breakpoint"},
    blocked_attributes={"__subclasses__", "__globals__", "__code__", "__builtins__"},
    blocked_calls={
        "os.system", "os.popen", "os.fork", "os.kill",
        "shutil.rmtree",
    },
    allow_network=True,
    max_execution_time_seconds=300,
    max_memory_mb=1024,
    max_files_created=50,
)


def get_policy(level: PolicyLevel | str = "standard") -> SecurityPolicy:
    """Return the named preset policy."""
    policies = {
        "strict": STRICT_POLICY,
        "standard": STANDARD_POLICY,
        "permissive": PERMISSIVE_POLICY,
    }
    policy = policies.get(level.lower())
    if policy is None:
        raise ValueError(
            f"Unknown policy level '{level}'. Choose from: {', '.join(policies)}"
        )
    return policy
