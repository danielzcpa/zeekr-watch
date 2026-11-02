"""Monthly deliveries (VFACTS + EVC) from the CarExpert New Car Sales Atlas latest-dataset page.
Writes docs/data/sales_history.json:
  {months: {"2026-09": {label, fetched, source, models: {"Make|Model": {units, yoy, ytd}}, makes: {...}, buyer_type: {...}, fuel_mix: {...}, segments: {...}, total}}, updated, latest}
A month is (re)written whenever the page shows it; earlier months are kept."""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime

from .benchmark import _get, _st
from .util import DATA_DIR, config, load_json, save_json, now_iso

URL = "https://atlas.carexpert.com.au/latest-dataset"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def _num(s):
    s = (s or "").replace(",", "").replace("−", "-").strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def _pct(s):
    s = (s or "").replace("−", "-").replace("%", "").strip()
    if s in ("", "—", "-", "flat"):
        return 0.0 if s == "flat" else None
    try:
        return float(s)
    except ValueError:
        return None


def _cells(row_html):
    return [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.S)]


def _section_tables(html):
    """Return list of (heading, [rows]) for each table preceded by an h2/h3 heading."""
    out = []
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>(.*?)(?=<h[23]|\Z)", html, flags=re.S):
        head = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(2), flags=re.S)]
        if rows:
            out.append((head, rows))
    return out


KEYS = {
    "buyer_type": ["Private", "S.Fleet", "Demo", "L.Fleet", "Rental", "Govt. + NFP", "Company", "Business", "Government"],
    "fuel_mix": ["Electric", "Petrol", "Diesel", "Hybrid", "PHEV", "MHEV", "Hydrogen"],
    "category": ["SUV", "Light Commercial", "Passenger", "Heavy Commercial"],
}


def _kv_pairs(text, keys):
    """Parse 'Private 55,986 53.1% S.Fleet 15,217 14.4% ...' into {name: {units, share}} for the given keys only."""
    out = {}
    for k in keys:
        m = re.search(re.escape(k) + r"\s+([\d,]+)\s+([\d.]+)%", text)
        if m:
            out[k] = {"units": _num(m.group(1)), "share": float(m.group(2))}
    return out


def parse(html):
    m = re.search(r"Make and model ranking: ([A-Z][a-z]+) (\d{4})", html)
    if not m:
        raise ValueError("month heading not found")
    month = f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    rec = {"label": f"{m.group(1)} {m.group(2)}", "fetched": now_iso(), "source": URL, "models": {}, "makes": {}, "buyer_type": {}, "fuel_mix": {}, "segments": {}, "category": {}, "total": None}
    for head, rows in _section_tables(html):
        if head.startswith("Make and model ranking"):
            for r in rows:
                if len(r) >= 6 and r[0].isdigit():
                    rec["models"][f"{r[1]}|{r[2]}"] = {"make": r[1], "model": r[2], "units": _num(r[3]), "yoy": _pct(r[4]), "ytd": _num(r[5])}
        elif head.startswith("Make ranking"):
            for r in rows:
                if len(r) >= 6 and r[0].isdigit():
                    rec["makes"][r[1]] = {"units": _num(r[2]), "yoy": _pct(r[3]), "share": _pct(r[4]), "ytd": _num(r[5])}
        elif head.startswith("Top segments"):
            for r in rows:
                r = [c for c in r if c != ""]
                if len(r) >= 4 and r[0].isdigit():
                    rec["segments"][r[1]] = {"units": _num(r[2]), "share": _pct(r[3])}
    for key, head in (("buyer_type", "Buyer type:"), ("fuel_mix", "Fuel mix:"), ("category", "Market category:")):
        i = html.find(head)
        if i >= 0:
            seg = re.sub(r"<script.*?</script>", "", html[i:i + 6000], flags=re.S)
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", seg))
            rec[key] = _kv_pairs(txt, KEYS[key])
    t = re.search(r"Share of ([\d,]+) sales across Australian states", html)
    rec["total"] = _num(t.group(1)) if t else sum(v["units"] or 0 for v in rec["makes"].values())
    return month, rec


def run():
    path = DATA_DIR / "sales_history.json"
    store = load_json(path, {"months": {}, "updated": None, "latest": None})
    r, err = _get(URL, timeout=40)
    if r is None:
        return store, {"sales-atlas": _st(False, 0, err or "")}, 0
    try:
        month, rec = parse(r.text)
    except Exception as ex:  # noqa: BLE001
        return store, {"sales-atlas": _st(False, 0, f"parse: {str(ex)[:100]}")}, 0
    if not rec["models"]:
        return store, {"sales-atlas": _st(False, 0, "no model rows")}, 0
    new = month not in store["months"]
    store["months"][month] = rec
    store["latest"] = max(store["months"])
    store["updated"] = now_iso()
    save_json(path, store)
    note = f"{rec['label']}: {len(rec['models'])} models, total {rec['total']}" + (" (new month)" if new else "")
    return store, {"sales-atlas": _st(True, len(rec["models"]), note + (" via mirror" if getattr(r, "via_mirror", False) else ""))}, int(new)


# --------------------------------------------------------------- The Driven: BEV deliveries by model by month (whole year on one page)
MON3 = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def driven_ev_monthly():
    """docs/data/ev_monthly.json: {year, models: {name: {"2026-01": units, ...}}, brands: {...}, source, updated}"""
    smap = config("sales_map.json")
    url = smap.get("driven_url")
    path = DATA_DIR / "ev_monthly.json"
    store = load_json(path, {"models": {}, "brands": {}, "updated": None})
    r, err = _get(url, timeout=60)
    if r is None:
        return store, {"sales-thedriven": _st(False, 0, err or "")}
    tables = re.findall(r"<table[^>]*>(.*?)</table>", r.text, flags=re.S)
    if len(tables) < 2:
        return store, {"sales-thedriven": _st(False, 0, "tables not found")}
    ym = re.search(r"sales by month in (\d{4})", r.text)
    year = ym.group(1) if ym else str(datetime.utcnow().year)

    def table(tb):
        rows = [_cells(rr) for rr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, flags=re.S)]
        head = rows[0]
        cols = {i: f"{year}-{MON3[h]:02d}" for i, h in enumerate(head) if h in MON3}
        out = {}
        for rr in rows[1:]:
            if not rr or not rr[0]:
                continue
            out[rr[0]] = {cols[i]: _num(rr[i]) for i in cols if i < len(rr) and _num(rr[i]) is not None}
        return out

    models, brands = table(tables[0]), table(tables[1])
    if not models:
        return store, {"sales-thedriven": _st(False, 0, "no rows")}
    store.update({"year": year, "models": models, "brands": brands, "source": url, "updated": now_iso()})
    save_json(path, store)
    months = sorted({m for v in models.values() for m in v})
    return store, {"sales-thedriven": _st(True, len(models), f"{len(models)} BEV models, {months[0]}..{months[-1]}" + (" via mirror" if getattr(r, "via_mirror", False) else ""))}


def run_all():
    statuses = {}
    out = {}
    try:
        store, st, n = run()
        statuses.update(st)
        out["sales"] = store
    except Exception as ex:  # noqa: BLE001
        statuses["sales-atlas"] = _st(False, 0, f"crashed: {str(ex)[:120]}")
    try:
        store, st = driven_ev_monthly()
        statuses.update(st)
        out["ev"] = store
    except Exception as ex:  # noqa: BLE001
        statuses["sales-thedriven"] = _st(False, 0, f"crashed: {str(ex)[:120]}")
    return out, statuses
