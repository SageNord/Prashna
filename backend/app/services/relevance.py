"""Deterministic UPSC screening and event-key helpers for source candidates."""
from __future__ import annotations

from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import re
import unicodedata


CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "Polity": ("constitution", "constitutional", "supreme court", "high court", "judgment", "judgement", "bill", "act", "parliament", "lok sabha", "rajya sabha", "election commission", "election", "governance", "federal", "fundamental right", "ordinance", "justice", "tribunal", "panchayat", "municipal", " lokpal", "cag", "comptroller"),
    "Economy": ("rbi", "reserve bank", "inflation", "monetary policy", "repo rate", "gdp", "fiscal", "budget", "tax", "gst", "sebi", "banking", "financial", "trade deficit", "exports", "imports", "employment", "unemployment", "economic survey", "investment", "rupee", "npas", "msme"),
    "IR": ("bilateral", "multilateral", "treaty", "convention", "summit", "foreign minister", "foreign affairs", "mea", "united nations", "un security council", "world bank", "imf", "wto", "brics", "g20", "sco", "quad", "indo-pacific", "international organisation", "international organization", "diplomatic", "geopolit"),
    "Environment": ("climate", "biodiversity", "wetland", "wildlife", "forest", "species", "conservation", "pollution", "renewable energy", "emission", "cop28", "cop29", "cop30", "unfccc", "paris agreement", "environment", "ecology", "national park", "biosphere", "carbon", "tiger reserve", "elephant reserve"),
    "Science": ("isro", "space mission", "satellite", "launch vehicle", "science", "technology", "artificial intelligence", "semiconductor", "quantum", "biotechnology", "genome", "vaccine", "research", "innovation", "digital public infrastructure", "cybersecurity", "telecom", "deep sea", "nuclear energy"),
    "Geography": ("earthquake", "cyclone", "monsoon", "glacier", "river basin", "geological", "geography", "landslide", "flood", "drought", "coastal", "himalaya", "arctic", "ocean current", "disaster management"),
    "Society": ("public health", "health ministry", "education policy", "school education", "higher education", "nutrition", "census", "poverty", "social justice", "gender", "tribal", "scheduled caste", "scheduled tribe", "disability", "demographic", "migration", "women and child"),
    "Security": ("internal security", "terrorism", "terrorist", "border security", "defence", "defense", "armed forces", "military", "cyber attack", "cyberattack", "insurgency", "naxal", "left wing extremism", "coast guard", "missile", "drone"),
    "Agriculture": ("agriculture", "farmer", "farmers", "crop", "minimum support price", "msp", "food security", "food grain", "fertiliser", "fertilizer", "irrigation", "fisheries", "animal husbandry", "agri"),
    "Schemes": ("government scheme", "central scheme", "centrally sponsored", "yojana", "mission mode", "cabinet approves", "cabinet approved", "national mission", "pms", "pm-kisan", "pm kisan", "ayushman bharat", "pib"),
    "Reports & Indices": ("report", "index", "indices", "survey", "ranked", "ranking", "global hunger", "human development", "annual report", "assessment", "statistics", "data release"),
}

IGNORE_TERMS = ("celebrity", "box office", "film star", "movie review", "reality show", "fashion week", "cricket match", "football match", "ipl match", "sports result", "horoscope", "recipe", "lifestyle", "viral video", "gossip")
HIGH_SIGNAL_TERMS = ("supreme court", "constitution", "rbi", "sebi", "isro", "cabinet approves", "parliament", "treaty", "climate change", "national park", "government scheme", "budget", "monetary policy", "election commission", "united nations", "world bank", "imf", "report", "index")


def classify_relevance(title: str, summary: str = "") -> tuple[int, str, str | None]:
    text = normalize_title(f"{title} {summary}")
    if any(term in text for term in IGNORE_TERMS):
        return 0, "LOW", None
    matches = [(category, [term for term in terms if term.strip() in text]) for category, terms in CATEGORY_TERMS.items()]
    matches = [(category, terms) for category, terms in matches if terms]
    if not matches:
        return 0, "LOW", None
    matches.sort(key=lambda item: (len(item[1]), item[0] in ("Polity", "Economy", "Environment", "Science", "IR")), reverse=True)
    signal_count = sum(len(terms) for _, terms in matches)
    high_signal = any(term in text for term in HIGH_SIGNAL_TERMS)
    score = min(96, 42 + min(signal_count, 4) * 9 + (16 if high_signal else 0))
    level = "HIGH" if score >= 67 else "MEDIUM"
    return score, level, matches[0][0]


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"\b(pib|press release|rbi press release)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def event_fingerprint(title: str, published_at: datetime | None) -> str:
    normalized = normalize_title(title)
    published_day = published_at.date().isoformat() if published_at else "undated"
    return sha256(f"{normalized}|{published_day}".encode()).hexdigest()


def title_similarity(left: str, right: str) -> float:
    left_norm, right_norm = normalize_title(left), normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens, right_tokens = set(left_norm.split()), set(right_norm.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return max(sequence, overlap)


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
