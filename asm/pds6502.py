"""Load the shared PDS 1.26 assembler.

There is no separate ``pdsasm`` program. The assembler is
https://github.com/ap0ught/pds6502, and this file is the loader its README
documents: import ``pds6502.py`` from ``$PDS6502_HOME`` or from a sibling
checkout. The game build calls ``Assembler``; it does not reimplement PDS.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _locate() -> Path:
    env = os.environ.get("PDS6502_HOME")
    if env:
        path = Path(env) / "pds6502.py"
        if path.is_file():
            return path
        raise SystemExit(f"PDS6502_HOME does not contain pds6502.py: {env}")
    sibling = Path(__file__).resolve().parents[2] / "pds6502" / "pds6502.py"
    if sibling.is_file():
        return sibling
    raise SystemExit(
        "pds6502 assembler not found. Clone https://github.com/ap0ught/pds6502 "
        "next to this repo (../pds6502) or set PDS6502_HOME. "
        "There is no pdsasm repository; pds6502 is the assembler."
    )


_path = _locate()
_spec = importlib.util.spec_from_file_location("_pds6502_impl", _path)
if _spec is None or _spec.loader is None:
    raise SystemExit(f"cannot load {_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_pds6502_impl"] = _mod
_spec.loader.exec_module(_mod)

ASSEMBLER_FILE = str(_path)
for _name, _value in vars(_mod).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value
