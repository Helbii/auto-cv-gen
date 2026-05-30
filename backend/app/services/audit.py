"""
Audit anti-hallucination du CV généré et résolution des contenus safe
(titre, résumé, email) en cas de claim interdit détecté.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from .text_utils import normalize_text


def contains_forbidden_claim(text: str, forbidden_claims: List[str]) -> List[str]:
    found = []
    text_lower = normalize_text(text)
    for claim in forbidden_claims:
        normalized_claim = normalize_text(str(claim).strip())
        # Ignorer les claims trop courts — mots grammaticaux ("une", "les", "api"...)
        # qui matcheraient n'importe quel texte naturel
        if not normalized_claim or len(normalized_claim) <= 3:
            continue
        if normalized_claim in text_lower:
            found.append(claim)
    return found


def contains_unsupported_claim(text: str, forbidden_claims: List[str]) -> List[str]:
    found = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", str(text))
    claim_words = ["maitrise", "expertise", "expert", "experience en", "competence en", "specialise", "developpement en"]
    safe_words = ["poste", "candidature", "formation", "apprentissage", "environnement", "souhaite", "interesse"]

    for claim in forbidden_claims:
        normalized_claim = normalize_text(str(claim).strip())
        if not normalized_claim:
            continue
        for sentence in sentences:
            normalized_sentence = normalize_text(sentence)
            if normalized_claim not in normalized_sentence:
                continue
            has_claim_word = any(word in normalized_sentence for word in claim_words)
            has_safe_word = any(word in normalized_sentence for word in safe_words)
            if has_claim_word and not has_safe_word:
                found.append(claim)
                break
    return found


def validate_generated_cv(
    generated: Dict[str, Any],
    allowed_ids: Set[str],
    forbidden_claims: List[str],
) -> Dict[str, Any]:
    cv = generated.get("targeted_cv", {})
    valid_bullets, rejected_bullets = [], []

    for item in cv.get("experience_bullets", []):
        bullet = item.get("bullet", "")
        evidence_ids = item.get("evidence_ids", [])
        status = item.get("status", "")
        invalid_reasons = []
        if status not in ["CONFIRMED", "TRANSFERABLE"]:
            invalid_reasons.append("Statut non autorise")
        if not evidence_ids:
            invalid_reasons.append("Aucune preuve citee")
        unknown_ids = [eid for eid in evidence_ids if eid not in allowed_ids]
        if unknown_ids:
            invalid_reasons.append(f"Preuves non autorisees : {unknown_ids}")
        forbidden_found = contains_forbidden_claim(bullet, forbidden_claims)
        if forbidden_found:
            invalid_reasons.append(f"Contient des elements interdits : {forbidden_found}")
        if invalid_reasons:
            rejected_bullets.append({"bullet": bullet, "reasons": invalid_reasons, "original_item": item})
        else:
            valid_bullets.append(item)

    valid_skills, rejected_skills = [], []
    for item in cv.get("skills_to_display", []):
        skill = item.get("skill", "")
        evidence_ids = item.get("evidence_ids", [])
        invalid_reasons = []
        if not evidence_ids:
            invalid_reasons.append("Aucune preuve citee")
        unknown_ids = [eid for eid in evidence_ids if eid not in allowed_ids]
        if unknown_ids:
            invalid_reasons.append(f"Preuves non autorisees : {unknown_ids}")
        forbidden_found = contains_forbidden_claim(skill, forbidden_claims)
        if forbidden_found:
            invalid_reasons.append(f"Contient des elements interdits : {forbidden_found}")
        if invalid_reasons:
            rejected_skills.append({"skill": skill, "reasons": invalid_reasons, "original_item": item})
        else:
            valid_skills.append(item)

    email = cv.get("application_email", {})
    # Couvre le nouveau format structuré (accroche/preuves/motivation) et l'ancien (body)
    email_text = " ".join(str(email.get(k, "")) for k in
                          ["subject", "accroche", "preuves", "motivation", "body"])
    return {
        "valid_bullets": valid_bullets,
        "rejected_bullets": rejected_bullets,
        "valid_skills": valid_skills,
        "rejected_skills": rejected_skills,
        "title_forbidden_claims": contains_forbidden_claim(cv.get("title", ""), forbidden_claims),
        "summary_forbidden_claims": contains_unsupported_claim(cv.get("professional_summary", ""), forbidden_claims),
        "email_forbidden_claims": contains_unsupported_claim(email_text, forbidden_claims),
    }


def build_safe_summary(audit: Dict[str, Any], matching: Dict[str, Any] | None = None) -> str:
    matching = matching or {}
    skills = [item.get("skill", "") for item in audit.get("valid_skills", []) if item.get("skill")]
    title = (
        matching.get("safe_recommended_title", "")
        or matching.get("recommended_title", "")
        or "Développeur"
    )
    sector = matching.get("offer_sector", "")

    if skills:
        skills_str = ", ".join(skills[:4])
        summary = f"{title} avec expériences documentées en {skills_str}."
        if sector:
            summary += f" Expérience applicable au contexte {sector}."
        return summary

    return (
        f"{title} avec expériences documentées en développement logiciel, "
        "support applicatif et analyse technique."
    )


def _is_valid_title(text: str) -> bool:
    """Un titre valide est court (≤ 12 mots) et non vide."""
    return bool(text) and len(text.split()) <= 12


def resolve_safe_title(matching: Dict[str, Any], generated: Dict[str, Any], audit: Dict[str, Any]) -> str:
    cv = generated.get("targeted_cv", {})

    safe = matching.get("safe_recommended_title", "")
    llm_title = cv.get("title", "")
    recommended = matching.get("recommended_title", "")

    # Ordre de priorité : safe > LLM title > recommended — chacun validé par longueur
    for candidate in [safe, llm_title, recommended]:
        if _is_valid_title(candidate):
            title = candidate
            break
    else:
        title = "CV cible"

    # Si le titre contient un claim interdit, retomber sur le titre safe ou recommended
    if audit.get("title_forbidden_claims"):
        for candidate in [safe, recommended]:
            if _is_valid_title(candidate):
                title = candidate
                break
        else:
            title = "CV cible"

    return title


def resolve_safe_summary(
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    matching: Dict[str, Any] | None = None,
) -> str:
    matching = matching or {}
    cv = generated.get("targeted_cv", {})
    summary = cv.get("professional_summary", "")
    if audit.get("summary_forbidden_claims"):
        summary = build_safe_summary(audit, matching)
    return summary


def _assemble_cover_letter(accroche: str, preuves: str, motivation: str) -> str:
    """Assemble une lettre de motivation : formule d'appel + 3 paragraphes + clôture."""
    paragraphs = [p.strip() for p in (accroche, preuves, motivation) if p and p.strip()]
    parts = ["Madame, Monsieur,", *paragraphs, "Cordialement,"]
    return "\n\n".join(parts)


