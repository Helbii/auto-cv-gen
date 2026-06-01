"""
Génération des fichiers Markdown (CV recruteur, audit, email)
et utilitaires de formatage dates/localisation.
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import resolve_safe_title, resolve_safe_summary, resolve_safe_email
from .text_utils import normalize_text


# ── Utilitaires dates et format ───────────────────────────────────────────────

def year_only(value: Any) -> str:
    value = str(value or "").strip()
    return value[:4] if len(value) >= 4 else value


MONTHS_FR = {
    "01": "janv.", "02": "févr.", "03": "mars", "04": "avr.",
    "05": "mai",   "06": "juin",  "07": "juil.", "08": "août",
    "09": "sept.", "10": "oct.",  "11": "nov.",  "12": "déc.",
}


def month_year(value: Any) -> str:
    value = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})", value)
    if not match:
        return year_only(value)
    year, month = match.groups()
    month_name = MONTHS_FR.get(month)
    return f"{month_name} {year}" if month_name else year


def format_cv_date(start: Any, end: Any, is_current: bool = False) -> str:
    start_year = year_only(start)
    end_year = "présent" if is_current else year_only(end)
    if start_year and end_year:
        if start_year == end_year:
            start_month = month_year(start)
            end_month = month_year(end)
            if start_month and end_month and start_month != start_year and end_month != end_year:
                return start_month if start_month == end_month else f"{start_month.split()[0]}-{end_month}"
            return start_year
        return f"{start_year}-{end_year}"
    single_date = month_year(start or end)
    return single_date or start_year or end_year


def format_location(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(part for part in [value.get("city"), value.get("country")] if part)
    return str(value or "")


def is_database_cv(cv_master: Any) -> bool:
    if not isinstance(cv_master, dict):
        return False
    schema_type = cv_master.get("schema_type", "")
    if schema_type:
        return schema_type == "database"
    return isinstance(cv_master.get("profile"), dict) and (
        "firstName" in cv_master["profile"] or "lastName" in cv_master["profile"]
    )


def format_achievement(achievement: Any) -> str:
    if not isinstance(achievement, dict):
        return str(achievement or "").strip()
    description = str(achievement.get("description") or "").strip()
    impact = str(achievement.get("impact") or "").strip()
    metrics = achievement.get("metrics", {})
    metric_text = ""
    if isinstance(metrics, dict) and metrics.get("value"):
        metric_text = f" ({metrics.get('value')} {metrics.get('unit') or ''})".strip()
    if description and impact:
        return f"{description} Impact : {impact}{metric_text}"
    return description or impact


# ── Niveau / expérience des compétences ───────────────────────────────────────

def _parse_year_month(value: Any) -> Optional[int]:
    """Convertit 'YYYY-MM' ou 'YYYY' en nombre de mois absolu (année*12 + mois)."""
    value = str(value or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})", value)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2)) - 1
    m = re.match(r"^(\d{4})", value)
    if m:
        return int(m.group(1)) * 12
    return None


def _merge_intervals_months(intervals: List[tuple]) -> int:
    """Fusionne des intervalles (start_months, end_months) et somme la durée distincte."""
    valid = sorted((s, e) for s, e in intervals if s is not None and e is not None and e >= s)
    if not valid:
        return 0
    total = 0
    cur_s, cur_e = valid[0]
    for s, e in valid[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return total


def build_skill_experience_map(cv_master: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Pour chaque technologie, calcule la durée d'expérience (intervalles fusionnés)
    à partir des dates des expériences qui la mentionnent.
    Retourne {techno_normalisée: "3 ans"} pour les durées >= ~1 an.
    """
    if not isinstance(cv_master, dict):
        return {}
    now_months = datetime.date.today().year * 12 + datetime.date.today().month - 1

    tech_intervals: Dict[str, List[tuple]] = {}
    for exp in cv_master.get("experiences", []):
        start = _parse_year_month(exp.get("startDate"))
        end = now_months if exp.get("isCurrent") else _parse_year_month(exp.get("endDate"))
        techs = exp.get("technologies") or exp.get("stack") or exp.get("technical_environment") or []
        for tech in techs:
            key = normalize_text(tech)
            if key:
                tech_intervals.setdefault(key, []).append((start, end))

    result: Dict[str, str] = {}
    for key, intervals in tech_intervals.items():
        months = _merge_intervals_months(intervals)
        years = round(months / 12)
        if years >= 1:
            result[key] = f"{years} an{'s' if years > 1 else ''}"
    return result


