"""Download raw datasets into data/raw/.

Usage:
    python -m hpf.download            # all downloadable datasets
    python -m hpf.download ll87 pluto # only some

Datasets with no URL in config (for example boiler_permits, produced by the team)
are skipped: copy those files into data/raw/ by hand.
"""
import sys

import requests

from hpf import config


def download(key: str) -> None:
    spec = config.DATASETS[key]
    out = config.RAW / spec["file"]
    if not spec.get("url"):
        print(f"Skipping {key}: no download URL. Copy {spec['file']} into {config.RAW} by hand.")
        return
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
