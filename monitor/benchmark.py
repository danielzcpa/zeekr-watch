"""Benchmark monitoring: live drive-away prices (The Beep JSON-LD), official offer
feeds (The Beep offers pages, Zecar offers pages) and the 2026 policy timeline store.

Outputs (docs/data):
  dap_history.json   {models: {slug: {label, group, zeekr, cid, variants: {name: {NSW: [[date, price]...], VIC: [...]}}}}, updated}
  policy_events.json {events: [...], updated}   merged: baseline (config) + Beep + Zecar, de-duplicated
"""
from __future__ import annotations

import html as html_lib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .util import DATA_DIR, config, load_json, save_json, now_iso, sha, UA

BENCH = config("benchmark.json")
H = {"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"}


MIRROR = "https://r.jina.ai/"  # read-only HTML mirror; used only when the origin blocks datacenter IPs (403)
_mirror_lock = __import__("threading").Lock()


def _get(url, timeout=25, retries=1, mirror=True):
    err = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=H, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r, None
            err = f"HTTP {r.status_code}"
            if r.status_code in (429, 502, 503):
                time.sleep(4 * (i + 1))
                continue
            break
        except requests.RequestException as e:
            err = str(e)[:120]
            time.sleep(3)
    if mirror and err and (err.startswith("HTTP 403") or err.startswith("HTTP 503")):
        # Cloudflare blocks GitHub-hosted runners; fetch the same HTML through the mirror, serialised to respect its rate limit
        with _mirror_lock:
            for i in range(3):
                try:
                    r = requests.get(MIRROR + url, headers={**H, "X-Return-Format": "html"}, timeout=60)
                    if r.status_code == 200 and len(r.text) > 2000:
                        r.via_mirror = True
                        time.sleep(2.5)
                        return r, None
                    merr = f"mirror HTTP {r.status_code}"
                    if r.status_code == 429:
                        time.sleep(15 * (i + 1))
                        continue
                    break
                except requests.RequestException as e:
                    merr = "mirror " + str(e)[:80]
                    time.sleep(5)
            err = f"{err}; {merr}"
    return None, err


def _st(ok, count, note=""):
    return {"ok": bool(ok), "count": int(count), "note": note[:200]}


# --------------------------------------------------------------- The Beep: DAP per variant per state
def beep_prices():
    states = BENCH.get("states", ["NSW", "VIC"])
    path = DATA_DIR / "dap_history.json"
    store = load_json(path, {"models": {}, "updated": None})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    statuses = {}

    def work(m):
        url = f"https://thebeep.com.au/cars/{m['slug']}/"
        r, err = _get(url)
        if r is None:
            return m, None, err
        out = {}
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, flags=re.S):
            try:
                d = json.loads(blk)
            except json.JSONDecodeError:
                continue
            if not isinstance(d, dict) or not isinstance(d.get("offers"), dict):
                continue
            for o in d["offers"].get("offers", []):
                try:
                    st = o["areaServed"]["address"]["addressRegion"]
                    name = o["itemOffered"].get("vehicleConfiguration") or o["itemOffered"].get("name")
                    price = int(o["price"])
                except Exception:
                    continue
                if st in states:
                    out.setdefault(name, {})[st] = price
        return m, out, ("via mirror" if getattr(r, "via_mirror", False) else None)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(work, BENCH["beep_models"]))
    n_models = 0
    for m, out, err in results:
        key = m["slug"]
        rec = store["models"].setdefault(key, {"label": m["label"], "group": m["group"], "zeekr": m.get("zeekr"), "cid": m.get("cid"), "variants": {}})
        rec.update({"label": m["label"], "group": m["group"], "zeekr": m.get("zeekr"), "cid": m.get("cid")})
        if out is None:
            rec["last_error"] = err
            statuses["beep-" + key] = _st(False, 0, err or "")
            continue
        rec["last_error"] = None
        rec["via"] = "mirror" if err == "via mirror" else "direct"
        rec["checked"] = now_iso()
        for name, byst in out.items():
            v = rec["variants"].setdefault(name, {})
            for st, price in byst.items():
                series = v.setdefault(st, [])
                if series and series[-1][0] == today:
                    series[-1][1] = price
                elif not series or series[-1][1] != price:
                    series.append([today, price])
                v[st] = series[-600:]
        n_models += 1
        statuses["beep-" + key] = _st(True, len(out), err or "")
    store["updated"] = now_iso()
    save_json(path, store)
    return store, statuses, n_models


# --------------------------------------------------------------- offers feeds
def _clean(t):
    return html_lib.unescape(t or "").replace("\ufffd", "'").strip()


def _beep_offers(brand):
    url = f"https://thebeep.com.au/offers-and-deals/{brand}/"
    r, err = _get(url)
    if r is None:
        return None, err
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, flags=re.S)
    def _dec(c):
        try:
            return json.loads('"' + c + '"')
        except ValueError:
            try:
                return c.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "ignore")
            except (UnicodeDecodeError, UnicodeEncodeError):
                return c.encode().decode("unicode_escape", "ignore")
    blob = "".join(_dec(c) for c in chunks)
    events = []
    for m in re.finditer(r'\{"make":"(.*?)","makeCode":"(.*?)","offerTitle":"(.*?)","offerText_rephrased":"(.*?)","modelsText":"(.*?)","state":"(.*?)","fromDate":"(.*?)"(?:,"toDate":"(.*?)")?', blob):
        make, code, title, text, models, state, frm, to = m.groups()
        start = frm[:10]
        end = (to or "")[:10] or None
        events.append({
            "id": "beep:" + sha(code + title + start, 12), "source": "thebeep", "brand": code, "brand_name": make,
            "title": _clean(title), "detail": _clean(text)[:400], "models": _clean(models),
            "state": state or "national", "start": start, "end": end, "url": url,
        })
    return events, None


