import re
import unicodedata
from collections import Counter
from typing import Set


_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou",
    "a", "au", "aux", "en", "pour", "par", "avec", "sur", "dans", "ce",
    "cet", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "vous", "nous",
    "ils", "elles", "il", "elle", "etre", "avoir", "poste", "profil", "mission",
    "missions", "competence", "competences", "experience", "experiences", "candidat",
    "candidature", "homme", "femme", "h", "f", "hf"
}


def normalize_text(text: str) -> str:
    text = str(text).lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("’", "’")
    return text


def _raw_words(text: str):
    normalized = normalize_text(text)
    return [w for w in re.findall(r"[a-zA-Z0-9+#.\-/]+", normalized)
            if len(w) >= 3 and w not in _STOPWORDS]


def simple_tokens(text: str) -> Set[str]:
    return set(_raw_words(text))


def token_counts(text: str) -> Counter:
    """Comme simple_tokens mais retourne les fréquences (avec répétitions)."""
    return Counter(_raw_words(text))
