from __future__ import annotations

import logging
import re
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

_ALLOWED_CATEGORIES = {"GRAMMAR", "MISC"}

_TECH_RE = re.compile(
    r'^(?:'
    r'[A-Z]{2,}'
    r'|[A-Z]\w*[A-Z]\w*'
    r'|\w*\d\w*'
    r')$'
)


def _is_tech_term(word: str) -> bool:
    return bool(_TECH_RE.match(word))


def correct_text(text: str, lt_url: str, lang: str = "fr") -> str:
    """
    Corrige les fautes de grammaire via LanguageTool.
    lang : "fr" pour français, "en-US" pour anglais.
    Retourne le texte original si LanguageTool est indisponible.
    """
    if not text or not text.strip():
        return text
    try:
        resp = requests.post(
            f"{lt_url.rstrip('/')}/v2/check",
            data={"text": text, "language": lang},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("LanguageTool indisponible — correction ignorée : %s", exc)
        return text

    matches = resp.json().get("matches", [])
    corrected = text
    for match in sorted(matches, key=lambda m: m["offset"], reverse=True):
        category = match.get("rule", {}).get("category", {}).get("id", "")
        rule_id  = match.get("rule", {}).get("id", "?")
        replacements = match.get("replacements", [])
        offset = match["offset"]
        length = match["length"]
        original_word = text[offset : offset + length]

        if category not in _ALLOWED_CATEGORIES:
            logger.warning("LT ignoré (cat=%s rule=%s) : %r", category, rule_id, original_word)
            continue
        if not replacements:
            continue
        if _is_tech_term(original_word):
            continue
        replacement = replacements[0]["value"]
        logger.warning("LT corrige : %r → %r  (cat=%s rule=%s)", original_word, replacement, category, rule_id)
        corrected = corrected[:offset] + replacement + corrected[offset + length:]

    return corrected


def fix_verb_coordination_fr(text: str) -> str:
    """
    Corrige 'Analyse et résolu' → 'Analysé et résolu'.
    Règle 1er groupe : mot majuscule finissant en -e + "et" + participe passé → -e → -é.
    """
    _PATTERN = re.compile(
        r'(?<![a-zà-üé])'
        r'([A-ZÀ-Ü][a-zà-ü]{2,}[^éèêëàùa-z]?e)'
        r'(\s+et\s+[a-zà-üé]{3,}(?:é|u|is|it)\b)',
        re.UNICODE,
    )

    def _replace(m: re.Match) -> str:
        verb, rest = m.group(1), m.group(2)
        return verb[:-1] + "é" + rest

    return _PATTERN.sub(_replace, text)


def correct_cv(generated: Dict[str, Any], lt_url: str, language: str = "fr") -> Dict[str, Any]:
    """
    Applique la correction grammaticale sur le résumé et les bullets.
    language : "fr" (français) ou "en" (anglais).
    """
    cv = generated.get("targeted_cv")
    if not isinstance(cv, dict):
        return generated

    lang_lt = "en-US" if language == "en" else "fr"

    if cv.get("professional_summary"):
        text = cv["professional_summary"]
        if language == "fr":
            text = fix_verb_coordination_fr(text)
        cv["professional_summary"] = correct_text(text, lt_url, lang=lang_lt)

    for bullet in cv.get("experience_bullets", []) or []:
        if isinstance(bullet, dict) and bullet.get("bullet"):
            b = bullet["bullet"]
            if language == "fr":
                b = fix_verb_coordination_fr(b)
            bullet["bullet"] = correct_text(b, lt_url, lang=lang_lt)

    return generated


# Alias rétrocompat
def correct_cv_french(generated: Dict[str, Any], lt_url: str) -> Dict[str, Any]:
    return correct_cv(generated, lt_url, language="fr")
