"""Fetch the E3 result databases (runs/e3/lane0..lane4.sqlite) from the GitHub release, verify
them against SHA256SUMS.txt and decompress them in place. Lanes already present with the right
hash are skipped. Needs Python 3.14 (compression.zstd) and, without --from-dir, a logged-in
GitHub CLI (gh auth login) with access to the private repository.

usage: python scripts/fetch_e3_data.py [--force] [--from-dir DIR]
  --from-dir DIR  use laneN.sqlite.zst and SHA256SUMS.txt already downloaded into DIR
  --force         re-fetch lanes even when the local file matches
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from compression import zstd
from pathlib import Path

REPO = "alexandre-zatti/postgis-consistency-testing"
TAG = "e3-data-v1"
FILES = [f"lane{i}.sqlite" for i in range(5)]
DEST = Path(__file__).resolve().parents[1] / "runs" / "e3"
CHUNK = 1 << 20


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def gh_download(pattern, out):
    r = subprocess.run(["gh", "release", "download", TAG, "--repo", REPO, "--pattern", pattern,
                        "--dir", str(out), "--clobber"], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"gh release download {pattern} failed: {r.stderr.strip()}")
    return out / pattern


def check_gh():
    if not shutil.which("gh"):
        sys.exit("GitHub CLI (gh) not found. Install it and run 'gh auth login', or download the "
                 f"release assets of {TAG} from https://github.com/{REPO}/releases in the browser "
                 "and run this script with --from-dir DIR.")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        sys.exit("gh is not logged in. Run 'gh auth login', or download the release assets in "
                 "the browser and use --from-dir DIR.")


def unpack(zst, want, out):
    part = out.with_name(out.name + ".part")
    h = hashlib.sha256()
    dec = zstd.ZstdDecompressor()
    with open(zst, "rb") as f, open(part, "wb") as o:
        while b := f.read(CHUNK):
            d = dec.decompress(b)
            h.update(d)
            o.write(d)
    if not dec.eof or h.hexdigest() != want:
        part.unlink()
        sys.exit(f"{out.name}: decompressed hash mismatch")
    part.replace(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from-dir", type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if args.from_dir:
            sums_file = args.from_dir / "SHA256SUMS.txt"
        else:
            check_gh()
            sums_file = gh_download("SHA256SUMS.txt", tmp)
        sums = {}
        for line in sums_file.read_text().splitlines():
            if line.strip():
                h, name = line.split(maxsplit=1)
                sums[name.lstrip("*")] = h
        for name in FILES:
            out = DEST / name
            if out.exists() and not args.force and sha256(out) == sums[name]:
                print(f"{name}: present, hash ok")
                continue
            zst = (args.from_dir / f"{name}.zst" if args.from_dir
                   else gh_download(f"{name}.zst", tmp))
            if sha256(zst) != sums[f"{name}.zst"]:
                sys.exit(f"{zst.name}: hash mismatch, download again")
            unpack(zst, sums[name], out)
            if not args.from_dir:
                zst.unlink()
            print(f"{name}: fetched, hash ok ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
