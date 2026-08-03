"""Static release checks for the repository's Jupyter notebooks.

The benchmark itself needs Colab, a GPU, and external data, so CI does not
execute it. These checks still catch malformed notebook JSON, missing cell IDs,
committed outputs, and ordinary Python syntax errors in code cells.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted(ROOT.glob("*.ipynb"))
CELL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _source_text(cell: Dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(line, str) for line in source):
        return "".join(source)
    raise ValueError("cell source must be a string or a list of strings")


def _python_for_static_compile(source: str) -> str:
    """Replace Colab/IPython line commands while preserving Python lines."""
    transformed: List[str] = []
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("%%"):
            raise ValueError("cell magics are not supported by the static validator")
        if stripped.startswith(("%", "!")):
            indentation = line[: len(line) - len(stripped)]
            newline = "\n" if line.endswith("\n") else ""
            transformed.append(f"{indentation}pass{newline}")
        else:
            transformed.append(line)
    return "".join(transformed)


def validate_notebook(path: Path) -> List[str]:
    errors: List[str] = []
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot read valid UTF-8 notebook JSON: {exc}"]

    if notebook.get("nbformat") != 4:
        errors.append(f"expected nbformat 4, got {notebook.get('nbformat')!r}")
    minor = notebook.get("nbformat_minor")
    if not isinstance(minor, int) or isinstance(minor, bool) or minor < 0:
        errors.append(f"expected a non-negative nbformat_minor, got {minor!r}")
    if not isinstance(notebook.get("metadata"), dict):
        errors.append("top-level metadata must be an object")

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return errors + ["top-level cells must be a list"]

    seen_ids = set()
    for index, cell in enumerate(cells):
        location = f"cell {index}"
        if not isinstance(cell, dict):
            errors.append(f"{location}: cell must be an object")
            continue

        cell_id = cell.get("id")
        ids_required = int(notebook.get("nbformat_minor", 0)) >= 5
        if cell_id is None and not ids_required:
            pass
        elif not isinstance(cell_id, str) or not CELL_ID_RE.fullmatch(cell_id):
            errors.append(f"{location}: missing or invalid nbformat 4.5 cell id")
        elif cell_id in seen_ids:
            errors.append(f"{location}: duplicate cell id {cell_id!r}")
        else:
            seen_ids.add(cell_id)

        cell_type = cell.get("cell_type")
        if cell_type not in {"code", "markdown", "raw"}:
            errors.append(f"{location}: unsupported cell_type {cell_type!r}")
            continue

        try:
            source = _source_text(cell)
        except ValueError as exc:
            errors.append(f"{location}: {exc}")
            continue

        if cell_type != "code":
            continue
        if cell.get("execution_count") is not None:
            errors.append(f"{location}: execution_count must be null in source control")
        outputs = cell.get("outputs")
        if outputs != []:
            errors.append(f"{location}: outputs must be an empty list in source control")
        try:
            compile(
                _python_for_static_compile(source),
                f"{path.name}:{index}",
                "exec",
            )
        except (SyntaxError, ValueError) as exc:
            errors.append(f"{location}: static Python validation failed: {exc}")

    return errors


def main(paths: Iterable[Path] = NOTEBOOKS) -> int:
    paths = list(paths)
    if not paths:
        print("No notebooks found.", file=sys.stderr)
        return 1

    failures = 0
    for path in paths:
        errors = validate_notebook(path)
        if errors:
            failures += 1
            print(f"FAIL {path.relative_to(ROOT)}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {path.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
