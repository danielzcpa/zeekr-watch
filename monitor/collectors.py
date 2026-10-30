"""Source collectors. Each returns (items, status) where items is a list of raw dicts:
{source, source_name, url, title, text, author, published, rating, kind, scope}
and status is {ok: bool, count: int, note: str}.
"""
from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import quote

import feedparser

from concurrent.futures import ThreadPoolExecutor
import requests as _rq

from .util import fetch, strip_html, parse_date, polite_sleep, sha, load_json, save_json, DATA_DIR, now_iso, UA

SRC = None  # set by run.py


def _get(url, timeout=20, headers=None, retries=0, backoff=4):
    """Thread-safe GET (own session). Returns (resp|None, err|None)."""
    h = {"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9", **(headers or {})}
    err = None
    for attempt in range(retries + 1):
        try:
            r = _rq.get(url, headers=h, timeout=timeout)
            if r.status_code == 200:
                return r, None
            err = f"HTTP {r.status_code}"
            if r.status_code in (429,) or r.status_code >= 500:
                time.sleep(backoff * (attempt + 1))
                continue
            return None, err
        except _rq.RequestException as e:
            err = str(e)[:140]
            time.sleep(backoff)
    return None, err


def _status(ok, count, note=""):
    return {"ok": bool(ok), "count": int(count), "note": note[:200]}


def _feed_items(content: bytes | str, source_key: str, source_name: str, kind: str, scope: str):
    fp = feedparser.parse(content)
    out = []
    for e in fp.entries:
        title = strip_html(e.get("title", ""))
        summary = strip_html(e.get("summary", "") or e.get("description", ""))
        if "content" in e and e.content:
            try:
                summary = strip_html(e.content[0].get("value", "")) or summary
            except Exception:
                pass
        link = e.get("link", "")
        pub = e.get("published") or e.get("updated") or e.get("pubDate")
        src_name = source_name
        if "source" in e and isinstance(e.source, dict) and e.source.get("title"):
            src_name = f"{source_name} · {e.source['title']}"
        out.append({
            "source": source_key, "source_name": src_name, "url": link, "title": title,
            "text": summary[:1200], "author": (e.get("author") or ""), "published": parse_date(pub),
            "rating": None, "kind": kind, "scope": scope,
        })
    return out, fp


# ------------------------------------------------------------- Google News
def google_news(queries: list[dict]):
    base = SRC["google_news"]["base"]
    items, statuses = [], {}

    def work(q):
        url = base + quote(q["q"], safe="")
        r, err = _get(url, timeout=25, retries=1, backoff=5)
        if r is None:
            return q["key"], [], _status(False, 0, err or "fetch failed")
        its, fp = _feed_items(r.content, q["key"], "Google News", "news", q["scope"])
        return q["key"], its, _status(True, len(its))

    with ThreadPoolExecutor(max_workers=3) as ex:
        for key, its, st in ex.map(work, queries):
            items.extend(its); statuses[key] = st
    return items, statuses


# ------------------------------------------------------------- generic RSS
def rss_feeds(feeds: list[dict]):
    items, statuses = [], {}

    def work(f):
        r, err = _get(f["url"], timeout=25, retries=1)
        if r is None:
            return f["key"], [], _status(False, 0, err or "fetch failed")
        kind = "deal" if "ozbargain" in f["key"] else "news"
        its, fp = _feed_items(r.content, f["key"], f["name"], kind, f["scope"])
        return f["key"], its, _status(len(its) > 0 or not fp.bozo, len(its), "" if its else "empty/bozo")

    with ThreadPoolExecutor(max_workers=4) as ex:
        for key, its, st in ex.map(work, feeds):
            items.extend(its); statuses[key] = st
    return items, statuses


# ------------------------------------------------------------- Reddit
def _reddit_token():
    cid, sec = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not sec:
        return None
    try:
        import requests
        r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, sec),
                          data={"grant_type": "client_credentials"},
                          headers={"User-Agent": SRC["reddit"]["user_agent"]}, timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        return None
    return None


