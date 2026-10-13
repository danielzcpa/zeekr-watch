"""Keyword classification: Zeekr model tags, complaint categories, severity,
competitor mentions, launch / price-policy signals.

Everything is rule-based and transparent so the finance team can audit why an
item was flagged. Lists are bilingual (English + Chinese) where relevant.
"""
from __future__ import annotations

import re

from .util import config

_MODELS = config("zeekr_models.json").get("models", [])
_COMPS = config("competitors.json").get("competitors", [])

# ---------------------------------------------------------------- Zeekr models
_MODEL_PATTERNS: list[tuple[str, re.Pattern]] = []
for m in _MODELS:
    alts = sorted(set([m["name"].lower()] + m.get("aliases", [])), key=len, reverse=True)
    pats = []
    for a in alts:
        a_esc = re.escape(a)
        # short tokens like "7x" need word boundaries; "zeekr x" needs trailing boundary
        pats.append(rf"(?<![a-z0-9]){a_esc}(?![a-z0-9])")
    _MODEL_PATTERNS.append((m["key"], re.compile("|".join(pats), re.I)))

# bare "X" is ambiguous - only count ZEEKR X when "zeekr x" appears, handled via aliases above.


def zeekr_models(text: str) -> list[str]:
    t = text.lower()
    found = [k for k, p in _MODEL_PATTERNS if p.search(t)]
    return found


ZEEKR_RE = re.compile(r"zeekr|极氪|zekr", re.I)


def mentions_zeekr(text: str) -> bool:
    return bool(ZEEKR_RE.search(text))


# ------------------------------------------------------------- competitors
_COMP_PATTERNS: list[tuple[str, re.Pattern]] = []
for c in _COMPS:
    brand = c["brand"].split(" (")[0]
    model = re.sub(r"\s*\(.*?\)", "", c["model"])
    model = re.sub(r"（.*?）", "", model)
    # split "iX1 / iX2" style
    models = [x.strip() for x in re.split(r"/|／", model) if x.strip()]
    pats = []
    for mdl in models:
        mdl_core = mdl.split("（")[0].strip()
        # Take ASCII part only (e.g. "EV4 轿车" -> "EV4")
        mdl_ascii = re.sub(r"[^\x00-\x7f]+", " ", mdl_core).strip()
        if not mdl_ascii:
            continue
        pats.append(rf"{re.escape(brand.lower())}\s*{re.escape(mdl_ascii.lower())}(?![a-z0-9])")
        # model-only when distinctive (>=3 chars and contains a digit or is multiword)
        if len(mdl_ascii) >= 3 and (re.search(r"\d", mdl_ascii) or " " in mdl_ascii):
            pats.append(rf"(?<![a-z0-9]){re.escape(mdl_ascii.lower())}(?![a-z0-9])")
    if pats:
        _COMP_PATTERNS.append((c["id"], re.compile("|".join(pats), re.I)))

_BRAND_SPECIAL = {
    "smart": r"smart\s*#\s?[135]\b|smart\s+(?:brabus|australia|ev\b|suv|electric)",
    "mini": r"\bmini\s+(?:aceman|countryman|cooper|jcw|electric|ev\b)",
    "im": r"\bim5\b|\bim6\b|\bim\s+motor",
    "gac": r"\bgac\b|\baion\b",
}
_BRAND_PATTERNS: dict[str, re.Pattern] = {}
for c in _COMPS:
    b = c["brand"].split(" (")[0].lower()
    if b in _BRAND_PATTERNS:
        continue
    if b in _BRAND_SPECIAL:
        _BRAND_PATTERNS[b] = re.compile(_BRAND_SPECIAL[b], re.I)
    else:
        _BRAND_PATTERNS[b] = re.compile(rf"(?<![a-z]){re.escape(b)}(?![a-z])", re.I)


def competitor_ids(text: str) -> list[str]:
    t = text.lower()
    return [cid for cid, p in _COMP_PATTERNS if p.search(t)]


def competitor_brands(text: str) -> list[str]:
    t = text.lower()
    return [b for b, p in _BRAND_PATTERNS.items() if p.search(t)]


