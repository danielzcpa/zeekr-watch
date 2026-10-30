"""Orchestrator: collect -> classify -> merge -> write docs/data/*.json

Usage: python -m monitor.run [--skip reddit,offers,places] [--force-places]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import collectors as C
from . import benchmark as B
from . import classify as K
from .util import (DATA_DIR, config, load_json, save_json, now_iso, sha)

RETAIN_DAYS = 180


def _utc(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def normalise(raw: dict) -> dict | None:
    url = (raw.get("url") or "").strip()
    title = (raw.get("title") or "").strip()
    text = (raw.get("text") or "").strip()
    if not url and not title:
        return None
    # Google News redirect URLs are unique per article; use url when present.
    iid = sha(url or (raw["source"] + title + (raw.get("published") or "")))
    full = f"{title}\n{text}"
    models = K.zeekr_models(full)
    zk = K.mentions_zeekr(full) or raw["scope"].startswith("zeekr") and raw["source"] in (
        "appstore-ios", "playstore-android", "google-places") or raw["source"].startswith("productreview") \
        or raw["source"].startswith("reddit-Zeekr")
    comps = K.competitor_ids(full)
    brands = K.competitor_brands(full)
    rating = raw.get("rating")
    sent = K.sentiment(full, rating)
    cats = K.complaint_categories(full)
    sigs = K.signals(full)
    kind = raw.get("kind", "news")
    scope = raw.get("scope", "")

    # relevance filters
    if K.is_listing(title):
        return None  # classified "for sale" listings
    if not zk and not comps and not brands:
        return None
    if not zk and not comps:
        # brand only: keep when it is EV-related and carries a launch / price / offer signal
        if not (sigs and K.is_ev_context(full)):
            return None
    src_name = raw.get("source_name", raw["source"])
    if re.search(r"whirlpool|ozbargain|productreview|reddit", src_name, re.I) and kind == "news":
        kind = "post"
    au = K.is_au(full, src_name, url)

    # type assignment
    if kind == "recall":
        itype = "complaint"
    elif kind == "review":
        itype = "complaint" if (sent["label"] == "negative" or (rating is not None and rating <= 3)) else "review"
    elif kind == "post":
        itype = "complaint" if (sent["label"] == "negative" and (cats or sent["neg_hits"] >= 2)) else "post"
    elif kind == "deal":
        itype = "deal"
        if zk and sent["label"] == "negative" and cats and sent["neg_hits"] >= 2:
            itype = "complaint"
    elif kind == "official":
        itype = "official"
    else:
        if zk:
            is_recall = "safety" in cats and re.search(r"\brecall", full, re.I) is not None
            itype = "complaint" if (sent["label"] == "negative" and cats and sent["neg_hits"] >= 3) or is_recall else "news_zeekr"
        else:
            itype = "competitor_news"
    sev = K.severity(full, sent, rating, cats) if itype == "complaint" else None
    return {
        "id": iid, "type": itype, "source": raw["source"], "source_name": raw.get("source_name", raw["source"]),
        "url": url, "title": title[:300], "text": text[:1200], "author": (raw.get("author") or "")[:80],
        "published": raw.get("published"), "rating": rating, "zeekr": zk, "models": models, "competitors": comps,
        "brands": brands, "categories": cats, "sentiment": sent, "severity": sev, "signals": sigs,
        "scope": scope, "au": au, "extra": raw.get("extra") or {},
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="", help="comma list: reddit,offers,places,news,apps,productreview,official,recalls")
    ap.add_argument("--force-places", action="store_true")
    args = ap.parse_args(argv)
    skip = set(x.strip() for x in args.skip.split(",") if x.strip())

    SRC = config("sources.json")
    C.SRC = SRC
    t0 = time.time()
    run_at = now_iso()
    raw_items: list[dict] = []
    statuses: dict = {}

    def step(name, fn, *a, **kw):
        if name in skip:
            statuses[name] = {"ok": True, "count": 0, "note": "skipped"}
            return None
        ts = time.time()
        try:
            return fn(*a, **kw)
        except Exception as ex:  # keep the run alive whatever a source does
            statuses[name] = {"ok": False, "count": 0, "note": f"crashed: {str(ex)[:150]}"}
            return None
        finally:
            print(f"  step {name}: {time.time()-ts:.1f}s", flush=True)

    r = step("news", C.google_news, SRC["google_news"]["zeekr_queries"] + SRC["google_news"]["competitor_queries"])
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("news", C.rss_feeds, SRC["rss_feeds"])
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("reddit", C.reddit)
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("productreview", C.productreview)
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("apps", C.app_stores)
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("official", C.zeekr_official)
    if r:
        raw_items += r[0]; statuses.update(r[1])
    r = step("recalls", C.recalls)
    if r:
        raw_items += r[0]; statuses.update(r[1])
    places_state = None
    r = step("places", C.google_places, force=args.force_places)
    if r:
        raw_items += r[0]; statuses.update(r[1]); places_state = r[2]
    bench_out = {}
    r = step("benchmark", B.run_all, skip=skip)
    if r:
        bench_out, st = r
        statuses.update(st)
    offer_changes, offer_snaps = [], {}
    r = step("offers", C.offer_pages)
    if r:
        offer_changes, st, offer_snaps = r
        statuses.update(st)

    # ---------------------------------------------------------- merge
    items_path = DATA_DIR / "items.json"
    store = {it["id"]: it for it in load_json(items_path, [])}
    new_ids = []
    for raw in raw_items:
        it = normalise(raw)
        if not it:
            continue
        if it["id"] in store:
            old = store[it["id"]]
            it["first_seen"] = old.get("first_seen", run_at)
            # keep earliest published if new is None
            it["published"] = it["published"] or old.get("published")
            store[it["id"]] = it
        else:
            it["first_seen"] = run_at
            store[it["id"]] = it
            new_ids.append(it["id"])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETAIN_DAYS)).isoformat()
    items = [it for it in store.values() if (it.get("published") or it.get("first_seen")) >= cutoff]
    # de-duplicate the same article seen via Google News and via the outlet's own feed:
    # prefer the direct URL, then the earlier first_seen.
    def tkey(it):
        t = re.sub(r"\s+[-|]\s+(?:[^\s|-]+\s?){1,4}$", "", it["title"].lower())  # strip " - Outlet" suffix (<=4 words)
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", t)[:120]
    best: dict[str, dict] = {}
    for it in items:
        k = tkey(it)
        if len(k) < 12:
            best[it["id"]] = it
            continue
        cur = best.get(k)
        if cur is None:
            best[k] = it
            continue
        it_direct = "news.google.com" not in it["url"]
        cur_direct = "news.google.com" not in cur["url"]
        if (it_direct and not cur_direct) or (it_direct == cur_direct and it["first_seen"] < cur["first_seen"]):
            best[k] = it
    items = list(best.values())
    items.sort(key=lambda x: (x.get("published") or x.get("first_seen")), reverse=True)
    save_json(items_path, items)

    # offer changes log
    oc_path = DATA_DIR / "offer_changes.json"
    oc = load_json(oc_path, [])
    known = {c["id"] for c in oc}
    for c in offer_changes:
        if c["id"] not in known:
            oc.insert(0, c)
    oc = oc[:500]
    save_json(oc_path, oc)
    save_json(DATA_DIR / "offer_snapshots.json", {k: {kk: vv for kk, vv in v.items() if kk != "lines"} | {"lines": v.get("lines", [])[:60]} for k, v in offer_snaps.items()} if offer_snaps else load_json(DATA_DIR / "offer_snapshots.json", {}))

    # ---------------------------------------------------------- summary
    now = datetime.now(timezone.utc)
    def within(it, hours):
        d = _utc(it.get("published") or it.get("first_seen") or "")
        return d is not None and (now - d) <= timedelta(hours=hours)
    complaints = [it for it in items if it["type"] == "complaint"]
    comp_news = [it for it in items if it["type"] == "competitor_news"]
    daily = defaultdict(lambda: {"complaints": 0, "competitor_news": 0, "zeekr_news": 0})
    for it in items:
        d = (it.get("published") or it.get("first_seen"))[:10]
        if it["type"] == "complaint":
            daily[d]["complaints"] += 1
        elif it["type"] == "competitor_news":
            daily[d]["competitor_news"] += 1
        elif it["type"] in ("news_zeekr", "official"):
            daily[d]["zeekr_news"] += 1
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    series = [{"date": d, **daily.get(d, {"complaints": 0, "competitor_news": 0, "zeekr_news": 0})} for d in days]

    cat_counts = Counter(c for it in complaints if within(it, 24 * 30) for c in it["categories"])
    model_counts = Counter(m for it in complaints if within(it, 24 * 30) for m in it["models"])
    src_counts = Counter(it["source_name"].split(" · ")[0] for it in complaints if within(it, 24 * 30))
    sev_counts = Counter(it["severity"] for it in complaints if within(it, 24 * 7))

    comps_cfg = config("competitors.json")
    comp_signals = {}
    for c in comps_cfg["competitors"]:
        hits = [it for it in comp_news if c["id"] in it["competitors"]]
        comp_signals[c["id"]] = {
            "n_30d": sum(1 for it in hits if within(it, 24 * 30)),
            "launch": [it["id"] for it in hits if "launch" in it["signals"]][:10],
            "offer": [it["id"] for it in hits if "offer" in it["signals"] or "price" in it["signals"]][:10],
            "latest": hits[0]["id"] if hits else None,
        }

    alerts = []
    for it in complaints:
        if it["severity"] == "high" and within(it, 48):
            alerts.append({"kind": "complaint_high", "id": it["id"], "title": it["title"], "source": it["source_name"], "t": it.get("published") or it["first_seen"]})
    for it in comp_news:
        if within(it, 72) and "launch" in it["signals"] and it["competitors"]:
            alerts.append({"kind": "competitor_launch", "id": it["id"], "title": it["title"], "source": it["source_name"], "t": it.get("published") or it["first_seen"], "competitors": it["competitors"]})
        elif within(it, 72) and ("offer" in it["signals"] or "price" in it["signals"]) and it["competitors"]:
            alerts.append({"kind": "competitor_offer", "id": it["id"], "title": it["title"], "source": it["source_name"], "t": it.get("published") or it["first_seen"], "competitors": it["competitors"]})
    for c in oc[:20]:
        if (now - _utc(c["detected"])) <= timedelta(hours=72):
            alerts.append({"kind": "offer_page_change", "id": c["id"], "title": f"{c['brand']} 官网政策页面变化（+{len(c['added'])} / −{len(c['removed'])} 行）", "title_en": f"{c['brand']} offer page changed (+{len(c['added'])} / −{len(c['removed'])} lines)", "source": c["url"], "t": c["detected"]})
    alerts.sort(key=lambda a: a["t"], reverse=True)

    summary = {
        "generated": run_at, "duration_s": round(time.time() - t0, 1), "items_total": len(items), "new_this_run": len(new_ids),
        "counts": {
            "complaints_24h": sum(1 for it in complaints if within(it, 24)),
            "complaints_7d": sum(1 for it in complaints if within(it, 24 * 7)),
            "complaints_30d": sum(1 for it in complaints if within(it, 24 * 30)),
            "high_7d": sev_counts.get("high", 0), "medium_7d": sev_counts.get("medium", 0), "low_7d": sev_counts.get("low", 0),
            "competitor_news_7d": sum(1 for it in comp_news if within(it, 24 * 7)),
            "launch_signals_7d": sum(1 for it in comp_news if within(it, 24 * 7) and "launch" in it["signals"] and it["competitors"]),
            "offer_signals_7d": sum(1 for it in comp_news if within(it, 24 * 7) and ("offer" in it["signals"] or "price" in it["signals"]) and it["competitors"]),
            "zeekr_news_7d": sum(1 for it in items if it["type"] in ("news_zeekr", "official") and within(it, 24 * 7)),
            "offer_page_changes_7d": sum(1 for c in oc if (now - _utc(c["detected"])) <= timedelta(days=7)),
        },
        "series_30d": series,
        "categories_30d": [{"key": k, "zh": K.COMPLAINT_CATEGORIES[k]["zh"], "en": K.COMPLAINT_CATEGORIES[k]["en"], "n": n} for k, n in cat_counts.most_common()],
        "models_30d": dict(model_counts), "sources_30d": dict(src_counts.most_common(12)),
        "competitor_signals": comp_signals, "alerts": alerts[:60],
        "source_status": statuses,
        "places": {"configured": bool(places_state and places_state.get("configured")), "last_run": places_state.get("last_run") if places_state else None,
                   "stores": [{"name": k, "rating": v.get("rating"), "count": v.get("count"), "error": v.get("error"), "maps_url": v.get("maps_url"), "state": v.get("state")} for k, v in (places_state or {}).get("stores", {}).items()],
                   "n_reviews": len((places_state or {}).get("reviews", []))},
    }
    save_json(DATA_DIR / "summary.json", summary)

    runs_path = DATA_DIR / "runs.json"
    runs = load_json(runs_path, [])
    ok = sum(1 for s in statuses.values() if s.get("ok"))
    runs.insert(0, {"t": run_at, "duration_s": summary["duration_s"], "new": len(new_ids), "sources_ok": ok, "sources_total": len(statuses)})
    save_json(runs_path, runs[:300])

    # publish config copies for the site
    save_json(DATA_DIR / "zeekr.json", config("zeekr_models.json"))
    save_json(DATA_DIR / "competitors.json", comps_cfg)
    save_json(DATA_DIR / "benchmark.json", config("benchmark.json"))
    save_json(DATA_DIR / "german_evidence.json", config("german_evidence.json"))
    print(f"run {run_at}: {len(raw_items)} raw -> {len(items)} stored ({len(new_ids)} new); sources ok {ok}/{len(statuses)}; {summary['duration_s']}s")
    for k, s in statuses.items():
        if not s.get("ok"):
            print(f"  ! {k}: {s.get('note')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
