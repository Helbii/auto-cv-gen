import json
from typing import Any, Dict, List, Optional


def _format_evidence_compact(evidence_bank: List[Dict[str, Any]]) -> str:
    """ID | catégorie | texte (80 chars max) — ~70 % moins de tokens qu'un JSON indenté."""
    lines = []
    for ev in evidence_bank:
        text = (ev.get("text") or "").strip().replace("\n", " ")[:80]
        lines.append(f"{ev['id']} | {ev.get('category', '')} | {text}")
    return "\n".join(lines)


def _format_requirement_groups(
    requirement_groups: Dict[str, Dict[str, List[str]]]
) -> str:
    """
    Formate les groupes de preuves candidates par exigence.
    Format : exigence → direct: EV001, EV002 | proche: EV010 | contexte: EV021
    """
    lines = []
    for req, groups in requirement_groups.items():
        direct = groups.get("direct", [])
        near = groups.get("near", [])
        context = groups.get("context", [])
        parts = []
        if direct:
            parts.append(f"direct: {', '.join(direct)}")
        if near:
            parts.append(f"proche: {', '.join(near)}")
        if context:
            parts.append(f"contexte: {', '.join(context)}")
        suffix = " → " + " | ".join(parts) if parts else " → (aucune preuve candidate)"
        lines.append(f"{req}{suffix}")
    return "\n".join(lines)


MATCHING_SCHEMA = {
    "type": "object",
    "required": [
        "recommended_title",
        "matching_score",
        "job_keywords",
        "requirements_analysis",
        "confirmed_skill_evidence_ids",
        "transferable_skill_evidence_ids",
        "weak_or_missing_requirements",
        "forbidden_claims",
        "strategy",
    ],
    "properties": {
        "recommended_title": {"type": "string"},
        "matching_score": {"type": "integer"},
        "job_keywords": {"type": "array", "items": {"type": "string"}},
        "requirements_analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["requirement", "category", "status", "evidence_ids", "explanation", "cv_usage"],
                "properties": {
                    "requirement": {"type": "string"},
                    "category": {"type": "string"},
                    "status": {"type": "string", "enum": ["CONFIRMED", "TRANSFERABLE", "WEAK", "ABSENT"]},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"},
                    "cv_usage": {"type": "string", "enum": ["USE", "USE_CAREFULLY", "DO_NOT_CLAIM"]},
                },
            },
        },
        "confirmed_skill_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "transferable_skill_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "weak_or_missing_requirements": {"type": "array", "items": {"type": "string"}},
        "forbidden_claims": {"type": "array", "items": {"type": "string"}},
        "strategy": {"type": "string"},
    },
}