# ------------------------------------------------------------- complaints
COMPLAINT_CATEGORIES: dict[str, dict] = {
    "quality": {
        "zh": "质量/故障", "en": "Quality / faults",
        "kw": ["fault", "faulty", "defect", "broke", "broken", "failure", "failed", "rattle", "rattling",
               "squeak", "noise", "leak", "leaking", "warning light", "error", "won't start", "wont start",
               "stuck", "stopped working", "not working", "doesn't work", "doesnt work", "issue with", "problem with",
               "panel gap", "paint", "scratch", "creak", "vibration", "steering", "brake", "suspension",
               "故障", "异响", "漏", "坏了", "问题", "质量"],
    },
    "software": {
        "zh": "软件/APP/车机", "en": "Software / app / infotainment",
        "kw": ["app", "software", "ota", "update", "bug", "glitch", "crash", "crashes", "freeze", "frozen",
               "screen", "infotainment", "bluetooth", "carplay", "android auto", "digital key", "phone key",
               "reboot", "lag", "laggy", "unresponsive", "login", "log in", "sign in", "account", "connectivity",
               "软件", "车机", "死机", "卡顿", "升级", "钥匙"],
    },
    "charging": {
        "zh": "充电/续航/电池", "en": "Charging / range / battery",
        "kw": ["charging", "charger", "charge", "range", "battery", "kwh", "efficiency", "consumption",
               "dc fast", "wallbox", "wall box", "v2l", "degradation", "12v", "充电", "续航", "电池", "电耗"],
    },
    "delivery": {
        "zh": "交付/等待/订单", "en": "Delivery / waiting / orders",
        "kw": ["delivery", "delivered", "delay", "delayed", "waiting", "wait time", "eta", "order", "ordered",
               "shipping", "ship", "stock", "backorder", "allocation", "build date", "交付", "交车", "等车", "延迟", "订单"],
    },
    "service": {
        "zh": "售后/服务/保修", "en": "After-sales / service / warranty",
        "kw": ["service", "servicing", "dealer", "dealership", "warranty", "repair", "repaired", "parts",
               "spare parts", "support", "customer service", "response", "no response", "ignored", "technician",
               "booked", "booking", "loan car", "courtesy car", "售后", "服务", "保修", "维修", "配件", "经销商", "4s"],
    },
    "price": {
        "zh": "价格/贬值/退款", "en": "Price / resale / refund",
        "kw": ["price cut", "price drop", "dropped the price", "resale", "depreciation", "refund", "deposit",
               "overpriced", "expensive", "value", "trade-in", "trade in", "降价", "贬值", "退款", "定金", "保值"],
    },
    "safety": {
        "zh": "召回/安全", "en": "Recall / safety",
        "kw": ["recall", "recalled", "safety", "airbag", "fire", "smoke", "accident", "crash test", "ancap",
               "adas", "emergency braking", "phantom braking", "lane keep", "召回", "安全", "起火", "刹车"],
    },
    "sales": {
        "zh": "销售体验", "en": "Sales experience",
        "kw": ["salesperson", "sales person", "sales rep", "sales team", "test drive", "quote", "pushy",
               "misleading", "lied", "promised", "showroom", "销售", "试驾", "报价", "误导"],
    },
}

NEGATIVE_KW = [
    "worst", "terrible", "awful", "horrible", "disappointed", "disappointing", "frustrated", "frustrating",
    "annoying", "useless", "regret", "avoid", "never again", "nightmare", "poor", "bad", "unacceptable",
    "ridiculous", "joke", "scam", "lemon", "complaint", "complain", "unhappy", "angry", "furious", "rubbish",
    "garbage", "pathetic", "disgrace", "shocking", "waste", "don't buy", "dont buy", "do not buy", "warning",
    "beware", "stay away", "failed", "fail", "broken", "not working", "no response", "ignored", "still waiting",
    "months", "weeks", "fault", "faulty", "issue", "issues", "problem", "problems", "defect", "recall",
    "糟糕", "失望", "垃圾", "后悔", "投诉", "差", "坑", "骗", "别买", "不要买", "无人回复", "没人管",
]
POSITIVE_KW = [
    "love", "loving", "great", "excellent", "amazing", "fantastic", "happy", "impressed", "recommend",
    "best", "awesome", "brilliant", "smooth", "no issues", "no problems", "satisfied", "worth it", "perfect",
    "喜欢", "满意", "推荐", "好评", "不错", "很棒",
]

_CAT_RES = {k: re.compile("|".join(re.escape(w) for w in v["kw"]), re.I) for k, v in COMPLAINT_CATEGORIES.items()}
_NEG_RE = re.compile("|".join(re.escape(w) for w in NEGATIVE_KW), re.I)
_POS_RE = re.compile("|".join(re.escape(w) for w in POSITIVE_KW), re.I)


def complaint_categories(text: str) -> list[str]:
    return [k for k, r in _CAT_RES.items() if r.search(text)]


def sentiment(text: str, rating: float | None = None) -> dict:
    """Returns {score, label} where score<0 is negative. Rating (1-5) dominates when present."""
    neg = len(_NEG_RE.findall(text))
    pos = len(_POS_RE.findall(text))
    score = pos - neg
    if rating is not None:
        if rating <= 2:
            score = min(score, -3)
        elif rating == 3:
            score = min(score, -1)
        elif rating >= 4:
            score = max(score, 1)
    label = "negative" if score < 0 else ("positive" if score > 0 else "neutral")
    return {"score": score, "neg_hits": neg, "pos_hits": pos, "label": label}


