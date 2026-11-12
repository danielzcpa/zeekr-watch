"""Transaction-price (TP) reference: docs/data/tp.json

Method (per variant):
  MSRP  - config/competitors.json (or evidence override)
  DAP   - evidence > The Beep NSW DAP (dap_history) > NSW on-road estimate from MSRP
  kind  - demo   : dealer demo / near-new drive-away asking price (below new-car TP);
                   new-car TP = observed x uplift_low..uplift_high, capped at DAP
          newcar : DAP less official cash offer (or official campaign DAP)
          agency : direct-sales / agency fixed price, TP = DAP
          est    : no evidence, TP = DAP x seeded random factor in est_range
Australia has no public settled-price dataset; this is a reference built from
public asking prices and official offers. Edit config/tp_evidence.json to update.
"""
from __future__ import annotations

import random
import re

from .util import DATA_DIR, config, load_json, save_json, now_iso

STOP = {"m", "sport", "4matic", "4matic+", "xdrive", "auto", "my26", "my25", "my27", "座", "seat", "7", "6", "the", "edition"}


SYN = [("standard range", "sr"), ("long range", "lr"), ("extended range", "er"), ("gt-line", "gtline"), ("gt line", "gtline")]
# tokens that distinguish grades: a mismatch on any of these disqualifies a candidate
RANGE = {"sr", "lr", "er"}
DISTINCT = {"black", "performance", "pro", "ultra", "premium", "brabus", "dual", "twin",
            "touring", "gt", "gtline", "azami", "air", "earth", "elite", "plus", "luxury", "sports", "autobiography", "hse", "dynamic",
            "s", "turbo", "amg", "63", "53", "450", "300", "350", "500", "600", "700h", "500d", "40d", "40i", "30d", "50e", "m60i"}


def _tokens(s: str) -> set[str]:
    s = re.sub(r"[（(].*?[)）]", " ", s or "").lower()
    for a, b in SYN:
        s = s.replace(a, b)
    s = s.replace("-", " ").replace("/", " ")
    return {t for t in re.findall(r"[a-z0-9+]+", s) if t not in STOP}


def _match(name: str, cands: dict, model: str = "") -> str | None:
    a = _tokens(name)
    if not (a - _tokens(model)):
        # variant named after the model itself (e.g. "Elexio") -> base grade
        for c in cands:
            if _tokens(c) & {"base"}:
                return c
        return None
    best, score = None, 0.0
    for c in cands:
        b = _tokens(c)
        if not b:
            continue
        inter = len(a & b)
        if not inter:
            continue
        if (a ^ b) & DISTINCT:
            continue
        if (a & RANGE) and (b & RANGE) and (a & RANGE) != (b & RANGE):
            continue
        j = inter / len(a | b)
        if b <= a or a <= b:
            j += 0.5
        if j > score:
            best, score = c, j
    return best if score >= 0.5 else None


def nsw_onroad(msrp: float) -> int:
    duty = 0.03 * min(msrp, 45000) + 0.05 * max(msrp - 45000, 0)
    rego_ctp = 1350
    delivery = 2000 if msrp < 80000 else (3000 if msrp < 150000 else 4500)
    return int(round(msrp + duty + rego_ctp + delivery))


def _latest_dap(hist: dict, cid: str, variant: str, model: str = "", zeekr_key: str | None = None, explicit: str | None = None, msrp=None):
    """Return (dap, state, beep_variant) for a competitor variant from dap_history.
    When several Beep pages share one cid (iX1 / iX2), prefer the page whose slug appears in the variant name."""
    cands = []
    for slug, m in (hist.get("models") or {}).items():
        if zeekr_key:
            if m.get("group") != "zeekr" or m.get("zeekr") != zeekr_key:
                continue
        elif m.get("cid") != cid:
            continue
        tail = slug.split("/")[-1].replace("-", "")
        pri = 0 if tail in variant.lower().replace("-", "").replace(" ", "") else 1
        cands.append((pri, slug, m))
    for _, slug, m in sorted(cands, key=lambda x: x[0]):
        vs = m.get("variants") or {}
        bv = explicit if (explicit and explicit in vs) else _match(variant, vs, model)
        if not bv:
            continue
        for st in ("NSW", "VIC"):
            ser = vs[bv].get(st) or []
            if ser and ser[-1][1]:
                if msrp and ser[-1][1] > msrp * 1.15:   # different model year / grade on the Beep page
                    break
                return ser[-1][1], st, bv
    return None, None, None


