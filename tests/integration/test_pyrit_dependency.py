"""Tests for pyrit dependency."""

import importlib

import pytest

REQUIRED_PYRIT_VERSION = "1.1.0"

REQUIRED_PYRIT_EXPORTS: dict[str, tuple[str, ...]] = {
    "pyrit.models": ("SeedPrompt", "Message", "MessagePiece", "Score"),
    "pyrit.executor.attack": (
        "PromptSendingAttack",
        "AttackScoringConfig",
    ),
    "pyrit.prompt_target": ("OpenAIChatTarget",),
    "pyrit.score": (
        "SelfAskTrueFalseScorer",
        "SelfAskCategoryScorer",
        "TrueFalseQuestion",
    ),
    "pyrit.memory": ("CentralMemory",),
    "pyrit.setup": ("initialize_pyrit_async", "IN_MEMORY", "SQLITE"),
}


def test_installed_pyrit_version_matches_pinned_version() -> None:
    """The adapters are written against one exact PyRIT release."""
    pyrit = importlib.import_module("pyrit")

    assert pyrit.__version__ == REQUIRED_PYRIT_VERSION


@pytest.mark.parametrize("module_name", sorted(REQUIRED_PYRIT_EXPORTS))
def test_required_pyrit_exports_are_available(module_name: str) -> None:
    """Each PyRIT module exposes the names the adapters import."""
    module = importlib.import_module(module_name)

    missing_names = [
        name
        for name in REQUIRED_PYRIT_EXPORTS[module_name]
        if not hasattr(module, name)
    ]

    assert missing_names == []


async def test_pyrit_memory_initializes_without_network() -> None:
    """PyRIT initializes its central memory in-process."""
    setup = importlib.import_module("pyrit.setup")
    memory_module = importlib.import_module("pyrit.memory")

    await setup.initialize_pyrit_async(
        memory_db_type=setup.IN_MEMORY, silent=True
    )

    assert memory_module.CentralMemory.get_memory_instance() is not None
