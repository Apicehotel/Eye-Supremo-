"""Publish a verified Windows installer to the private Supabase S3 bucket."""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

BUCKET = "eye-updates"
MAX_VERSIONS = 5
MAX_BYTES = 15 * 1024**3
PROJECT = "ooqlfldcrnkudhgjnied"


def publish(installer: Path) -> None:
    match = re.fullmatch(r"EyeSupremo-Setup-(\d+\.\d+\.\d+)\.exe", installer.name)
    if not match:
        raise ValueError("Expected EyeSupremo-Setup-X.Y.Z.exe")
    if not installer.is_file() or installer.stat().st_size < 1024 * 1024:
        raise ValueError("Installer missing or unexpectedly small")
    version = match.group(1)
    with installer.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError("Not a Windows executable")
    sha = hashlib.sha256()
    with installer.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{PROJECT}.storage.supabase.co/storage/v1/s3",
        region_name="eu-central-1",
        aws_access_key_id=os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"],
    )
    existing = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET):
        for entry in page.get("Contents", []):
            if re.fullmatch(r"EyeSupremo-Setup-\d+\.\d+\.\d+\.exe", entry["Key"]):
                existing.append(entry)
    prior = next((x for x in existing if x["Key"] == installer.name), None)
    total = sum(x["Size"] for x in existing) - (prior["Size"] if prior else 0) + installer.stat().st_size
    if total > MAX_BYTES:
        raise RuntimeError("Quota aggiornamenti 15 GiB exceeded; refusing to publish")
    client.upload_file(
        str(installer), BUCKET, installer.name,
        ExtraArgs={"ContentType": "application/octet-stream", "Metadata": {"sha256": sha.hexdigest()}},
    )
    remote = client.head_object(Bucket=BUCKET, Key=installer.name)
    if remote["ContentLength"] != installer.stat().st_size or remote.get("Metadata", {}).get("sha256") != sha.hexdigest():
        raise RuntimeError("Remote installer verification failed; latest.json not updated")
    manifest = {
        "version": version, "filename": installer.name, "sha256": sha.hexdigest(),
        "size": installer.stat().st_size,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    client.put_object(
        Bucket=BUCKET, Key="latest.json",
        Body=json.dumps(manifest).encode("utf-8"), ContentType="application/json",
    )
    confirmed = json.loads(client.get_object(Bucket=BUCKET, Key="latest.json")["Body"].read())
    if confirmed != manifest:
        raise RuntimeError("Remote manifest verification failed")
    # Only prune after the new binary and manifest have been verified.
    all_versions = [x for x in existing if x["Key"] != installer.name]
    all_versions.append({"Key": installer.name, "LastModified": datetime.now(timezone.utc)})
    all_versions.sort(key=lambda x: x["LastModified"], reverse=True)
    for old in all_versions[MAX_VERSIONS:]:
        client.delete_object(Bucket=BUCKET, Key=old["Key"])
    print(f"Verified publication of {installer.name}, sha256={sha.hexdigest()}; retained at most {MAX_VERSIONS} installers")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: publish_eye_update.py PATH_TO_EXE")
    publish(Path(sys.argv[1]))