def reddit():
    cfg = SRC["reddit"]
    ua = {"User-Agent": cfg["user_agent"]}
    items, statuses = [], {}
    token = _reddit_token()

    def add_posts(key, children, scope):
        n = 0
        for ch in children:
            d = ch.get("data", {})
            if not d.get("title"):
                continue
            items.append({
                "source": key, "source_name": f"Reddit r/{d.get('subreddit', '')}",
                "url": "https://www.reddit.com" + d.get("permalink", ""), "title": d["title"],
                "text": (d.get("selftext") or "")[:1200], "author": d.get("author", ""),
                "published": parse_date(d.get("created_utc")), "rating": None, "kind": "post", "scope": scope,
                "extra": {"score": d.get("score"), "comments": d.get("num_comments"), "flair": d.get("link_flair_text")},
            })
            n += 1
        return n

    if token:
        import requests
        h = {"Authorization": f"bearer {token}", **ua}
        targets = [(f"reddit-{s}", f"https://oauth.reddit.com/r/{s}/new?limit=50", "zeekr_complaint") for s in cfg["subreddit_new"]]
        targets += [(f"reddit-{s}", f"https://oauth.reddit.com/r/{s}/search?q=zeekr&restrict_sr=1&sort=new&limit=50", "zeekr_complaint") for s in cfg["subreddit_search"]]
        targets += [("reddit-global", "https://oauth.reddit.com/search?q=zeekr&sort=new&limit=100", "zeekr_complaint")]
        for key, url, scope in targets:
            try:
                r = requests.get(url, headers=h, timeout=25)
                if r.status_code != 200:
                    statuses[key] = _status(False, 0, f"HTTP {r.status_code}")
                    continue
                n = add_posts(key, r.json().get("data", {}).get("children", []), scope)
                statuses[key] = _status(True, n, "oauth")
            except Exception as e:
                statuses[key] = _status(False, 0, str(e)[:100])
            time.sleep(1.0)
        return items, statuses

    # Anonymous RSS fallback (works but rate-limited; back off on 429)
    targets = [(f"reddit-{s}", f"https://www.reddit.com/r/{s}/new.rss?limit=50", "zeekr_complaint") for s in cfg["subreddit_new"]]
    targets += [(f"reddit-{s}", f"https://www.reddit.com/r/{s}/search.rss?q=zeekr&restrict_sr=on&sort=new", "zeekr_complaint") for s in cfg["subreddit_search"]]
    targets += [("reddit-global", cfg["global_search"], "zeekr_complaint")]
    fails = 0
    for key, url, scope in targets:
        if fails >= 3:
            statuses[key] = _status(False, 0, "skipped after repeated 429 (anonymous RSS; add REDDIT_CLIENT_ID/SECRET secrets)")
            continue
        r, err = _get(url, timeout=25, retries=1, headers=ua, backoff=6)
        if r is None:
            fails += 1
            statuses[key] = _status(False, 0, (err or "") + " (anonymous RSS; add REDDIT_CLIENT_ID/SECRET secrets)")
            time.sleep(3)
            continue
        fails = 0
        its, fp = _feed_items(r.content, key, "Reddit", "post", scope)
        for it in its:
            m = re.search(r"/r/([^/]+)/", it["url"])
            if m:
                it["source_name"] = f"Reddit r/{m.group(1)}"
            it["text"] = re.sub(r"\s*submitted by\s*/u/\S+.*$", "", it["text"]).strip()
        items.extend(its)
        statuses[key] = _status(True, len(its), "anonymous RSS")
        time.sleep(3)
    return items, statuses