def _row(p: dict, cid: str, brand: str, model: str, model_en: str, tier: str, zk: list, v: dict, hist: dict,
         offer: dict | None, is_zeekr=False):
    name = v["name"]
    msrp = v.get("msrp") if v.get("msrp") is not None else v.get("price")
    kind = v.get("kind")
    observed = v.get("observed")
    note, note_en, conf, rng = v.get("note", ""), v.get("note_en", ""), v.get("confidence", ""), v.get("range", "")
    urls = list(v.get("urls") or [])
    # DAP
    dap, dap_src, dap_state = v.get("dap"), v.get("dap_source"), "NSW"
    dap_src_en = v.get("dap_source_en") or (dap_src.replace("（", " (").replace("）", ")") if dap_src else None)
    if dap is None:
        explicit = ((p.get("zeekr_dap_map") or {}).get(zk[0]) or {}).get(name) if is_zeekr else None
        d, st, _ = _latest_dap(hist, cid, name, model, zk[0] if is_zeekr else None, explicit, msrp)
        if d:
            dap, dap_src, dap_src_en, dap_state = d, f"{st} DAP（The Beep）", f"{st} DAP (The Beep)", st
        elif v.get("basis") == "da" and msrp:
            dap, dap_src, dap_src_en = msrp, "官方 DAP 定价", "Official DAP pricing"
        elif msrp:
            dap, dap_src, dap_src_en = nsw_onroad(msrp), "估算：MSRP + NSW 上路费用", "Estimate: MSRP + NSW on-roads"
    if is_zeekr:
        kind, observed = "agency", dap
        note, note_en = "本品，固定 DAP，作对照", "Own model, fixed DAP, for reference"
        conf = "—"
    elif kind is None:
        if offer:
            kind = offer.get("kind", "newcar")
            cash = offer.get("cash") or 0
            observed = (dap + cash) if (dap is not None and kind in ("newcar", "agency")) else None
            note, note_en, conf = offer.get("note", ""), offer.get("note_en", ""), offer.get("confidence", "中")
            urls += offer.get("urls") or []
        elif brand in p.get("agency_brands", []):
            kind, observed = "agency", dap
            note, note_en, conf = "代理制/直销固定价格，无公开折让", "Agency / direct-sales fixed price, no public discount", "中"
        else:
            kind = "est"
    factor = None
    if kind == "est" or (kind == "demo" and observed is None):
        kind = "est"
        lo, hi = p["est_range"]
        factor = round(random.Random(f"{p['seed']}:{cid}:{name}").uniform(lo, hi), 4)
        observed = round(dap * factor) if dap else None
        if not note:
            note, note_en = "无展车、折扣挂牌或成交记录，按 DAP × 随机系数估算", "No demo, discounted listing or settlement record; DAP x seeded random factor"
        conf = conf or "低"
    if observed is None or dap is None:
        tp_lo = tp_hi = tp_mid = None
    elif kind == "demo":
        tp_lo = min(dap, round(observed * p["uplift_low"]))
        tp_hi = min(dap, round(observed * p["uplift_high"]))
        tp_mid = round((tp_lo + tp_hi) / 2)
    else:
        tp_lo = tp_hi = tp_mid = round(observed)
    return {
        "cid": cid, "brand": brand, "model": model, "model_en": model_en, "tier": tier, "zeekr": zk, "own": is_zeekr,
        "variant": name, "variant_en": v.get("name_en"), "msrp": msrp, "dap": dap, "dap_src": dap_src, "dap_src_en": dap_src_en,
        "dap_state": dap_state, "kind": kind, "observed": observed, "note": note, "note_en": note_en, "range": rng,
        "tp_low": tp_lo, "tp_high": tp_hi, "tp": tp_mid,
        "disc_dap": (tp_mid / dap - 1) if (tp_mid and dap) else None,
        "disc_msrp": (tp_mid / msrp - 1) if (tp_mid and msrp) else None,
        "factor": factor, "confidence": conf, "urls": urls,
    }


