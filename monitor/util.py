"""Shared helpers: HTTP fetching with retries, text extraction, hashing, time."""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "docs" / "data"
SNAP_DIR = DATA_DIR / "snapshots"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"})


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
    os.replace(tmp, path)


def config(name: str):
    return load_json(CONFIG_DIR / name, {})


def sha(s: str, n: int = 16) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:n]


def fetch(url: str, *, timeout: int = 25, retries: int = 2, headers: dict | None = None,
          backoff: float = 3.0, ok_codes=(200,)) -> requests.Response | None:
    """GET with retries. Returns None on persistent failure (caller records status)."""
    last_err = None
    fetch.last_error = None  # type: ignore[attr-defined]
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=timeout, headers=headers or {})
            if r.status_code in ok_codes:
                return r
            last_err = f"HTTP {r.status_code}"
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(backoff * (attempt + 1) + 2)
                continue
            fetch.last_error = last_err  # type: ignore[attr-defined]
            return None
        except requests.RequestException as e:  # noqa: PERF203
            last_err = str(e)[:120]
            time.sleep(backoff)
    fetch.last_error = last_err  # type: ignore[attr-defined]
    return None


fetch.last_error = None  # type: ignore[attr-defined]


def fetch2(url: str, **kw):
    """Thread-safe variant: returns (response_or_None, error_or_None)."""
    import threading
    r = fetch(url, **kw)
    return r, (None if r is not None else (fetch.last_error or "fetch failed"))


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = TAG_RE.sub(" ", s)
    s = html_lib.unescape(s)
    return WS_RE.sub(" ", s).strip()


def visible_text(html: str) -> str:
    """Rough visible-text extraction for offer-page snapshots."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for t in soup(["script", "style", "noscript", "svg", "head"]):
            t.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = strip_html(html)
    lines = [WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


MONEY_RE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d{4,6}(?:\.\d+)?")
PCT_RE = re.compile(r"\d{1,2}(?:\.\d{1,2})?\s?%\s?(?:p\.?a\.?|per annum|comparison)?", re.I)


def money_values(text: str) -> list[int]:
    vals = []
    for m in MONEY_RE.findall(text):
        try:
            v = int(float(m.replace("$", "").replace(",", "").strip()))
            if 1000 <= v <= 600000:
                vals.append(v)
        except ValueError:
            pass
    return vals


def parse_date(s) -> str | None:
    """Best-effort to ISO-8601 UTC."""
    if not s:
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(float(s), tz=timezone.utc).replace(microsecond=0).isoformat()
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(str(s))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(str(s)[:len(fmt) + 6], fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except Exception:
            continue
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def polite_sleep(sec: float = 1.2) -> None:
    time.sleep(sec)
