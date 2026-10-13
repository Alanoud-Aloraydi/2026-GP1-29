"""Shared test fixtures."""

import os

# OpenBLAS reserves a buffer per thread when numpy loads; PyRIT imports numpy without doing
# matrix work, and a single thread avoids allocation failures on memory-constrained machines.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import pytest
from pyrit.setup import IN_MEMORY, initialize_pyrit_async


@pytest.fixture
async def pyrit_memory() -> None:
    """Initialize PyRIT with a fresh in-memory database, which PyRIT targets require."""
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)
