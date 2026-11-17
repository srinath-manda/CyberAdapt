"""Shim — re-exports CyberAdapt crypto classes from CyberAdapt_v1/cyberadapt_crypto.py"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]  # e:\final_proj_implementation
_v1_path = str(_repo_root / "CyberAdapt_v1")

if _v1_path not in sys.path:
    sys.path.insert(0, _v1_path)

from cyberadapt_crypto import (  # noqa: E402
    ZKTAT,
    HPO,
    RevocationBloomFilter,
    SMBP_TABLE_G,
    SMBP_TABLE_H,
    scalar_mult_baseline,
    ORDER,
)

__all__ = [
    "ZKTAT",
    "HPO",
    "RevocationBloomFilter",
    "SMBP_TABLE_G",
    "SMBP_TABLE_H",
    "scalar_mult_baseline",
    "ORDER",
]
