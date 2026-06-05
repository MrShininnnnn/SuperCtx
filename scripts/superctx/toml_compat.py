"""TOML loading with a source-runtime fallback for plugin execution.

SuperCtx skills execute the package directly from ``scripts/`` via
``PYTHONPATH``. In that mode Python 3.9/3.10 may not have installed package
dependencies, so falling back from stdlib ``tomllib`` to external ``tomli`` is
not enough. The final fallback below intentionally supports only the small TOML
subset SuperCtx writes and ships: tables, arrays of tables, strings, booleans,
and arrays of strings.
"""

from __future__ import annotations

import ast
from typing import BinaryIO

try:
    import tomllib as _toml
except ModuleNotFoundError:
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:
        _toml = None


def load(fp: BinaryIO) -> dict:
    if _toml is not None:
        return _toml.load(fp)

    raw = fp.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = raw
    return _load_minimal(text)


def _load_minimal(text: str) -> dict:
    data: dict = {}
    current: dict = data

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line).strip()
        if not line:
            continue

        if line.startswith("[[") and line.endswith("]]"):
            table_name = line[2:-2].strip()
            if not table_name:
                raise ValueError(f"Invalid TOML array table on line {line_no}")
            table = data.setdefault(table_name, [])
            if not isinstance(table, list):
                raise ValueError(f"Table {table_name!r} is not an array on line {line_no}")
            current = {}
            table.append(current)
            continue

        if line.startswith("[") and line.endswith("]"):
            table_name = line[1:-1].strip()
            if not table_name:
                raise ValueError(f"Invalid TOML table on line {line_no}")
            table = data.setdefault(table_name, {})
            if not isinstance(table, dict):
                raise ValueError(f"Table {table_name!r} is not a table on line {line_no}")
            current = table
            continue

        if "=" not in line:
            raise ValueError(f"Invalid TOML assignment on line {line_no}")

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Missing TOML key on line {line_no}")
        current[key] = _parse_value(raw_value.strip(), line_no)

    return data


def _strip_comment(line: str) -> str:
    in_string = False
    escaped = False
    for idx, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:idx]
    return line


def _parse_value(value: str, line_no: int):
    if value in {"true", "false"}:
        return value == "true"

    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Unsupported TOML value on line {line_no}: {value}") from exc

    if isinstance(parsed, (str, list)):
        return parsed
    raise ValueError(f"Unsupported TOML value on line {line_no}: {value}")