def severity(text: str, sent: dict, rating: float | None, cats: list[str]) -> str:
    """high / medium / low."""
    t = text.lower()
    if "safety" in cats and re.search(r"recall|fire|smoke|airbag|brake fail|phantom braking|accident", t):
        return "high"
    if rating is not None and rating <= 1:
        return "high"
    if sent["neg_hits"] >= 4 or (rating is not None and rating <= 2):
        return "high" if sent["neg_hits"] >= 6 else "medium"
    if sent["label"] == "negative":
        return "medium" if sent["neg_hits"] >= 2 else "low"
    return "low"


def is_complaint(text: str, rating: float | None = None) -> bool:
    s = sentiment(text, rating)
    return s["label"] == "negative"


# ------------------------------------------------------------- launches / offers
LAUNCH_KW = ["launch", "launches", "launched", "launching", "arrives", "arrival", "on sale", "goes on sale",
             "priced", "pricing", "price and specs", "prices and specs", "revealed", "reveal", "confirmed for australia",
             "confirmed", "orders open", "order books", "pre-order", "pre-orders", "deliveries", "first deliveries",
             "debut", "debuts", "lands", "landing", "arriving", "coming to australia", "heading to australia",
             "australian launch", "australia launch", "unveiled", "new entrant", "new brand", "enters australia",
             "to australia", "for australia", "locked in"]
OFFER_KW = ["drive-away", "driveaway", "drive away", "cashback", "cash back", "finance offer", "special offer",
            "launch offer", "introductory offer", "limited time offer", "offers and deals", "comparison rate",
            "discount", "rebate", "free charging", "free servicing", "free wallbox", "free wall box", "runout",
            "run-out", "eofy", "clearance", "incentive", "trade-in bonus", "trade in bonus", "novated", "sharpened",
            "bonus", "优惠", "返现", "金融", "全包价"]
PRICE_CUT_KW = ["price cut", "price cuts", "price drop", "price drops", "slashes", "slashed", "slashing", "cuts price",
                "cut price", "cuts the price", "cheaper", "now cheaper", "price reduction", "reduces price", "undercuts",
                "undercut", "降价", "下调"]
PRICE_RISE_KW = ["price rise", "price rises", "price hike", "price hikes", "price increase", "price increases",
                 "more expensive", "pricier", "prices up", "price bump", "涨价", "上调"]
_LAUNCH_RE = re.compile("|".join(re.escape(w) for w in LAUNCH_KW), re.I)
_OFFER_RE = re.compile("|".join(re.escape(w) for w in OFFER_KW), re.I)
_CUT_RE = re.compile("|".join(re.escape(w) for w in PRICE_CUT_KW), re.I)
_RISE_RE = re.compile("|".join(re.escape(w) for w in PRICE_RISE_KW), re.I)
EV_RE = re.compile(r"\b(?:electric|ev|evs|bev|phev|plug-in|hybrid|range-extender|reev|kwh|charging)\b", re.I)
AU_RE = re.compile(r"australia|aussie|\bau\b|sydney|melbourne|brisbane|perth|adelaide|canberra|\bnsw\b|victoria|queensland|tasmania|drive-away|driveaway|ancap|novated", re.I)
AU_OUTLETS = re.compile(r"drive|carexpert|carsguide|whichcar|chasing cars|the driven|ev central|evcentral|zecar|carsauce|the beep|thebeep|carsales|caradvice|canberra times|newcastle herald|illawarra mercury|the advertiser|port news|bendigo advertiser|border mail|whirlpool|ozbargain|productreview|app store \(au\)|google play \(au\)|google 地图|zeekr australia|news\.com\.au|\.com\.au|goauto|motoring|torquecafe|evee|gridly|cars24|wheels|4x4 australia|babydrive|r/(?:zeekr7xaustralia|zeekraustralianz|carsaustralia|australianev|evaustralia|ausautomotive|ausev)", re.I)
LISTING_RE = re.compile(r"for sale\s*-\s*drive\.com\.au|\bfor sale\b.*(?:wagon|sedan|suv|hatch)|used \d{4}", re.I)
_RATE_RE = re.compile(r"\d{1,2}(?:\.\d{1,2})?\s?%\s?(?:p\.?a\.?|per annum|comparison)", re.I)


def signals(text: str) -> list[str]:
    out = []
    if _LAUNCH_RE.search(text):
        out.append("launch")
    if _OFFER_RE.search(text) or _RATE_RE.search(text):
        out.append("offer")
    if _CUT_RE.search(text):
        out.append("price_cut")
    if _RISE_RE.search(text):
        out.append("price_rise")
    if re.search(r"\$\s?\d{2,3},\d{3}", text):
        out.append("price")
    return out


def is_ev_context(text: str) -> bool:
    return bool(EV_RE.search(text))


def is_au(text: str, source_name: str, url: str) -> bool:
    if ".au/" in url or url.endswith(".au"):
        return True
    if AU_RE.search(text):
        return True
    return bool(AU_OUTLETS.search(source_name))


def is_listing(title: str) -> bool:
    return bool(LISTING_RE.search(title))
