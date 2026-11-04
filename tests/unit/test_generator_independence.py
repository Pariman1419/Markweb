import ast
import inspect
from pathlib import Path

from mark_engine.generate.generator import generate_expected


def test_signature_has_no_oracle():
    sig = inspect.signature(generate_expected)
    for param_name, param in sig.parameters.items():
        assert param_name != "oracle", f"Parameter {param_name} looks like oracle"
        if param.annotation != inspect.Parameter.empty:
            ann_str = str(param.annotation)
            assert "OracleMark" not in ann_str, f"Parameter {param_name} has OracleMark annotation"


def test_ast_has_no_oracle_references():
    generator_path = Path(__file__).resolve().parents[2] / "mark_engine" / "generate" / "generator.py"
    assert generator_path.is_file(), f"File not found: {generator_path}"

    with generator_path.open("r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename=str(generator_path))

    forbidden = {"oraclemark", "top_mark", "back_mark"}

    for node in ast.walk(tree):
        # Check Name nodes
        if isinstance(node, ast.Name):
            for forb in forbidden:
                assert forb not in node.id.lower(), f"Forbidden name {node.id!r} found at line {node.lineno}"

        # Check Constant/Str nodes
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for forb in forbidden:
                assert forb not in node.value.lower(), f"Forbidden string constant {node.value!r} found at line {node.lineno}"

        # Check Attribute nodes
        elif isinstance(node, ast.Attribute):
            for forb in forbidden:
                assert forb not in node.attr.lower(), f"Forbidden attribute {node.attr!r} found at line {node.lineno}"

        # Check function parameter args
        elif isinstance(node, ast.arg):
            for forb in forbidden:
                assert forb not in node.arg.lower(), f"Forbidden argument {node.arg!r} found at line {node.lineno}"

        # Check imports
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "adapters.snapshot" not in mod, f"Forbidden import from adapters.snapshot at line {node.lineno}"
            assert "adapters" not in mod, f"Forbidden import from adapters at line {node.lineno}"
            for alias in node.names:
                for forb in forbidden:
                    assert forb not in alias.name.lower(), f"Forbidden imported name {alias.name!r} at line {node.lineno}"

        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "adapters" not in alias.name, f"Forbidden import of adapters at line {node.lineno}"
                for forb in forbidden:
                    assert forb not in alias.name.lower(), f"Forbidden imported module {alias.name!r} at line {node.lineno}"
