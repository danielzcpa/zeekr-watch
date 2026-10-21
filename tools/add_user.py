#!/usr/bin/env python3
"""Add or update a login for the site. Usage: python3 tools/add_user.py <username> <password> [display name]
Then commit docs/auth.json. To remove a user, delete the entry from docs/auth.json."""
import hashlib, json, sys, pathlib
if len(sys.argv) < 3:
    sys.exit(__doc__)
u, pw = sys.argv[1].strip().lower(), sys.argv[2]
name = sys.argv[3] if len(sys.argv) > 3 else sys.argv[1]
p = pathlib.Path(__file__).resolve().parent.parent / "docs" / "auth.json"
d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"users": []}
h = hashlib.sha256(f"{u}:{pw}".encode()).hexdigest()
d["users"] = [x for x in d["users"] if x["u"] != u] + [{"u": u, "name": name, "h": h}]
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"ok: {u} ({name}) -> {len(d['users'])} users in {p}")