def resolve_safe_email(matching: Dict[str, Any], generated: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, str]:
    cv = generated.get("targeted_cv", {})
    title = resolve_safe_title(matching, generated, audit)
    email = cv.get("application_email", {})

    subject = email.get("subject", "") or f"Candidature - {title}"
    accroche = email.get("accroche", "")
    preuves = email.get("preuves", "")
    motivation = email.get("motivation", "")

    if audit.get("email_forbidden_claims"):
        # Fallback prudent : 3 paragraphes sûrs, aucune compétence non prouvée revendiquée
        subject = f"Candidature - {title}"
        accroche = f"Votre poste de {title} a retenu toute mon attention et correspond à mon projet professionnel."
        preuves = (
            "Mon parcours s'appuie sur des preuves concrètes en développement logiciel, support applicatif, "
            "analyse d'incidents et documentation technique, directement transposables aux besoins du poste."
        )
        motivation = (
            "Le contexte du poste correspond à ma capacité de montée en compétence rapide sur les technologies "
            "de votre environnement. Je me tiens à votre disposition pour un entretien."
        )

    if accroche or preuves or motivation:
        body = _assemble_cover_letter(accroche, preuves, motivation)
    else:
        # Compat ancien format (entrées d'historique antérieures)
        body = email.get("body", "")

    return {"subject": subject, "body": body}
