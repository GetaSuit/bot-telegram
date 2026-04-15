"""
database.py — stockage local (JSON)
Pas besoin de base de données : deux fichiers JSON suffisent.
"""

import json
import os
from pathlib import Path

SEEN_FILE  = Path("data/seen_items.json")
FAVS_FILE  = Path("data/favorites.json")


def _load(path: Path) -> dict | list:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        return {} if "seen" in path.name else []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Articles déjà vus (évite les doublons d'alertes) ──────

def is_seen(url: str) -> bool:
    seen = _load(SEEN_FILE)
    return url in seen


def mark_seen(url: str, title: str):
    seen = _load(SEEN_FILE)
    seen[url] = title
    # Garde max 5000 entrées pour ne pas gonfler indéfiniment
    if len(seen) > 5000:
        keys = list(seen.keys())
        seen = {k: seen[k] for k in keys[-4000:]}
    _save(SEEN_FILE, seen)


# ── Favoris ───────────────────────────────────────────────

def add_favorite(item: dict):
    favs = _load(FAVS_FILE)
    # Dédupliquer par URL
    if any(f["url"] == item["url"] for f in favs):
        return False
    favs.append(item)
    _save(FAVS_FILE, favs)
    return True


def remove_favorite(url: str):
    favs = _load(FAVS_FILE)
    new = [f for f in favs if f["url"] != url]
    _save(FAVS_FILE, new)
    return len(favs) != len(new)


def list_favorites() -> list[dict]:
    return _load(FAVS_FILE)


def clear_seen():
    _save(SEEN_FILE, {})
