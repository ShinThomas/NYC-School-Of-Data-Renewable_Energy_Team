"""Small helpers shared by the loaders."""
import re

import numpy as np
import pandas as pd


def norm(name: str) -> str:
    """'Natural Gas Use (kBtu)' -> 'natural_gas_use_kbtu'."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [norm(c) for c in df.columns]
    return df


def pick(df: pd.DataFrame, mapping: dict, dataset: str, required=()) -> pd.DataFrame:
    """Rename columns to our short keys using the candidate lists in config.

    Missing optional columns are created as NaN. Missing required columns raise
    an error that says which names were tried.
    """
    out = pd.DataFrame(index=df.index)
    for key, candidates in mapping.items():
        found = next((c for c in candidates if c in df.columns), None)
        if found is None:
            if key in required:
                raise KeyError(
                    f"[{dataset}] none of {candidates} found for '{key}'. "
                    f"Run `python -m hpf.inspect {dataset}` and fix hpf/config.py."
                )
            out[key] = np.nan
        else:
            out[key] = df[found]
    return out


def to_num(s: pd.Series) -> pd.Series:
    """Numbers stored as text ('Not Available', '1,234') -> float."""
    if s.dtype.kind in "if":
        return s.astype(float)
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")


def clean_bbl(s: pd.Series) -> pd.Series:
    """Return a 10-digit BBL string (borough 1 + block 5 + lot 4), or NaN.

    Handles '1012340056', 1012340056.0, '1-01234-0056', and LL84 lists like
    '1012340056;1012340057' (first one is kept).
    """
    def one(x):
        if pd.isna(x):
            return np.nan
        x = str(x).split(";")[0].split(",")[0].strip()
        if "-" in x:
            parts = x.split("-")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                return np.nan
            b, blk, lot = parts
            return f"{int(b)}{int(blk):05d}{int(lot):04d}"
        x = x.split(".")[0]
        if x.isdigit() and len(x) == 10 and x[0] in "12345":
            return x
        return np.nan

    return s.map(one)


def clean_bin(s: pd.Series) -> pd.Series:
    """Return a 7-digit BIN string, or NaN. LL84 lists like '1000003;1000004' keep the first."""
    def one(x):
        if pd.isna(x):
            return np.nan
        x = str(x).split(";")[0].split(",")[0].strip().split(".")[0]
        if x.isdigit() and len(x) == 7 and x[0] in "12345" and not x.endswith("000000"):
            return x
        return np.nan

    return s.map(one)