def _zecar_offers(brand):
    url = f"https://zecar.com/offers-and-deals/{brand}"
    r, err = _get(url)
    if r is None:
        return None, err
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, flags=re.S)
    if not m:
        return None, "no __NEXT_DATA__"
    try:
        d = json.loads(m.group(1))
        offers = d["props"]["pageProps"]["listing"]["offers"]
    except Exception as e:
        return None, f"parse: {str(e)[:60]}"
    events = []
    for o in offers:
        start = (o.get("published_time") or "")[:10]
        end = (o.get("expired_time") or "")[:10] or None
        slug = (o.get("slug") or {}).get("current") or ""
        events.append({
            "id": "zecar:" + (o.get("_id") or sha(o.get("title", ""), 12)), "source": "zecar", "brand": brand,
            "brand_name": o.get("model") or brand, "title": o.get("title") or "", "detail": (o.get("description") or "")[:400],
            "models": o.get("model") or "", "state": "national", "start": start, "end": end,
            "url": f"https://zecar.com/offers-and-deals/{slug}" if slug else url, "product": o.get("product"),
        })
    return events, None


EVENT_TYPES = [
    ("price_cut", r"price cut|price drop|slash|cheaper|cuts? price|lower(?:ed)? price|price reduc|reduced by \$|降价"),
    ("price_rise", r"price rise|price hike|price increase|more expensive|涨价"),
    ("cashback", r"cashback|cash back|bonus cash|\$[\d,]+ (?:off|bonus|saving)|save \$"),
    ("driveaway", r"drive-?away|driveaway"),
    ("finance_rate", r"\d(?:\.\d+)?% ?p\.?a|comparison rate|finance offer|loan|apr\b|interest"),
    ("novated", r"novated"),
    ("bonus", r"free |complimentary|wallbox|wall box|charger|servicing|service plan|trade-in bonus|trade in bonus|deposit contribution|charging credit"),
    ("launch", r"launch|arrives|on sale|orders open|pre-order|new variant|special edition|sport collection|limited edition"),
    ("runout", r"runout|run-out|clearance|demo sale|demonstrator|stock"),
]


def classify_event(title, detail=""):
    t = f"{title} {detail}".lower()
    for k, pat in EVENT_TYPES:
        if re.search(pat, t):
            return k
    return "offer"


def match_models(text):
    t = text.lower()
    hits = []
    for cid, kws in BENCH.get("model_keywords", {}).items():
        for kw in kws:
            kw = kw.strip().rstrip("$")
            if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", t):
                hits.append(cid)
                break
    return hits


def offers_feeds():
    path = DATA_DIR / "policy_events.json"
    store = load_json(path, {"events": [], "updated": None})
    known = {e["id"]: e for e in store["events"]}
    statuses = {}
    now = now_iso()

    jobs = [("beep", b) for b in BENCH["beep_brands"]] + [("zecar", b) for b in BENCH["zecar_brands"]]

    def work(j):
        kind, brand = j
        ev, err = (_beep_offers if kind == "beep" else _zecar_offers)(brand)
        return kind, brand, ev, err

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(work, jobs))
    n_new = 0
    for kind, brand, ev, err in results:
        key = f"{kind}-offers-{brand}"
        if ev is None:
            statuses[key] = _st(False, 0, err or "")
            continue
        for e in ev:
            e["type"] = classify_event(e["title"], e["detail"])
            e["cids"] = match_models(e["title"] + " " + e.get("models", "") + " " + e["detail"])
            e["last_seen"] = now
            if e["id"] in known:
                old = known[e["id"]]
                e["first_seen"] = old.get("first_seen", now)
                known[e["id"]] = e
            else:
                e["first_seen"] = now
                known[e["id"]] = e
                n_new += 1
        statuses[key] = _st(True, len(ev))
    # baseline events from config (curated, with sources)
    for e in config("policy_baseline.json").get("events", []):
        e = dict(e)
        e.setdefault("id", "base:" + sha(e.get("brand", "") + e.get("title", "") + e.get("start", ""), 12))
        e.setdefault("source", "baseline")
        e.setdefault("type", classify_event(e.get("title", ""), e.get("detail", "")))
        e.setdefault("cids", match_models(e.get("title", "") + " " + e.get("models", "") + " " + e.get("detail", "")))
        e.setdefault("state", "national")
        e["last_seen"] = now
        e["first_seen"] = known.get(e["id"], {}).get("first_seen", now)
        known[e["id"]] = e
    events = sorted(known.values(), key=lambda x: (x.get("start") or "", x.get("title") or ""))
    store = {"events": events, "updated": now, "n_sources_ok": sum(1 for s in statuses.values() if s["ok"]), "n_sources": len(statuses)}
    save_json(path, store)
    return store, statuses, n_new


def run_all(skip=()):
    statuses = {}
    out = {}
    if "prices" not in skip:
        try:
            store, st, n = beep_prices()
            statuses.update(st)
            statuses["beep-prices"] = _st(n > 0, n, f"{n} models")
            out["dap"] = store
        except Exception as ex:  # noqa: BLE001
            statuses["beep-prices"] = _st(False, 0, f"crashed: {str(ex)[:120]}")
    if "feeds" not in skip:
        try:
            store, st, n = offers_feeds()
            statuses.update(st)
            statuses["policy-events"] = _st(store["n_sources_ok"] > 0, n, f"{n} new; {store['n_sources_ok']}/{store['n_sources']} feeds ok")
            out["events"] = store
        except Exception as ex:  # noqa: BLE001
            statuses["policy-events"] = _st(False, 0, f"crashed: {str(ex)[:120]}")
    return out, statuses