# ------------------------------------------------------------- ProductReview.com.au
def productreview():
    items, statuses = [], {}
    for url in SRC["productreview"]["listings"]:
        key = "productreview-" + url.rstrip("/").split("/")[-1]
        r = fetch(url, timeout=30)
        if r is None:
            statuses[key] = _status(False, 0, fetch.last_error or "fetch failed")
            continue
        n = 0
        for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', r.text, re.S):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            blobs = data if isinstance(data, list) else [data]
            for b in blobs:
                reviews = b.get("review") or b.get("reviews") or []
                if isinstance(reviews, dict):
                    reviews = [reviews]
                for rv in reviews:
                    try:
                        rating = float((rv.get("reviewRating") or {}).get("ratingValue"))
                    except (TypeError, ValueError):
                        rating = None
                    author = rv.get("author")
                    author = author.get("name") if isinstance(author, dict) else (author or "")
                    items.append({
                        "source": key, "source_name": "ProductReview.com.au", "url": rv.get("url") or url,
                        "title": rv.get("name") or rv.get("headline") or f"Review ({rating}★)",
                        "text": strip_html(rv.get("reviewBody") or rv.get("description") or "")[:1200],
                        "author": author, "published": parse_date(rv.get("datePublished")), "rating": rating,
                        "kind": "review", "scope": "zeekr_complaint",
                    })
                    n += 1
                agg = b.get("aggregateRating")
                if agg:
                    statuses[key + "-agg"] = _status(True, 0, f"aggregate {agg.get('ratingValue')}★ / {agg.get('reviewCount') or agg.get('ratingCount')} reviews")
        statuses[key] = _status(True, n)
        polite_sleep(1.0)
    # detect new model listings
    r = fetch(SRC["productreview"]["search"], timeout=30)
    if r is not None:
        slugs = sorted(set(re.findall(r'/listings/(zeekr[a-z0-9\-]*)', r.text)))
        statuses["productreview-search"] = _status(True, len(slugs), "listings: " + ", ".join(slugs[:10]))
    else:
        statuses["productreview-search"] = _status(False, 0, fetch.last_error or "")
    return items, statuses


# ------------------------------------------------------------- App stores
def app_stores():
    items, statuses = [], {}
    cfg = SRC["app_stores"]
    r = fetch(cfg["ios_rss"], timeout=25)
    if r is None:
        statuses["appstore-ios"] = _status(False, 0, fetch.last_error or "")
    else:
        n = 0
        try:
            entries = r.json().get("feed", {}).get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            for e in entries:
                if "im:rating" not in e:
                    continue
                rating = float(e["im:rating"]["label"])
                items.append({
                    "source": "appstore-ios", "source_name": "Apple App Store (AU) · ZEEKR app",
                    "url": (e.get("link") or {}).get("attributes", {}).get("href") or f"https://apps.apple.com/au/app/zeekr/id{cfg['ios_app_id']}?see-all=reviews",
                    "title": e.get("title", {}).get("label", ""), "text": e.get("content", {}).get("label", "")[:1200],
                    "author": e.get("author", {}).get("name", {}).get("label", ""),
                    "published": parse_date(e.get("updated", {}).get("label")), "rating": rating, "kind": "review",
                    "scope": "zeekr_complaint", "extra": {"version": e.get("im:version", {}).get("label")},
                })
                n += 1
            statuses["appstore-ios"] = _status(True, n)
        except Exception as ex:
            statuses["appstore-ios"] = _status(False, 0, str(ex)[:100])
    try:
        from google_play_scraper import reviews, Sort
        res, _ = reviews(cfg["android_package"], lang="en", country="au", sort=Sort.NEWEST, count=60)
        n = 0
        for rv in res:
            items.append({
                "source": "playstore-android", "source_name": "Google Play (AU) · ZEEKR app",
                "url": f"https://play.google.com/store/apps/details?id={cfg['android_package']}&hl=en_AU&gl=AU&reviewId={rv.get('reviewId')}",
                "title": f"{rv.get('score')}★ · {(rv.get('content') or '')[:60]}", "text": (rv.get("content") or "")[:1200],
                "author": rv.get("userName", ""), "published": parse_date(rv.get("at").isoformat() if rv.get("at") else None),
                "rating": float(rv.get("score")) if rv.get("score") else None, "kind": "review", "scope": "zeekr_complaint",
                "extra": {"version": rv.get("reviewCreatedVersion"), "thumbs": rv.get("thumbsUpCount")},
            })
            n += 1
        statuses["playstore-android"] = _status(True, n)
    except Exception as ex:
        statuses["playstore-android"] = _status(False, 0, str(ex)[:120])
    return items, statuses