def build() -> dict:
    comp = config("competitors.json")
    zk = config("zeekr_models.json")
    ev = config("tp_evidence.json")
    hist = load_json(DATA_DIR / "dap_history.json", {})
    p = ev.get("params") or {}
    p.setdefault("uplift_low", 1.03); p.setdefault("uplift_high", 1.06)
    p.setdefault("est_range", [0.92, 0.96]); p.setdefault("seed", 20261109); p.setdefault("agency_brands", [])
    emodels = ev.get("models") or {}
    rows: list[dict] = []
    for c in comp.get("competitors", []):
        if c.get("status") not in ("on_sale", "launching"):
            continue
        cid = c["id"]; em = emodels.get(cid) or {}
        offer = em.get("offer")
        replaced = {v.get("replaces") for v in em.get("variants", []) if v.get("replaces")}
        base = [v for v in c.get("variants", []) if v.get("price") is not None and v.get("name") not in replaced]
        for v in base:
            rows.append(_row(p, cid, c["brand"], c["model"], c.get("model_en") or c["model"], c.get("tier"), c.get("zeekr") or [], v, hist, offer))
        for v in em.get("variants", []):
            r = _row(p, cid, c["brand"], c["model"], c.get("model_en") or c["model"], c.get("tier"), c.get("zeekr") or [], v, hist, None)
            rows.append(r)
    # ZEEKR own models (reference rows)
    own: list[dict] = []
    for m in (zk.get("models") or []):
        if m.get("status") not in ("on_sale", "launching"):
            continue
        for v in m.get("variants", []):
            if v.get("rrp") is None:
                continue
            vv = {"name": v["name"], "msrp": v["rrp"]}
            own.append(_row(p, "zeekr-" + m["key"].lower(), "ZEEKR", m["name"], m.get("name_en") or m["name"], "own", [m["key"]], vv, hist, None, is_zeekr=True))
    # group by ZEEKR model
    groups: dict[str, list] = {}
    for r in rows:
        for z in r["zeekr"]:
            groups.setdefault(z, []).append(r)
    conf_rank = {"高": 0, "中": 1, "低–中": 2, "低-中": 2, "低": 3}
    for z in groups:
        # two-level sort: benchmark strength (core > reference > watch), then confidence (high > medium > low-medium > low)
        groups[z].sort(key=lambda r: ({"core": 0, "reference": 1, "watch": 2}.get(r["tier"], 3), conf_rank.get(r["confidence"], 4),
                                      r["brand"], r["model"], r["msrp"] or 0))
    # summary per group: median discount vs DAP among evidence-backed rows
    summary = {}
    for z, rs in groups.items():
        ev_rows = [r for r in rs if r["kind"] in ("demo", "newcar") and r["disc_dap"] is not None]
        all_rows = [r for r in rs if r["disc_dap"] is not None]
        def med(xs):
            xs = sorted(xs); n = len(xs)
            return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)
        summary[z] = {"n": len(rs), "n_evidence": len(ev_rows), "n_est": sum(1 for r in rs if r["kind"] == "est"),
                      "n_agency": sum(1 for r in rs if r["kind"] == "agency"),
                      "median_disc_evidence": med([r["disc_dap"] for r in ev_rows]), "median_disc_all": med([r["disc_dap"] for r in all_rows])}
    evidence = {cid: em.get("evidence", []) for cid, em in emodels.items() if em.get("evidence")}
    return {"generated": now_iso(), "as_of": ev.get("as_of"), "params": p, "groups": groups, "own": own, "summary": summary, "evidence": evidence}


def run_all():
    out = build()
    save_json(DATA_DIR / "tp.json", out)
    n = sum(len(v) for v in out["groups"].values())
    return {"rows": n, "groups": {k: len(v) for k, v in out["groups"].items()}}


if __name__ == "__main__":
    print(run_all())
