"""
Génération des fichiers Markdown (CV recruteur, audit, email)
et utilitaires de formatage dates/localisation.
"""
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
    return isinstance(cv_master, dict) and isinstance(cv_master.get("profile"), dict) and (
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
    import datetime
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
    lines = [f"# {title}", ""]

    contact_items = [
        full_name,
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
    lines.append(f"# {title}")
    lines.append("")
    contact_items = []
    name = static_sections["identity"].get("nom")
    if name:
        contact_items.append(name)
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