# ------------------------------------------------------------- Zeekr official news
def zeekr_official():
    items, statuses = [], {}
    url = SRC["zeekr_official"]["news"]
    r = fetch(url, timeout=30)
    if r is None:
        statuses["zeekr-official-news"] = _status(False, 0, fetch.last_error or "")
        return items, statuses
    n = 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/" not in href or href.rstrip("/").endswith("/news"):
                continue
            if not href.startswith("http"):
                href = "https://www.zeekrlife.com" + href
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 8 or href in seen:
                continue
            seen.add(href)
            items.append({"source": "zeekr-official-news", "source_name": "ZEEKR Australia official news", "url": href,
                          "title": title[:200], "text": "", "author": "ZEEKR Australia", "published": None,
                          "rating": None, "kind": "official", "scope": "zeekr"})
            n += 1
    except Exception as ex:
        statuses["zeekr-official-news"] = _status(False, 0, str(ex)[:100])
        return items, statuses
    statuses["zeekr-official-news"] = _status(True, n)
    return items, statuses


# ------------------------------------------------------------- Recalls
def recalls():
    items, statuses = [], {}
    url = SRC["recalls"]["vehicle_recalls"]
    r = fetch(url, timeout=20, retries=0)
    if r is None:
        statuses["recalls-gov"] = _status(False, 0, (fetch.last_error or "") + " (datacenter IP may be blocked; Google News fallback active)")
        return items, statuses
    n = 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.select("a[href*='/recall/']"):
            title = a.get_text(" ", strip=True)
            if "zeekr" not in title.lower():
                continue
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.vehicle.recalls.gov.au" + href
            items.append({"source": "recalls-gov", "source_name": "vehicle.recalls.gov.au", "url": href, "title": title,
                          "text": "", "author": "", "published": None, "rating": None, "kind": "recall", "scope": "zeekr_recall"})
            n += 1
        statuses["recalls-gov"] = _status(True, n)
    except Exception as ex:
        statuses["recalls-gov"] = _status(False, 0, str(ex)[:100])
    return items, statuses


# ------------------------------------------------------------- OEM offer-page snapshots
_OFFER_LINE_RE = re.compile(r"\$\s?\d|%|drive.?away|cashback|cash back|bonus|offer|finance|p\.a\.|comparison rate|free|discount|rebate|save|saving", re.I)


def offer_pages():
    """Fetch each OEM offers page, extract offer-like lines, diff against previous snapshot."""
    from .util import SNAP_DIR, visible_text, money_values
    changes, statuses, snapshots = [], {}, {}

    def work(p):
        r, err = _get(p["url"], timeout=20, retries=0)
        return p, r, err

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(work, SRC["offer_pages"]))
    for p, r, err in results:
        key = p["key"]
        snap_path = SNAP_DIR / f"{key}.json"
        prev = load_json(snap_path, {})
        if r is None:
            statuses["offers-" + key] = _status(False, 0, err or "")
            snapshots[key] = {**prev, "last_error": err, "last_attempt": now_iso()}
            continue
        text = visible_text(r.text)
        lines = []
        seen = set()
        for ln in text.splitlines():
            if 12 <= len(ln) <= 400 and _OFFER_LINE_RE.search(ln):
                k = ln.lower()
                if k not in seen:
                    seen.add(k)
                    lines.append(ln)
        lines = lines[:400]
        digest = sha("\n".join(lines))
        prev_lines = set(prev.get("lines", []))
        added = [l for l in lines if l not in prev_lines]
        removed = [l for l in prev.get("lines", []) if l not in set(lines)]
        snap = {"key": key, "brand": p["brand"], "url": p["url"], "fetched": now_iso(), "digest": digest,
                "lines": lines, "money": sorted(set(money_values("\n".join(lines))))[:80], "n_lines": len(lines)}
        if prev and prev.get("digest") != digest and (added or removed):
            changes.append({"id": sha(key + digest), "key": key, "brand": p["brand"], "url": p["url"], "detected": now_iso(),
                            "added": added[:40], "removed": removed[:40]})
        snapshots[key] = snap
        save_json(snap_path, snap)
        statuses["offers-" + key] = _status(True, len(lines), "changed" if (prev and prev.get("digest") != digest) else ("first snapshot" if not prev else "unchanged"))
    return changes, statuses, snapshots


