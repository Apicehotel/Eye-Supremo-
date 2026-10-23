"""Import local Eye Supremo archives into private Supabase Storage.

Requires py7zr and secure server-side SUPABASE_URL /
SUPABASE_SERVICE_ROLE_KEY environment variables.
"""
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SOURCES = [
    ("tutte.7z", "eye-invoices", "fatture", {".xml", ".p7m"}),
    ("Recensioni Hotel Gio.7z", "eye-reviews", "Gio", {".msg"}),
    ("Recensioni Choco.7z", "eye-reviews", "Choco", {".msg"}),
]

def safe_path(name):
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts or ":" in p.parts[0]:
        raise ValueError("Unsafe archive member")
    return p

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def upload(source, bucket, key):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    if not base.startswith("https://") or ".supabase.co" not in base:
        raise RuntimeError("Invalid Supabase URL")
    url = base + "/storage/v1/object/" + bucket + "/" + quote(key, safe="/")
    req = Request(url, data=source.read_bytes(), method="POST", headers={
        "apikey": token, "Authorization": "Bearer " + token,
        "Content-Type": "application/xml" if source.suffix.lower() == ".xml" else "application/octet-stream",
        "x-upsert": "false",
    })
    try:
        with urlopen(req, timeout=180) as response:
            return "uploaded" if response.status in (200, 201) else "error"
    except HTTPError as exc:
        if exc.code == 409:
            return "exists"
        raise

def run(input_dir, checkpoint):
    import py7zr
    db = sqlite3.connect(checkpoint)
    db.execute("CREATE TABLE IF NOT EXISTS completed (bucket TEXT, digest TEXT, PRIMARY KEY (bucket,digest))")
    totals = {}
    for archive_name, bucket, folder, accepted in SOURCES:
        archive = Path(input_dir) / archive_name
        if not archive.is_file():
            raise FileNotFoundError(str(archive))
        counters = {"uploaded": 0, "exists": 0, "duplicate": 0}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with py7zr.SevenZipFile(archive, "r") as z:
                members = z.getnames()
                for member in members:
                    safe_path(member)
                z.extractall(path=root)
            for member in members:
                if member.endswith("/"):
                    continue
                path = root.joinpath(*safe_path(member).parts)
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Unsafe extracted object")
                if path.suffix.lower() not in accepted:
                    continue
                if bucket == "eye-invoices" and path.stat().st_size > 30 * 1024 * 1024:
                    raise ValueError("Invoice exceeds bucket file limit")
                digest = sha256(path)
                if db.execute("SELECT 1 FROM completed WHERE bucket=? AND digest=?", (bucket, digest)).fetchone():
                    counters["duplicate"] += 1
                    continue
                key = folder + "/" + digest[:2] + "/" + digest + path.suffix.lower()
                status = upload(path, bucket, key)
                counters[status] += 1
                db.execute("INSERT OR IGNORE INTO completed VALUES (?,?)", (bucket, digest))
                db.commit()
        totals[archive_name] = counters
    db.close()
    return totals

if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--checkpoint", default="eye-import-checkpoint.sqlite")
    args = parser.parse_args()
    print(json.dumps(run(args.input_dir, args.checkpoint), indent=2))
