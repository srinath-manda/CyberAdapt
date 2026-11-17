"""Shim — re-exports CyberAdaptTrustController from CyberAdapt_v1/cyberadapt_control.py"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]  # e:\final_proj_implementation
_v1_path = _repo_root / "CyberAdapt_v1"

if str(_v1_path) not in sys.path:
    sys.path.insert(0, str(_v1_path))

from cyberadapt_control import CyberAdaptTrustController  # noqa: F401

__all__ = ["CyberAdaptTrustController"]
