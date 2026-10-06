"""Guard the files that decide what ends up in the install and the Docker image."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def declared_modules() -> set[str]:
    pyproject = (ROOT / "pyproject.toml").read_text()
    listed = re.search(r"py-modules\s*=\s*\[(.*?)\]", pyproject, re.S).group(1)
    return set(re.findall(r'"([\w]+)"', listed))


def test_every_top_level_module_is_installed():
    modules = {path.stem for path in ROOT.glob("*.py")}
    assert modules == declared_modules(), "Add new modules to [tool.setuptools] py-modules"


def test_every_top_level_module_is_copied_into_the_docker_image():
    allowed = set((ROOT / ".dockerignore").read_text().splitlines())
    missing = [f"{path.name}" for path in ROOT.glob("*.py") if f"!{path.name}" not in allowed]
    assert not missing, f"Add to .dockerignore: {missing}"


def test_subpackage_sources_are_copied_into_the_docker_image():
    allowed = set((ROOT / ".dockerignore").read_text().splitlines())
    for package in ("commands", "audit"):
        assert f"!{package}/*.py" in allowed
    for path in (ROOT / "audit").rglob("*.py"):
        parent = path.parent.relative_to(ROOT).as_posix()
        assert f"!{parent}/*.py" in allowed, f"{parent} is missing from .dockerignore"


def test_challenge_solver_is_installed_not_downloaded_at_runtime():
    # Node.js (the Docker image's JavaScript runtime) needs this package; without it
    # yt-dlp downloads the solver from GitHub on every cold start.
    assert importlib.util.find_spec("yt_dlp_ejs") is not None
    assert "yt-dlp[default]" in (ROOT / "pyproject.toml").read_text()
