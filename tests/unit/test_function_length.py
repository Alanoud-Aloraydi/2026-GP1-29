"""Keep every function short enough to read in one screen."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_LINES = 79


def test_no_function_exceeds_the_line_limit() -> None:
    """Functions in the code and tests stay within the limit; migrations are history."""
    long_functions = [
        f"{path.relative_to(ROOT)}:{node.lineno} {node.name} ({node.end_lineno - node.lineno + 1})"
        for folder in ("src", "tests")
        for path in (ROOT / folder).rglob("*.py")
        if "migrations" not in path.parts
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.end_lineno is not None
        and node.end_lineno - node.lineno + 1 > MAX_LINES
    ]
    assert long_functions == []
