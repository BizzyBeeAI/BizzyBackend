import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("sales.csv", "products.csv", "inventory.csv", "inventory_history.csv", "invoices.csv", "customer_feedback.csv", "customer_enquiries.csv", "returns.csv", "refunds.csv", "scenario_expectations.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    expected = (ROOT / "docker/BIZZY_DATA_REF").read_text().strip()
    if expected != f"BizzyBeeAI/BizzyData@{revision}":
        raise RuntimeError("Source does not match BIZZY_DATA_REF.")
    if subprocess.check_output(["git", "-C", str(args.source), "status", "--porcelain", "--", "data/demo"], text=True):
        raise RuntimeError("Source data has uncommitted changes.")
    contents = {name: (args.source / "data/demo" / name).read_bytes() for name in sorted(FILES)}
    archive_path = ROOT / "docker/bizzydata-demo.tar.gz"
    with archive_path.open("wb") as output, gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, content in contents.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                entry.mode = 0o644
                archive.addfile(entry, io.BytesIO(content))
    manifest = {"source": expected, "as_of": "2026-09-23", "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}}
    (ROOT / "docker/data-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
