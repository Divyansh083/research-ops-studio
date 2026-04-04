from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from app.core.config import settings

SANDBOX_PACKAGES = ["pandas", "numpy", "matplotlib", "scipy", "seaborn", "scikit-learn"]


def get_sandbox_root() -> Path:
    return Path(settings.code_sandbox_dir).resolve()


def get_sandbox_workspace() -> Path:
    workspace = get_sandbox_root() / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def get_sandbox_site_packages() -> Path:
    if os.name == "nt":
        site_packages = get_sandbox_root() / ".venv" / "Lib" / "site-packages"
    else:
        version_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = get_sandbox_root() / ".venv" / "lib" / version_dir / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    return site_packages


def get_sandbox_python() -> Path:
    if settings.code_sandbox_python:
        return Path(settings.code_sandbox_python).expanduser().resolve()

    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    python_name = "python.exe" if os.name == "nt" else "python"
    return get_sandbox_root() / ".venv" / scripts_dir / python_name


def _build_sandbox_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["MPLBACKEND"] = "Agg"
    sandbox_root = get_sandbox_root()
    env["MPLCONFIGDIR"] = str(get_sandbox_workspace() / ".mpl_config")
    venv_dir = sandbox_root / ".venv"
    env["VIRTUAL_ENV"] = str(venv_dir)

    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    env["PATH"] = str(venv_dir / scripts_dir) + os.pathsep + env.get("PATH", "")
    return env


def _run_command(
    command: list[str],
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    output = "\n".join(part for part in (stdout, stderr) if part)
    if completed.returncode != 0:
        raise RuntimeError(output or f"Command failed with exit code {completed.returncode}")
    return output


def _requirement_is_active(requirement_text: str) -> bool:
    requirement = Requirement(requirement_text)
    if requirement.marker is None:
        return True
    return requirement.marker.evaluate()


def _iter_required_distributions() -> list[metadata.Distribution]:
    queue = list(SANDBOX_PACKAGES)
    seen: set[str] = set()
    distributions: list[metadata.Distribution] = []

    while queue:
        requirement_name = queue.pop(0)
        distribution = metadata.distribution(requirement_name)
        canonical_name = canonicalize_name(distribution.metadata["Name"])
        if canonical_name in seen:
            continue
        seen.add(canonical_name)
        distributions.append(distribution)

        for dependency in distribution.requires or []:
            if not _requirement_is_active(dependency):
                continue
            queue.append(Requirement(dependency).name)

    return distributions


def _copy_distribution_into_sandbox(distribution: metadata.Distribution) -> None:
    target_site_packages = get_sandbox_site_packages()
    files = distribution.files or []
    for relative_file in files:
        source = Path(distribution.locate_file(relative_file))
        destination = target_site_packages / relative_file
        try:
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except PermissionError:
            if destination.exists():
                pass
            else:
                raise


def _bootstrap_packages_from_host_python() -> None:
    for distribution in _iter_required_distributions():
        _copy_distribution_into_sandbox(distribution)


def setup_sandbox() -> str:
    """Create the sandbox virtual-environment and provision data-science packages."""
    sandbox_root = get_sandbox_root()
    venv_dir = sandbox_root / ".venv"
    if not venv_dir.exists():
        venv.create(str(venv_dir), with_pip=False, clear=False)
    _bootstrap_packages_from_host_python()
    get_sandbox_workspace()  # ensure workspace directory exists
    if sandbox_ready():
        return "Sandbox ready — virtual-env created and packages bootstrapped."
    return "Sandbox created but package verification could not be confirmed."


def sandbox_ready() -> bool:
    python_path = get_sandbox_python()
    if not python_path.exists():
        return False
    try:
        _run_command(
            [str(python_path), "-c", "import pandas, numpy, matplotlib; print('ok')"],
            cwd=get_sandbox_root(),
            timeout=30,
            env=_build_sandbox_env(),
        )
        return True
    except Exception:
        return False


def sandbox_packages_ready() -> bool:
    return sandbox_ready()


def install_packages(packages: list[str]) -> str:
    """Dynamically install pip packages into the sandbox."""
    if not packages:
        return "No packages requested for installation."

    python_path = get_sandbox_python()
    if not python_path.exists():
        setup_sandbox()

    try:
        _run_command(
            [str(python_path), "-m", "pip", "install", "--no-input", *packages],
            cwd=get_sandbox_root(),
            timeout=600,
            env=_build_sandbox_env(),
        )
        return f"Successfully installed: {', '.join(packages)}"
    except Exception as exc:
        raise RuntimeError(f"Failed to install packages {packages}: {exc}") from exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--setup-sandbox",
        action="store_true",
        help="Create the local code sandbox virtual environment and provision its packages.",
    )
    args = parser.parse_args()

    if args.setup_sandbox:
        print(setup_sandbox())
    else:
        print(get_sandbox_python())
