import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

from .esco import esco_normalize
from .semantic_graph import expand_text_with_graph
from .storage import get_connection, load_all_evidence
from .text_utils import normalize_text, unique_tokens, token_counts

IMPORTANT_CATEGORIES = {
    "profile",
    "profile_strength",
    "experience",
    "experience_mission",
    "experience_achievement",
    "experience_tech",
    "skill",
    "project",
    "project_skill",
}

# Catégories qui méritent un boost supplémentaire au scoring
SKILL_CATEGORIES = {"skill", "experience_tech", "project_tech"}


def quote_fts_token(token: str) -> str:
    return token.replace('"', '')


def build_fts_query(offer_counts: Dict[str, int], total_tokens: int, limit_tokens: int = 20) -> str:
    """
    Sélectionne les tokens FTS en pondérant par TF × longueur.
    Un token qui revient souvent dans l'offre ET qui est long (donc spécifique)
    est prioritaire par rapport à un hapax court.
    """
    if not offer_counts or total_tokens == 0:
        return ""

    def score(token: str, count: int) -> float:
        tf = count / total_tokens
        length_bonus = min(len(token), 10) / 10  # normalisé entre 0.3 et 1.0
        return tf * length_bonus

    ranked = sorted(offer_counts.items(), key=lambda x: -score(x[0], x[1]))
    top_tokens = [t for t, _ in ranked[:limit_tokens]]
    return " OR ".join(quote_fts_token(t) for t in top_tokens)


_idf_cache: dict = {"key": None, "idf": {}}


def _compute_idf(all_evidence: List[Dict[str, Any]]) -> Dict[str, float]:
    """IDF lissé : log((N+1) / (df+1)) — résultat mis en cache par empreinte du corpus."""
    cache_key = tuple(ev["id"] for ev in all_evidence)
    if cache_key == _idf_cache["key"]:
        return _idf_cache["idf"]

    N = len(all_evidence)
    doc_freq: Dict[str, int] = {}
    for ev in all_evidence:
        full_text = f"{ev['category']} {ev['source']} {ev['field']} {ev['text']}"
        for tok in unique_tokens(full_text):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    idf = {tok: math.log((N + 1) / (df + 1)) for tok, df in doc_freq.items()}

    _idf_cache["key"] = cache_key
    _idf_cache["idf"] = idf
    return idf


def expand_offer_for_retrieval(job_offer: str) -> str:
    return esco_normalize(expand_text_with_graph(job_offer))


def retrieve_relevant_evidence(sqlite_path: Path, job_offer: str, top_k: int = 30) -> List[Dict[str, Any]]:
    all_evidence = load_all_evidence(sqlite_path)
    evidence_by_id = {ev["id"]: ev for ev in all_evidence}

    scores: Dict[str, float] = {}
    expanded_offer = expand_offer_for_retrieval(job_offer)
    normalized_offer = normalize_text(expanded_offer)

    # ── Prépare TF de l'offre ────────────────────────────────────────────────
    offer_counts = token_counts(expanded_offer)            # Counter avec répétitions
    total_offer_tokens = max(sum(offer_counts.values()), 1)
    offer_tokens = set(offer_counts.keys())                # set pour les intersections

    # ── Prépare IDF sur le corpus de preuves ─────────────────────────────────
    idf = _compute_idf(all_evidence)

    def tfidf_weight(token: str) -> float:
        tf = offer_counts.get(token, 0) / total_offer_tokens
        return tf * idf.get(token, 0.0)

    # ── 1) FTS rapide (query pondérée par TF×longueur) ───────────────────────
    query = build_fts_query(offer_counts, total_offer_tokens)
    if query:
        try:
            with get_connection(sqlite_path) as conn:
                rows = conn.execute(
                    """
                    SELECT id, rank
                    FROM evidence_fts
                    WHERE evidence_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, top_k * 3),
                ).fetchall()
                for idx, row in enumerate(rows):
                    scores[row["id"]] = scores.get(row["id"], 0) + max(1, top_k * 3 - idx)
        except Exception as exc:
            logger.warning("Recherche FTS échouée (scoring TF-IDF seul) : %s", exc)

    # ── 2) Scoring TF-IDF (remplace le simple comptage de tokens) ────────────
    for ev in all_evidence:
        full_text = esco_normalize(f"{ev['category']} {ev['source']} {ev['field']} {ev['text']}")
        ev_tokens = unique_tokens(full_text)
        overlap = offer_tokens.intersection(ev_tokens)
        if not overlap:
            continue

        # Somme des poids TF-IDF pour les tokens en commun
        raw = sum(tfidf_weight(tok) for tok in overlap)

        # Multiplicateurs catégorie (préservés de l'ancienne logique)
        if ev["category"] in IMPORTANT_CATEGORIES:
            raw *= 1.5
        if ev["category"] in SKILL_CATEGORIES:
            raw *= 2.0

        scores[ev["id"]] = scores.get(ev["id"], 0) + raw * 200

    # ── 3) Match exact de compétences (+25 fixe, inchangé) ───────────────────
    for ev in all_evidence:
        if ev["category"] not in {"skill", "experience_tech", "project_skill", "profile_strength"}:
            continue
        normalized_evidence = esco_normalize(ev["text"])
        if not normalized_evidence:
            continue
        if len(normalized_evidence) <= 4:
            is_match = re.search(r"\b" + re.escape(normalized_evidence) + r"\b", normalized_offer) is not None
        else:
            is_match = normalized_evidence in normalized_offer
        if is_match:
            scores[ev["id"]] = scores.get(ev["id"], 0) + 25

    # ── Tri et sélection ─────────────────────────────────────────────────────
    ranked: List[Tuple[float, str]] = sorted(
        ((score, eid) for eid, score in scores.items()), reverse=True
    )
    selected = [evidence_by_id[eid] for _, eid in ranked[:top_k] if eid in evidence_by_id]

    # ── Compléter jusqu'à top_k (priorité catégorie) ─────────────────────────
    FILL_PRIORITY = [
        "skill", "experience_tech", "project_tech", "project_skill",
        "profile_strength", "experience_mission", "experience_achievement",
        "profile", "experience", "project",
    ]
    existing = {ev["id"] for ev in selected}
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for ev in all_evidence:
        if ev["id"] not in existing:
            by_category.setdefault(ev["category"], []).append(ev)

    for cat in FILL_PRIORITY:
        for ev in by_category.get(cat, []):
            if len(selected) >= top_k:
                break
            selected.append(ev)
            existing.add(ev["id"])
        if len(selected) >= top_k:
            break

    if len(selected) < top_k:
        for ev in all_evidence:
            if ev["id"] not in existing:
                selected.append(ev)
                existing.add(ev["id"])
            if len(selected) >= top_k:
                break

    return selected[:top_k]
