"""Import a large invoice ZIP into Eye Supremo's central Supabase gateway."""
import hashlib, json, sys, tempfile, zipfile
from pathlib import Path
import httpx
from app.importers import parse_document

URL = "https://ooqlfldcrnkudhgjnied.supabase.co/functions/v1/eye-central-gateway"
KEY = "sb_publishable_Oiu7IOhuUd6YPEDmmSa7zA_ngNuiSlX"

def main(zip_path: str, shard: int = 0, shard_count: int = 1):
    batch = []
    sent = 0
    errors = 0
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith((".xml", ".txt")) and not n.endswith("/")]
        names = names[shard::shard_count]
        with httpx.Client(timeout=120) as client, tempfile.TemporaryDirectory(prefix="eye-import-") as temp:
            for index, name in enumerate(names, 1):
                raw = archive.read(name)
                path = Path(temp) / (f"{index}.xml")
                path.write_bytes(raw)
                try:
                    parsed = parse_document(path)
                    batch.append({"source_hash": hashlib.sha256(raw).hexdigest(), "source_filename": Path(name).name,
                                  "supplier": parsed["supplier"], "invoice": parsed["invoice"], "rows": parsed.get("rows", [])})
                except Exception as exc:
                    errors += 1
                    print(f"PARSE_ERROR {name}: {exc}", flush=True)
                if len(batch) >= 100 or index == len(names):
                    if batch:
                        response = client.post(URL, headers={"apikey": KEY, "Content-Type":"application/json"},
                            json={"action":"upsert_invoices","username":"supremo","pin":"000000","invoices":batch})
                        response.raise_for_status()
                        result=response.json(); sent += int(result.get("imported", 0)); errors += len(result.get("errors", [])); batch.clear()
                    print(f"PROGRESS {index}/{len(names)} imported={sent} errors={errors}", flush=True)
    print(json.dumps({"files":len(names),"imported":sent,"errors":errors}))

if __name__ == "__main__":
    if len(sys.argv) not in (2, 4): raise SystemExit("uso: python scripts/import_zip_supabase.py ZIP [shard shard_count]")
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 4 else 0, int(sys.argv[3]) if len(sys.argv) == 4 else 1)
