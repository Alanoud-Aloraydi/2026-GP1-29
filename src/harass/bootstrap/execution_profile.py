"""Fingerprint execution inputs before admitting or resuming durable work."""

import hashlib
from importlib.metadata import version
from pathlib import Path

from harass.infrastructure.settings import Settings


def execution_profile(settings: Settings) -> str:
    """Hash model settings, dependencies, dataset and execution sources."""
    digest = hashlib.sha256(repr(settings).encode("utf-8"))
    for dependency in ("pyrit", "openai", "httpx", "sqlalchemy"):
        digest.update(f"{dependency}:{version(dependency)}".encode())
    package = Path(__file__).resolve().parents[1]
    sources = [
        Path("data/test_dataset.xlsx"),
        *sorted(Path("config/templates").glob("*.yaml")),
        *sorted((package / "application/evaluation").glob("*.py")),
        *sorted((package / "application/reporting").glob("*.py")),
        *sorted((package / "domain").glob("*.py")),
        *sorted((package / "infrastructure/pyrit").rglob("*.py")),
        *sorted(
            (package / "infrastructure/pyrit/scoring/rubrics").glob("*.yaml")
        ),
        *sorted((package / "infrastructure/dataset").glob("*.py")),
        package / "infrastructure/settings.py",
        package / "infrastructure/http/endpoint_policy.py",
    ]
    for source in sources:
        name = (
            source.relative_to(package)
            if source.is_relative_to(package)
            else source
        )
        digest.update(name.as_posix().encode("utf-8"))
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()
