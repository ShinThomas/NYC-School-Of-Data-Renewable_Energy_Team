"""Download raw datasets into data/raw/.

Usage:
    python -m hpf.download            # all datasets
    python -m hpf.download ll87 pluto # only some
"""
import sys

import requests

from hpf import config


def download(key: str) -> None:
    spec = config.DATASETS[key]
    out = config.RAW / spec["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {key}: {spec['about']}")
    with requests.get(spec["url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        size = 0
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                size += len(chunk)
                print(f"\r  {size / 1e6:,.0f} MB", end="")
    print(f"\n  saved to {out}")


if __name__ == "__main__":
    keys = sys.argv[1:] or list(config.DATASETS)
    for k in keys:
        download(k)