_DURATION_ANNOTATION_RE = re.compile(r"\(\d+ ans?\)$")


def annotate_audit_skills(audit: Dict[str, Any], cv_master: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Enrichit les noms de compétences validées avec leur durée d'expérience.
    'Python' → 'Python (3 ans)'. Mutation en place de audit['valid_skills'].
    Se propage à tous les rendus (markdown, rendercv, docx) car ils lisent valid_skills.
    """
    exp_map = build_skill_experience_map(cv_master)
    if not exp_map:
        return audit
    for item in audit.get("valid_skills", []):
        name = str(item.get("skill", "")).strip()
        if not name:
            continue
        # Évite de ré-annoter si déjà fait — teste le pattern exact "(N an[s])"
        if _DURATION_ANNOTATION_RE.search(name):
            continue
        years = exp_map.get(normalize_text(name))
        if years:
            item["skill"] = f"{name} ({years})"
    return audit


# ── Pertinence offre : projets & missions ─────────────────────────────────────

def build_offer_terms(matching: Dict[str, Any]) -> set:
    """Ensemble des termes normalisés pertinents pour l'offre (mots-clés + exigences)."""
    terms = set()
    for kw in matching.get("job_keywords", []):
        t = normalize_text(str(kw))
        if len(t) >= 3:
            terms.add(t)
    for req in matching.get("requirements_analysis", []):
        if req.get("status") in {"CONFIRMED", "TRANSFERABLE"}:
            t = normalize_text(str(req.get("requirement", "")))
            if len(t) >= 3:
                terms.add(t)
    for term in matching.get("safe_context_terms", []):
        t = normalize_text(str(term))
        if len(t) >= 3:
            terms.add(t)
    return terms


def _relevance_score(text: str, offer_terms: set) -> int:
    """Compte le nombre de termes de l'offre présents dans le texte."""
    haystack = normalize_text(text)
    return sum(1 for t in offer_terms if t in haystack)


def select_relevant_projects(
    cv_master: Optional[Dict[str, Any]],
    matching: Dict[str, Any],
    max_projects: int = 3,
) -> List[Dict[str, Any]]:
    """
    Sélectionne les projets les plus pertinents pour l'offre.
    Score = recouvrement (techs + description + nom) avec les termes de l'offre,
    départage par date de fin la plus récente.
    """
    if not isinstance(cv_master, dict):
        return []
    projects = cv_master.get("projects", [])
    if not projects:
        return []

    offer_terms = build_offer_terms(matching)
    scored = []
    for proj in projects:
        haystack = " ".join([
            str(proj.get("name", "")),
            str(proj.get("description", "")),
            " ".join(str(t) for t in proj.get("technologies", [])),
        ])
        score = _relevance_score(haystack, offer_terms)
        end = str(proj.get("endDate", ""))
        scored.append((score, end, proj))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # Ne garde que les projets avec au moins un terme commun ; sinon, les plus récents
    relevant = [p for s, _, p in scored if s > 0][:max_projects]
    if not relevant:
        relevant = [p for _, _, p in scored[:max_projects]]
    return relevant


def rank_missions_by_relevance(missions: List[str], offer_terms: set, limit: int) -> List[str]:
    """Réordonne les missions par pertinence à l'offre puis tronque."""
    cleaned = [str(m).strip() for m in missions if str(m).strip()]
    if not offer_terms:
        return cleaned[:limit]
    ranked = sorted(cleaned, key=lambda m: _relevance_score(m, offer_terms), reverse=True)
    return ranked[:limit]


def format_project_entry(proj: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise un projet pour l'affichage : nom, description courte, techs, date."""
    name = str(proj.get("name", "")).strip()
    description = str(proj.get("description", "")).strip()
    # Première phrase de la description, tronquée
    short_desc = re.split(r"(?<=[.!?])\s+", description)[0] if description else ""
    if len(short_desc) > 150:
        short_desc = short_desc[:147].rstrip() + "…"
    techs = [str(t).strip() for t in proj.get("technologies", []) if str(t).strip()][:6]
    date = format_cv_date(proj.get("startDate"), proj.get("endDate"))
    return {"name": name, "description": short_desc, "technologies": techs, "date": date}


# ── Utilitaires sections CV ───────────────────────────────────────────────────

def extract_static_cv_sections(id_to_evidence: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    identity: Dict[str, str] = {}
    contact: Dict[str, str] = {}
    locations: List[str] = []
    education: Dict[str, Dict[str, Any]] = {}
    languages: List[str] = []

    for ev in id_to_evidence.values():
        category = ev.get("category", "")
        source = ev.get("source", "")
        field = ev.get("field", "")
        text = ev.get("text", "")
        if not text:
            continue
        if category == "identity":
            identity[field] = text
        elif category == "contact":
            contact[field] = text
        elif category == "location":
            if text not in locations:
                locations.append(text)
        elif category in {"education", "education_skill", "education_thesis"}:
            item = education.setdefault(source, {"title": source, "details": []})
            if field not in {"intitule", "ecole", "periode"} and text not in item["details"]:
                item["details"].append(text)
        elif category == "language":
            if text not in languages:
                languages.append(text)

    return {
        "identity": identity,
        "contact": contact,
        "locations": locations,
        "education": list(education.values()),
        "languages": languages,
    }


def group_experience_bullets(valid_bullets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[str]] = {}
    for item in valid_bullets:
        source = item.get("source", "Experience")
        bullet = item.get("bullet", "")
        if not bullet:
            continue
        grouped.setdefault(source, [])
        if bullet not in grouped[source]:
            grouped[source].append(bullet)
    return [{"source": source, "bullets": bullets} for source, bullets in grouped.items()]


def stack_for_source(source: str, id_to_evidence: Dict[str, Dict[str, Any]]) -> str:
    stack = []
    for ev in id_to_evidence.values():
        if ev.get("source") != source:
            continue
        if ev.get("category") in {"experience_tech", "project_tech"} and ev.get("text"):
            text = ev["text"]
            if text not in stack:
                stack.append(text)
    return ", ".join(stack[:10])


# ── Génération Markdown ───────────────────────────────────────────────────────

def generate_database_recruiter_markdown(
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    cv_master: Dict[str, Any],
) -> str:
    profile = cv_master.get("profile", {})
    contact = profile.get("contact", {})
    full_name = " ".join(part for part in [profile.get("firstName"), profile.get("lastName")] if part)
    title = resolve_safe_title(matching, generated, audit)
    lines = [f"# {full_name}", f"**{title}**", ""]

    contact_items = [
        format_location(profile.get("location")),
        contact.get("email"),
        contact.get("phone"),
        contact.get("github"),
        contact.get("linkedin"),
    ]
    lines.append(" | ".join(item for item in contact_items if item))
    lines.append("")
    lines.append("## Resume professionnel")
    lines.append("")
    lines.append(resolve_safe_summary(generated, audit, matching))
    lines.append("")

    technical = cv_master.get("skills", {}).get("technical", {})
    skill_groups = [
        ("Langages", "programmingLanguages"),
        ("Backend & APIs", "backend"),
        ("Data & IA", "dataEngineering"),
        ("Bases de donnees", "databases"),
        ("Frontend", "frontend"),
        ("DevOps & outils", "devOpsTools"),
        ("IoT & embarque", "embeddedIoT"),
    ]
    lines.append("## Competences cles")
    lines.append("")
    valid_skills = [item.get("skill", "") for item in audit.get("valid_skills", []) if item.get("skill")]
    if valid_skills:
        lines.append(f"- **Competences principales :** {', '.join(dict.fromkeys(valid_skills[:10]))}")
    for label, key in skill_groups:
        values = technical.get(key, []) if isinstance(technical, dict) else []
        if values:
            lines.append(f"- **{label} :** {', '.join(values[:8])}")
    lines.append("")

    offer_terms = build_offer_terms(matching)

    lines.append("## Experiences")
    lines.append("")
    for exp in cv_master.get("experiences", []):
        date = format_cv_date(exp.get("startDate"), exp.get("endDate"), bool(exp.get("isCurrent")))
        location = format_location(exp.get("location"))
        header_parts = [exp.get("position"), exp.get("company"), location, date]
        lines.append(f"### {' - '.join(part for part in header_parts if part)}")
        if exp.get("summary"):
            lines.append(exp["summary"])
        # Missions triées par pertinence à l'offre, volume réduit pour tenir sur 1 page
        for mission in rank_missions_by_relevance(exp.get("missions", []), offer_terms, limit=3):
            lines.append(f"- {mission}")
        for achievement in exp.get("achievements", [])[:2]:
            text = format_achievement(achievement)
            if text:
                lines.append(f"- {text}")
        technologies = exp.get("technologies", [])
        if technologies:
            lines.append(f"- **Stack :** {', '.join(technologies[:10])}")
        lines.append("")

    # Projets personnels les plus pertinents pour l'offre
    relevant_projects = select_relevant_projects(cv_master, matching, max_projects=3)
    if relevant_projects:
        lines.append("## Projets")
        lines.append("")
        for proj in relevant_projects:
            entry = format_project_entry(proj)
            header = entry["name"]
            if entry["date"]:
                header = f"{header} - {entry['date']}"
            lines.append(f"### {header}")
            if entry["description"]:
                lines.append(entry["description"])
            if entry["technologies"]:
                lines.append(f"- **Stack :** {', '.join(entry['technologies'])}")
            lines.append("")

    education = cv_master.get("education", [])
    if education:
        lines.append("## Formation")
        lines.append("")
        for edu in education[:4]:
            date = format_cv_date(edu.get("startDate"), edu.get("endDate"), bool(edu.get("isCurrent")))
            parts = [edu.get("school"), edu.get("degree"), date]
            lines.append(f"- **{' - '.join(part for part in parts if part)}**")
        lines.append("")

    languages = []
    for lang in cv_master.get("languages", []):
        if lang.get("language") and lang.get("level"):
            languages.append(f"{lang['language']} : {lang['level']}")
    certifications = [cert.get("name") for cert in cv_master.get("certifications", []) if cert.get("name")]
    if certifications and len(languages) >= 2:
        languages[1] = f"{languages[1]} - {certifications[0]}"
    if languages:
        lines.append("## Langues")
        lines.append("")
        for language in languages:
            lines.append(f"- {language}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_recruiter_markdown(
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    id_to_evidence: Dict[str, Dict[str, Any]],
    cv_master: Dict[str, Any] | None = None,
) -> str:
    if is_database_cv(cv_master):
        return generate_database_recruiter_markdown(matching, generated, audit, cv_master)

    cv = generated.get("targeted_cv", {})
    static_sections = extract_static_cv_sections(id_to_evidence)
    lines = []
    title = resolve_safe_title(matching, generated, audit)
    name = static_sections["identity"].get("nom")
    lines.append(f"# {name}" if name else f"# {title}")
    lines.append(f"**{title}**")
    lines.append("")
    contact_items = []
    if static_sections["locations"]:
        contact_items.append(", ".join(static_sections["locations"]))
    for field in ["email", "telephone", "linkedin", "github"]:
        value = static_sections["contact"].get(field)
        if value:
            contact_items.append(value)
    if contact_items:
        lines.append(" | ".join(contact_items))
        lines.append("")
    lines.append(f"**Score ATS cible :** {cv.get('matching_score', matching.get('matching_score', 0))}/100")
    lines.append("")
    lines.append("## Resume professionnel")
    lines.append("")
    lines.append(resolve_safe_summary(generated, audit, matching))
    lines.append("")

    lines.append("## Competences cles")
    lines.append("")
    for skill in audit.get("valid_skills", []):
        lines.append(f"- {skill.get('skill', '')}")
    lines.append("")

    lines.append("## Experiences")
    lines.append("")
    for experience in group_experience_bullets(audit.get("valid_bullets", [])):
        lines.append(f"### {experience['source']}")
        for bullet in experience["bullets"][:6]:
            lines.append(f"- {bullet}")
        stack = stack_for_source(experience["source"], id_to_evidence)
        if stack:
            lines.append(f"- Stack : {stack}")
        lines.append("")

    if static_sections["education"]:
        lines.append("## Formation")
        lines.append("")
        for item in static_sections["education"]:
            lines.append(f"- **{item['title']}**")
        lines.append("")

    if static_sections["languages"]:
        lines.append("## Langues")
        lines.append("")
        for language in static_sections["languages"]:
            lines.append(f"- {language}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_email_markdown(matching: Dict[str, Any], generated: Dict[str, Any], audit: Dict[str, Any]) -> str:
    email = resolve_safe_email(matching, generated, audit)
    return "\n".join([
        "# Lettre de motivation",
        "",
        f"**Objet :** {email['subject']}",
        "",
        email["body"],
        "",
    ])


def generate_audit_markdown(
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    id_to_evidence: Dict[str, Dict[str, Any]],
) -> str:
    cv = generated.get("targeted_cv", {})
    lines = []
    lines.append("# Audit generation CV")
    lines.append("")
    lines.append(f"**Score de matching :** {cv.get('matching_score', matching.get('matching_score', 0))}/100")
    lines.append("")
    lines.append("## Synthese")
    lines.append("")
    lines.append(f"- Bullets valides : {len(audit.get('valid_bullets', []))}")
    lines.append(f"- Bullets rejetes : {len(audit.get('rejected_bullets', []))}")
    lines.append(f"- Competences validees : {len(audit.get('valid_skills', []))}")
    lines.append(f"- Competences rejetees : {len(audit.get('rejected_skills', []))}")
    lines.append("")

    if audit.get("title_forbidden_claims") or audit.get("summary_forbidden_claims") or audit.get("email_forbidden_claims"):
        lines.append("## Corrections safety")
        lines.append("")
        if audit.get("title_forbidden_claims"):
            lines.append(f"- Titre corrige : {', '.join(audit['title_forbidden_claims'])}")
        if audit.get("summary_forbidden_claims"):
            lines.append(f"- Resume corrige : {', '.join(audit['summary_forbidden_claims'])}")
        if audit.get("email_forbidden_claims"):
            lines.append(f"- Mail corrige : {', '.join(audit['email_forbidden_claims'])}")
        lines.append("")

    lines.append("## Competences absentes ou faibles")
    lines.append("")
    for item in matching.get("weak_or_missing_requirements", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Analyse des correspondances")
    lines.append("")
    for req in matching.get("requirements_analysis", []):
        lines.append(f"### {req.get('requirement', '')}")
        lines.append(f"- **Statut :** {req.get('status', '')}")
        lines.append(f"- **Utilisation CV :** {req.get('cv_usage', '')}")
        lines.append(f"- **Explication :** {req.get('explanation', '')}")
        evidence_ids = req.get("evidence_ids", [])
        if evidence_ids:
            lines.append("- **Preuves :**")
            for eid in evidence_ids:
                ev = id_to_evidence.get(eid)
                if ev:
                    lines.append(f"  - `{eid}` - {ev.get('text', '')}")
        lines.append("")

    if audit.get("rejected_bullets") or audit.get("rejected_skills"):
        lines.append("## Elements rejetes automatiquement")
        lines.append("")
        for item in audit.get("rejected_bullets", []):
            lines.append(f"- {item.get('bullet', '')}")
            for reason in item.get("reasons", []):
                lines.append(f"  - Raison : {reason}")
        for item in audit.get("rejected_skills", []):
            lines.append(f"- {item.get('skill', '')}")
            for reason in item.get("reasons", []):
                lines.append(f"  - Raison : {reason}")

    return "\n".join(lines)


def generate_markdown(
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    id_to_evidence: Dict[str, Dict[str, Any]],
    cv_master: Dict[str, Any] | None = None,
) -> str:
    return generate_recruiter_markdown(matching, generated, audit, id_to_evidence, cv_master=cv_master)


_DEGREE_PREFIX_FR_TO_EN: Dict[str, str] = {
    "diplôme d'ingénieur":                     "Engineering Degree",
    "master":                                   "Master's Degree",
    "licence":                                  "Bachelor's Degree",
    "doctorat":                                 "PhD",
    "dut génie électrique et informatique industrielle": "2-Year Tech Degree — Electrical & Industrial IT",
    "dut génie électrique":                     "2-Year Tech Degree — Electrical Engineering",
    "dut informatique":                         "2-Year Tech Degree — Computer Science",
    "dut":                                      "2-Year Technical University Degree",
    "bts":                                      "Advanced Vocational Certificate",
    "baccalauréat sti2d":                       "High School Diploma — Science & Technology",
    "baccalauréat s":                           "High School Diploma — Sciences",
    "baccalauréat":                             "High School Diploma",
    "classe préparatoire ats":                  "Preparatory Class (ATS — Advanced Technician Sciences)",
    "classe préparatoire mpsi":                 "Preparatory Class (MPSI)",
    "classe préparatoire pcsi":                 "Preparatory Class (PCSI)",
    "classe préparatoire":                      "Preparatory Class",
}


def _translate_degree(degree: str) -> str:
    """Map common French degree names to English using a prefix dictionary."""
    lower = degree.lower()
    for fr_prefix, en in _DEGREE_PREFIX_FR_TO_EN.items():
        if lower.startswith(fr_prefix):
            remainder = degree[len(fr_prefix):].strip()
            if remainder and not remainder.startswith("—"):
                return f"{en} — {remainder}"
            return en
    return degree


_LEVEL_FR_TO_EN: Dict[str, str] = {
    "natif":             "Native",
    "langue maternelle": "Native",
    "courant":           "Fluent",
    "parlé":             "Spoken",
    "avancé":            "Advanced",
    "intermédiaire":     "Intermediate",
    "débutant":          "Basic",
    "notions":           "Basic",
    "bilingue":          "Bilingual",
    "b2":                "B2",
    "b1":                "B1",
    "c1":                "C1",
    "c2":                "C2",
}


def generate_en_markdown(
    cv_en: Dict[str, Any],
    cv_master: Dict[str, Any] | None = None,
) -> str:
    from collections import OrderedDict
    lines: List[str] = []
    master = cv_master or {}
    database_mode = is_database_cv(master)

    # ── Header ────────────────────────────────────────────────────────────────
    profile = master.get("profile", {})
    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    if name:
        contact  = profile.get("contact", {})
        location = profile.get("location", {})
        loc_str  = ", ".join(p for p in [location.get("city"), location.get("country")] if p)
        parts    = [p for p in [loc_str, contact.get("email"), contact.get("phone"),
                                 contact.get("github"), contact.get("linkedin")] if p]
        lines.append(f"# {name}")
        job_title = cv_en.get("title", "").strip()
        if job_title:
            lines.append(f"**{job_title}**")
        if parts:
            lines.append(" | ".join(parts))

    # ── Professional Summary ──────────────────────────────────────────────────
    summary = cv_en.get("professional_summary", "").strip()
    if summary:
        lines.append("\n## Professional Summary\n")
        lines.append(summary)

    # ── Key Skills ────────────────────────────────────────────────────────────
    skills_raw = cv_en.get("skills_to_display") or []
    skills = [s.get("skill", s) if isinstance(s, dict) else str(s) for s in skills_raw if s]
    if skills:
        lines.append("\n## Key Skills\n")
        for skill in skills:
            lines.append(f"- {skill}")

    # ── Experience ────────────────────────────────────────────────────────────
    raw_bullets = [b for b in (cv_en.get("experience_bullets") or []) if isinstance(b, dict) and b.get("bullet")]
    if raw_bullets:
        lines.append("\n## Experience\n")
        grouped: dict = OrderedDict()
        for b in raw_bullets:
            grouped.setdefault(b.get("source", ""), []).append(b["bullet"])
        for source, src_bullets in grouped.items():
            if source:
                lines.append(f"**{source}**")
            for bullet in src_bullets:
                lines.append(f"- {bullet}")
            lines.append("")

    # ── Projects (database mode only — titles and tech stacks need no translation) ──
    if database_mode:
        projects = master.get("projects", [])
        if projects:
            lines.append("\n## Projects\n")
            for proj in projects[:3]:
                proj_name = str(proj.get("name", "")).strip()
                proj_date = format_cv_date(proj.get("startDate"), proj.get("endDate"))
                header = f"**{proj_name}**" + (f" — {proj_date}" if proj_date else "")
                lines.append(header)
                desc = str(proj.get("description", "")).strip()
                if desc:
                    first_sentence = re.split(r"(?<=[.!?])\s+", desc)[0][:150]
                    lines.append(first_sentence)
                techs = [str(t) for t in proj.get("technologies", []) if t][:6]
                if techs:
                    lines.append(f"Stack: {', '.join(techs)}")
                lines.append("")

    # ── Education ─────────────────────────────────────────────────────────────
    if database_mode:
        education = master.get("education", [])
        if education:
            lines.append("\n## Education\n")
            for edu in education[:4]:
                school = str(edu.get("school", "")).strip()
                degree = _translate_degree(str(edu.get("degree", "")).strip())
                edu_date = format_cv_date(
                    edu.get("startDate"), edu.get("endDate"), bool(edu.get("isCurrent"))
                )
                parts_edu = [p for p in [school, degree, edu_date] if p]
                lines.append(f"- **{' — '.join(parts_edu)}**")
            lines.append("")

    # ── Languages ─────────────────────────────────────────────────────────────
    if database_mode:
        lang_entries = master.get("languages", [])
        certifications = [c.get("name") for c in master.get("certifications", []) if c.get("name")]
        lang_lines: List[str] = []
        for lang in lang_entries:
            language_name = str(lang.get("language", "")).strip()
            level_fr = str(lang.get("level", "")).strip()
            level_en = _LEVEL_FR_TO_EN.get(level_fr.lower(), level_fr)
            if language_name:
                lang_lines.append(f"{language_name}: {level_en}")
        if certifications and len(lang_lines) >= 2:
            lang_lines[1] = f"{lang_lines[1]} ({certifications[0]})"
        if lang_lines:
            lines.append("\n## Languages\n")
            for entry in lang_lines:
                lines.append(f"- {entry}")

    return "\n".join(lines)


# ── Persistence ───────────────────────────────────────────────────────────────

def save_outputs(output_dir: Path, files: Dict[str, Any]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, content in files.items():
        path = output_dir / name
        if name.endswith(".json"):
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")
        paths[name] = str(path)
    return paths
