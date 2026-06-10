"""Cobertura de docstrings (ISO/IEC 25010 — Mantenibilidad).

Via AST sobre src/pacusam/*.py: el ratio global de funciones/metodos con
docstring debe ser >= 0.80. Evidencia objetiva de codigo autodocumentado.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "pacusam"


def test_cobertura_de_docstrings_global_supera_80():
    total_funcs = total_doc = 0
    for p in SRC.glob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        funcs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        total_funcs += len(funcs)
        total_doc += sum(1 for f in funcs if ast.get_docstring(f))
    assert total_funcs and (total_doc / total_funcs) >= 0.80