# ------------------------------------------------------------- Google Places (store reviews)
def google_places(force: bool = False):
    """Needs GOOGLE_MAPS_API_KEY. Runs every interval_hours; caches place_ids."""
    cfg = SRC["google_places"]
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    state_path = DATA_DIR / "places.json"
    state = load_json(state_path, {"stores": {}, "reviews": [], "last_run": None, "configured": False})
    statuses = {}
    if not key:
        state["configured"] = False
        statuses["google-places"] = _status(False, 0, "GOOGLE_MAPS_API_KEY not set – store reviews skipped")
        save_json(state_path, state)
        return [], statuses, state
    state["configured"] = True
    last = state.get("last_run")
    if last and not force:
        from datetime import datetime, timezone
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600
        if age_h < cfg["interval_hours"] - 0.1:
            statuses["google-places"] = _status(True, 0, f"skipped (last run {age_h:.1f}h ago; interval {cfg['interval_hours']}h)")
            return [], statuses, state
    import requests
    items = []
    n_new = 0
    for st in cfg["stores"]:
        rec = state["stores"].get(st["name"], {"name": st["name"], "state": st["state"]})
        try:
            if not rec.get("place_id"):
                r = requests.post("https://places.googleapis.com/v1/places:searchText",
                                  headers={"X-Goog-Api-Key": key, "Content-Type": "application/json",
                                           "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount"},
                                  json={"textQuery": st["query"], "regionCode": "AU", "languageCode": "en"}, timeout=20)
                places = r.json().get("places", []) if r.status_code == 200 else []
                places = [p for p in places if "zeekr" in (p.get("displayName", {}).get("text", "").lower())] or places
                if not places:
                    rec["error"] = f"not found ({r.status_code})"
                    state["stores"][st["name"]] = rec
                    continue
                p0 = places[0]
                rec.update({"place_id": p0["id"], "display_name": p0.get("displayName", {}).get("text"),
                            "address": p0.get("formattedAddress")})
            r = requests.get(f"https://places.googleapis.com/v1/places/{rec['place_id']}",
                             headers={"X-Goog-Api-Key": key,
                                      "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,reviews,googleMapsUri,formattedAddress"},
                             params={"languageCode": "en"}, timeout=20)
            if r.status_code != 200:
                rec["error"] = f"details HTTP {r.status_code}"
                state["stores"][st["name"]] = rec
                continue
            d = r.json()
            hist = rec.get("history", [])
            hist.append({"t": now_iso(), "rating": d.get("rating"), "count": d.get("userRatingCount")})
            rec.update({"rating": d.get("rating"), "count": d.get("userRatingCount"), "maps_url": d.get("googleMapsUri"),
                        "address": d.get("formattedAddress") or rec.get("address"), "history": hist[-400:], "error": None,
                        "checked": now_iso()})
            for rv in d.get("reviews", []):
                rid = sha(rec["place_id"] + (rv.get("name") or "") + (rv.get("publishTime") or ""))
                if any(x["id"] == rid for x in state["reviews"]):
                    continue
                txt = (rv.get("text") or {}).get("text") or (rv.get("originalText") or {}).get("text") or ""
                entry = {"id": rid, "store": st["name"], "state": st["state"], "rating": rv.get("rating"),
                         "author": (rv.get("authorAttribution") or {}).get("displayName"), "text": txt[:1500],
                         "published": parse_date(rv.get("publishTime")), "relative": rv.get("relativePublishTimeDescription"),
                         "url": (rv.get("authorAttribution") or {}).get("uri") or rec.get("maps_url"), "first_seen": now_iso()}
                state["reviews"].append(entry)
                n_new += 1
                items.append({"source": "google-places", "source_name": f"Google Maps reviews · {st['name']}", "url": entry["url"] or "",
                              "title": f"{entry['rating']}★ · {st['name']}", "text": txt[:1200], "author": entry["author"] or "",
                              "published": entry["published"], "rating": float(rv.get("rating")) if rv.get("rating") else None,
                              "kind": "review", "scope": "zeekr_complaint", "extra": {"store": st["name"], "state": st["state"]}})
        except Exception as ex:
            rec["error"] = str(ex)[:120]
        state["stores"][st["name"]] = rec
        time.sleep(0.3)
    state["last_run"] = now_iso()
    state["reviews"] = sorted(state["reviews"], key=lambda x: x.get("published") or "", reverse=True)[:3000]
    save_json(state_path, state)
    statuses["google-places"] = _status(True, n_new, f"{len(cfg['stores'])} stores checked, {n_new} new reviews")
    return items, statuses, state
