from __future__ import annotations

import csv
import logging
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_NGRAM = 6
_synonym_map: Optional[Dict[str, str]] = None


def _norm(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _esco_path() -> Path:
    from ..core.config import settings
    return settings.esco_dict_path / "skills_fr.csv"


def _load() -> Dict[str, str]:
    global _synonym_map
    if _synonym_map is not None:
        return _synonym_map

    path = _esco_path()
    if not path.exists():
        logger.warning("ESCO introuvable : %s — normalisation synonymes désactivée.", path)
        _synonym_map = {}
        return _synonym_map

    result: Dict[str, str] = {}
    with open(path, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            preferred = _norm(row["preferredLabel"])
            if not preferred:
                continue
            for alt in (row.get("altLabels") or "").split("\n"):
                alt_n = _norm(alt.strip())
                if alt_n and len(alt_n) >= 3 and alt_n != preferred:
                    result[alt_n] = preferred

    _synonym_map = result
    logger.info("Index ESCO chargé : %d synonymes.", len(result))
    return result


def esco_normalize(text: str) -> str:
    """
    normalize_text + remplacement des synonymes ESCO par leur label canonique.
    Utilise une fenêtre glissante de n-grammes (taille max = _MAX_NGRAM, longest-match first).
    """
    from .text_utils import normalize_text
    normalized = normalize_text(text)
    synonym_map = _load()
    if not synonym_map:
        return normalized

    words = normalized.split()
    n = len(words)
    result: List[str] = []
    i = 0
    while i < n:
        matched = False
        for gram_size in range(min(_MAX_NGRAM, n - i), 0, -1):
            phrase = " ".join(words[i : i + gram_size])
            if phrase in synonym_map:
                result.append(synonym_map[phrase])
                i += gram_size
                matched = True
                break
        if not matched:
            result.append(words[i])
            i += 1
    return " ".join(result)