GENERATED_CV_SCHEMA = {
    "type": "object",
    "required": ["targeted_cv"],
    "properties": {
        "targeted_cv": {
            "type": "object",
            "required": [
                "title",
                "matching_score",
                "professional_summary",
                "skills_to_display",
                "experience_bullets",
                "weak_or_missing_skills",
                "risks",
                "application_email",
            ],
            "properties": {
                "title": {"type": "string"},
                "matching_score": {"type": "integer"},
                "professional_summary": {"type": "string"},
                "skills_to_display": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["skill", "evidence_ids"],
                        "properties": {
                            "skill": {"type": "string"},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "experience_bullets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["source", "bullet", "status", "evidence_ids"],
                        "properties": {
                            "source": {"type": "string"},
                            "bullet": {"type": "string"},
                            "status": {"type": "string", "enum": ["CONFIRMED", "TRANSFERABLE"]},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "weak_or_missing_skills": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "application_email": {
                    "type": "object",
                    "required": ["subject", "accroche", "preuves", "motivation"],
                    "properties": {
                        "subject": {"type": "string"},
                        "accroche": {"type": "string"},
                        "preuves": {"type": "string"},
                        "motivation": {"type": "string"},
                    },
                },
            },
        }
    },
}


def build_candidate_context(evidence_bank: List[Dict[str, Any]]) -> str:
    """
    Extrait un résumé du profil candidat depuis la banque de preuves.
    Produit un bloc court (< 5 lignes) pour contextualiser le prompt LLM.
    """
    identity: Dict[str, str] = {}
    profile_summary = ""
    experiences: List[str] = []
    exp_sources_seen: set = set()

    for ev in evidence_bank:
        cat   = ev.get("category", "")
        field = ev.get("field", "")
        text  = (ev.get("text") or "").strip()
        source = ev.get("source", "")
        if not text:
            continue

        if cat == "identity":
            identity[field] = text
        elif cat == "profile" and field == "summary" and not profile_summary:
            first = text.split(".")[0].strip()
            if 10 < len(first) < 220:
                profile_summary = first
        elif cat == "experience" and field in {"position", "poste"}:
            # Dédoublonne par source (une ligne par expérience)
            src_key = source.split(" - ")[0].strip()
            if src_key and src_key not in exp_sources_seen:
                exp_sources_seen.add(src_key)
                experiences.append(f"{src_key} ({text})")

    lines: List[str] = []
    nom    = identity.get("nom") or identity.get("name", "")
    titre  = identity.get("titre") or identity.get("current_title") or identity.get("titre_cible_principal", "")

    if nom or titre:
        lines.append("Candidat : " + " — ".join(p for p in [nom, titre] if p))
    if experiences:
        lines.append("Expériences : " + " · ".join(experiences[:3]))
    if profile_summary:
        lines.append(f"Profil : {profile_summary}.")

    return "\n".join(lines)


def build_matching_prompt(
    job_offer: str,
    evidence_bank: List[Dict[str, Any]],
    all_evidence: Optional[List[Dict[str, Any]]] = None,
    requirement_groups: Optional[Dict[str, Dict[str, List[str]]]] = None,
) -> str:
    candidate_ctx = build_candidate_context(all_evidence or evidence_bank)
    candidate_block = (
        f"\nPROFIL CANDIDAT (contexte global pour calibrer TRANSFERABLE vs ABSENT) :\n{candidate_ctx}\n"
        if candidate_ctx else ""
    )

    evidence_block = _format_evidence_compact(evidence_bank)

    if requirement_groups:
        groups_block = _format_requirement_groups(requirement_groups)
        return f"""
/no_think

Tu es un arbitre de matching CV ↔ offre.
{candidate_block}
MISSION : pour chaque exigence listée dans EXIGENCES ET PREUVES CANDIDATES,
juge avec les IDs proposés. Tu ne cherches pas d'autres preuves — tu arbitres.

STATUTS : CONFIRMED (preuve directe) | TRANSFERABLE (proche, même domaine) | WEAK (indirect) | ABSENT (rien de pertinent).
cv_usage : USE si CONFIRMED | USE_CAREFULLY si TRANSFERABLE | DO_NOT_CLAIM si WEAK/ABSENT.

RÈGLES :
- Utilise UNIQUEMENT les IDs fournis pour l'exigence concernée.
- explanation : une phrase ≤ 120 caractères.
- job_keywords : 15 mots-clés max.
- forbidden_claims : exigences WEAK ou ABSENT (12 max).
- Ne transforme jamais une absence en compétence.
- Ne mélange pas deux compétences proches (SQL ≠ PL/SQL).
- Remplis TOUTES les clés JSON demandées.

OFFRE D'EMPLOI :
\"\"\"
{job_offer}
\"\"\"

BANQUE DE PREUVES (ID | catégorie | texte) :
{evidence_block}

EXIGENCES ET PREUVES CANDIDATES :
{groups_block}

Réponds uniquement en JSON valide.
"""

    # Fallback : prompt original (sans groupes, format JSON complet)
    return f"""
/no_think

Tu es un assistant d'analyse de CV.
{candidate_block}
MISSION : comparer une offre d'emploi avec une banque de preuves issue d'un CV.

CONTRAINTE DE TAILLE :
- Analyse au maximum 12 exigences principales de l'offre.
- Garde les explications courtes : une phrase de 160 caracteres maximum.
- Limite job_keywords a 15 mots-cles maximum.
- Limite forbidden_claims aux 12 absences les plus importantes.

REGLES ABSOLUES :
- Remplis toutes les cles du JSON demande.
- Ne reponds jamais avec un JSON vide.
- N'invente aucune preuve.
- Ne transforme jamais une exigence de l'offre en competence du candidat.
- Utilise uniquement les preuves listees dans EVIDENCE_BANK.
- Chaque preuve utilisee doit etre citee par son id exact : EV001, EV002, etc.
- Si aucune preuve ne correspond, le statut doit etre ABSENT.
- Si la preuve est proche mais pas identique (meme domaine, outil similaire, competence transferable), le statut doit etre TRANSFERABLE.
- Si la preuve est faible ou indirecte, le statut doit etre WEAK.
- Si la preuve est directe, le statut doit etre CONFIRMED.
- Utilise le PROFIL CANDIDAT pour mieux qualifier TRANSFERABLE.
- Ne melange pas deux competences proches : SQL confirme ne veut pas dire PL/SQL confirme.

STATUTS AUTORISES : CONFIRMED, TRANSFERABLE, WEAK, ABSENT.
cv_usage : USE si CONFIRMED | USE_CAREFULLY si TRANSFERABLE | DO_NOT_CLAIM si WEAK ou ABSENT.

OFFRE D'EMPLOI :
\"\"\"
{job_offer}
\"\"\"

EVIDENCE_BANK :
{json.dumps(evidence_bank, ensure_ascii=False, indent=2)}

Reponds uniquement en JSON valide.
"""


def _condensed_matching(matching: Dict[str, Any]) -> str:
    """Résumé lisible du matching — remplace le json.dumps complet dans le prompt."""
    title    = matching.get("safe_recommended_title") or matching.get("recommended_title", "")
    score    = matching.get("matching_score", 0)
    training = matching.get("training_context", False)

    reqs     = matching.get("requirements_analysis", [])
    confirmed    = [r["requirement"] for r in reqs if r.get("status") == "CONFIRMED"]
    transferable = [r["requirement"] for r in reqs if r.get("status") == "TRANSFERABLE"]
    absent       = matching.get("weak_or_missing_requirements", [])[:6]
    ctx_terms    = matching.get("safe_context_terms", [])
    sector       = matching.get("offer_sector", "")

    lines = []
    if title:
        lines.append(f"Titre ciblé : {title}")
    lines.append(f"Score ATS : {score}/100")
    if sector:
        lines.append(f"Secteur / contexte de l'offre : {sector}")
    if confirmed:
        lines.append(f"CONFIRMÉES (USE) : {', '.join(confirmed[:10])}")
    if transferable:
        lines.append(f"TRANSFÉRABLES (USE_CAREFULLY) : {', '.join(transferable[:8])}")
    if absent:
        lines.append(f"ABSENTES — NE PAS REVENDIQUER : {', '.join(absent)}")
    if training:
        lines.append("Contexte offre : junior/formant → s'appuyer exclusivement sur les compétences CONFIRMÉES concrètes, sans revendiquer d'acquis sur les ABSENTES")
    if ctx_terms:
        lines.append(f"Termes contextuels sûrs à intégrer : {', '.join(ctx_terms[:6])}")
    return "\n".join(lines)


def build_generation_prompt(
    job_offer: str,
    matching: Dict[str, Any],
    allowed_evidence: List[Dict[str, Any]],
    forbidden_claims: List[str],
    all_evidence: Optional[List[Dict[str, Any]]] = None,
    retry_issues: Optional[List[str]] = None,
) -> str:
    candidate_ctx = build_candidate_context(all_evidence or allowed_evidence)
    candidate_block = f"""
PROFIL CANDIDAT :
{candidate_ctx}
""" if candidate_ctx else ""

    matching_summary = _condensed_matching(matching)

    sector = matching.get("offer_sector", "")
    transferable_block = ""
    if sector:
        transferable_block = f"""
CONTEXTUALISATION DES BULLETS TRANSFERABLES :
Le poste cible évolue dans le secteur/contexte : « {sector} ».
Pour chaque bullet issu d'une compétence TRANSFERABLE, fais le pont explicite avec ce contexte.
- AU LIEU DE : "Développé une API FastAPI exposant des traitements scientifiques"
- ÉCRIS PLUTÔT : "Développé une API FastAPI exposant des traitements — approche transposable au {sector}"
Reste honnête : ne prétends jamais avoir travaillé DANS ce secteur, indique seulement que l'expérience est transposable.
N'ajoute ce pont QUE sur les bullets transferables, pas sur les bullets déjà directement pertinents.
"""

    retry_block = ""
    if retry_issues:
        issues_list = "\n".join(f"- {issue}" for issue in retry_issues)
        retry_block = f"""
⚠️ TENTATIVE PRECEDENTE INSUFFISANTE — CORRIGE IMPERATIVEMENT :
{issues_list}
Cette fois, produis OBLIGATOIREMENT le nombre minimum d'elements demande.
Exploite TOUTES les preuves pertinentes de ALLOWED_EVIDENCE pour atteindre le volume requis.
"""

    return f"""
/no_think

Tu es un expert en redaction de CV optimises ATS.
{candidate_block}{retry_block}
MISSION : rediger les sections variables du CV cible a partir des preuves autorisees.

SYNTHESE DU MATCHING :
{matching_summary}

FORMAT OBLIGATOIRE DES BULLETS :
Structure : [Verbe d'action passe] + [contexte/technologie precise] + [resultat ou impact si disponible]
- BON  : "Developpe 4 pipelines Python batch pour la structuration de datasets industriels multi-capteurs"
- BON  : "Concu et deploye une API FastAPI exposant des traitements scientifiques via REST — utilisee en production"
- BON  : "Analyse et resolu des incidents de connectivite sur systemes embarques IoT"
- MAUVAIS : "Travaille sur des pipelines Python"
- MAUVAIS : "Participe au developpement d'APIs"
Regles :
- Commence par un verbe conjugue (Developpe, Concu, Analyse, Deploye, Integre, Optimise...)
- 60 a 120 caracteres par bullet
- Mention la technologie ou le contexte specifique issue des preuves
- Ordonne les bullets du plus au moins pertinent pour l'offre
{transferable_block}
FORMAT OBLIGATOIRE DU RESUME PROFESSIONNEL :
5 phrases minimum, chacune avec un role distinct. Utilise UNIQUEMENT les preuves de ALLOWED_EVIDENCE.

Phrase 1 — Ancrage : [Titre professionnel] avec [N] ans d'expérience en [domaine principal prouvé].
Phrase 2 — Preuves ciblées : maîtrise de [compétences CONFIRMED uniquement], appliquées à [contexte concret issu des preuves].
  INTERDIT de citer une compétence TRANSFERABLE ou ABSENTE comme si elle était acquise.
Phrase 3 — Réalisation concrète : une réalisation mesurable ou impactante issue des preuves (chiffre, échelle, résultat).
  Si aucun chiffre disponible : décrire le contexte technique précis (taille, environnement, criticité).
Phrase 4 — Valeur pour CE poste : lien explicite entre l'expérience réelle du candidat et les besoins spécifiques de l'offre.
  INTERDIT : nommer une techno absente, écrire "capacité à s'adapter" ou "montée en compétence".
  CORRECT : relier une compétence prouvée au contexte de l'offre (secteur, type de système, méthode de travail).
Phrase 5 — Positionnement : type d'environnement, de projet ou de méthode de travail où le candidat est à l'aise, cohérent avec l'offre cible (ex : travail en équipe agile, environnements Linux, projets data, systèmes embarqués…).
  INTERDIT : "montée en compétence", "capacité à évoluer", "potentiel d'adaptation" ou toute formule générique de ce type.

Maximum 600 caractères. Pas de formulations génériques ("passionné par", "rigoureux", "dynamique").

FORMAT OBLIGATOIRE DE LA LETTRE DE MOTIVATION (application_email) :
Une vraie lettre structurée en 3 paragraphes, champs séparés :
- "accroche" (1 paragraphe, 2-3 phrases) : accroche liée au POSTE et à l'entreprise. Montre que tu as compris l'offre et son contexte. Pas de "Je me permets de vous écrire".
- "preuves" (1 paragraphe, 3-4 phrases) : tes preuves concrètes les plus pertinentes pour CETTE offre (compétences CONFIRMÉES, réalisations chiffrées si disponibles). Fais le lien explicite entre ton expérience et les besoins du poste.
- "motivation" (1 paragraphe, 2-3 phrases) : ta motivation pour ce poste précis + capacité d'apprentissage sur les technologies à acquérir + disponibilité pour un entretien.
- "subject" : objet d'email clair, ex "Candidature - [titre du poste]".
Règles lettre :
- Ton professionnel, direct, sans flatterie excessive ni formules creuses.
- Ne revendique RIEN de FORBIDDEN_CLAIMS comme acquis ; formule comme objectif d'apprentissage.
- N'invente pas le nom de l'entreprise si absent de l'offre.

CONTRAINTES DE TAILLE :
- 6 a 9 competences a afficher
- 5 a 8 bullets d'experience
- Resume : 5 phrases, maximum 600 caracteres
- Chaque paragraphe de la lettre : 2 a 4 phrases maximum

REGLES ABSOLUES :
- Remplis toutes les cles du JSON demande.
- N'utilise aucune information absente de ALLOWED_EVIDENCE.
- N'invente aucune experience, aucun projet, aucune technologie.
- Ne revendique rien present dans FORBIDDEN_CLAIMS.
- Formule les elements TRANSFERABLES comme tels (experience proche, capacite de transfert).
- Formule les technologies absentes comme objectif de formation, jamais comme experience acquise.
- Chaque competence et chaque bullet doit citer au moins un evidence_id valide.
- Integre les mots-cles de l'offre dans competences et resume (optimisation ATS).

OFFRE D'EMPLOI :
\"\"\"
{job_offer}
\"\"\"

ALLOWED_EVIDENCE :
{json.dumps(allowed_evidence, ensure_ascii=False, indent=2)}

FORBIDDEN_CLAIMS :
{json.dumps(forbidden_claims, ensure_ascii=False, indent=2)}

Reponds uniquement en JSON valide.
"""
