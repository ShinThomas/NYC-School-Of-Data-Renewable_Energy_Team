"""Print each raw file's normalized column names and check them against config.

Usage:
    python -m hpf.inspect            # all datasets
    python -m hpf.inspect ll84_annual

Fix any 'MISSING' key by adding the right name to its list in hpf/config.py.
"""
import sys

import pandas as pd

from hpf import config
from hpf.utils import norm


def inspect(key: str) -> None:
    path = config.RAW / config.DATASETS[key]["file"]
    print(f"\n=== {key}  ({path.name})")
    if not path.exists():
        print("  file not found. Run: python -m hpf.download", key)
        return
    cols = [norm(c) for c in pd.read_csv(path, nrows=0).columns]
    print(f"  {len(cols)} columns")
    for key_name, candidates in config.COLS[key].items():
        hit = next((c for c in candidates if c in cols), None)
        print(f"  {'ok     ' if hit else 'MISSING'} {key_name:<16} -> {hit or candidates}")
    words = ["gas", "elec", "bbl", "bin", "use_type", "year", "month", "gfa", "plant", "eff",
             "nta", "units", "permit"]
    print("  columns that may be relevant:")
    for c in cols:
        if any(w in c for w in words):
            print("    ", c)


if __name__ == "__main__":
    for k in sys.argv[1:] or list(config.DATASETS):
        inspect(k)
