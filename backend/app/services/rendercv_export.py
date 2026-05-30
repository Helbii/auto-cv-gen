import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..core.config import settings
from .generator import (
    extract_static_cv_sections,
    group_experience_bullets,
    resolve_safe_summary,
    resolve_safe_title,
    _year_only as year_only,
    _month_year as month_year,
    _format_cv_date as format_cv_date,
    _format_location as format_location,
    _is_database_cv as is_database_cv,
    _format_achievement as format_achievement,
    stack_for_source as experience_stack_for_source,
    MONTHS_FR,
)
from .markdown import (
    build_offer_terms,
    rank_missions_by_relevance,
    select_relevant_projects,
    format_project_entry,
)


def clean_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "cv_targeted"


def split_source(source: str) -> Dict[str, str]:
    parts = [part.strip() for part in source.split(" - ") if part.strip()]
    return {
        "company": parts[0] if parts else "Experience",
        "position": parts[1] if len(parts) > 1 else "",
        "date": parts[2] if len(parts) > 2 else "",
    }


def clean_date(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"-?en cours.*", "", value, flags=re.IGNORECASE).strip("- ")
    return value.replace("depuis ", "")


def make_xyz_bullet(bullet: str) -> str:
    return str(bullet or "").strip()


def social_username(url: str, network: str) -> str:
    url = str(url or "").strip().rstrip("/")
    if network == "GitHub":
        return url.replace("https://github.com/", "").replace("http://github.com/", "").replace("github.com/", "")
    if network == "LinkedIn":
        return (
            url.replace("https://www.linkedin.com/in/", "")
            .replace("http://www.linkedin.com/in/", "")
            .replace("www.linkedin.com/in/", "")
            .replace("linkedin.com/in/", "")
            .strip("/")
        )
    return url


def build_database_skills(cv_master: Dict[str, Any], audit: Dict[str, Any]) -> List[Dict[str, str]]:
    technical = cv_master.get("skills", {}).get("technical", {})
    groups = [
        ("Langages", "programmingLanguages"),
        ("Backend & APIs", "backend"),
        ("Data & IA", "dataEngineering"),
        ("Bases de données", "databases"),
        ("Frontend", "frontend"),
        ("DevOps & outils", "devOpsTools"),
        ("IoT & embarqué", "embeddedIoT"),
    ]

    entries: List[Dict[str, str]] = []
    validated = [item.get("skill", "") for item in audit.get("valid_skills", []) if item.get("skill")]
    if validated:
        entries.append({"label": "Compétences principales", "details": ", ".join(dict.fromkeys(validated[:10]))})

    for label, key in groups:
        values = technical.get(key, []) if isinstance(technical, dict) else []
        if values:
            entries.append({"label": label, "details": ", ".join(values[:8])})
    return entries[:7]


def build_database_experiences(cv_master: Dict[str, Any], matching: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    offer_terms = build_offer_terms(matching or {})
    experiences: List[Dict[str, Any]] = []
    for index, exp in enumerate(cv_master.get("experiences", [])[:3]):
        highlights: List[str] = []
        # Missions triées par pertinence à l'offre, volume réduit pour laisser place aux projets
        mission_limit = 4 if index == 0 else 3
        for mission in rank_missions_by_relevance(exp.get("missions", []), offer_terms, mission_limit):
            highlights.append(mission)
        achievement_limit = 1 if index <= 1 else 0
        for achievement in exp.get("achievements", [])[:achievement_limit]:
            text = format_achievement(achievement)
            if text and text not in highlights:
                highlights.append(text)
        technologies = exp.get("technologies", [])
        if technologies:
            highlights.append(f"Stack : {', '.join(technologies[:10])}")

        experiences.append({
            "company": exp.get("company"),
            "position": exp.get("position") or "Expérience professionnelle",
            "location": format_location(exp.get("location")),
            "date": format_cv_date(exp.get("startDate"), exp.get("endDate"), bool(exp.get("isCurrent"))),
            "summary": exp.get("summary") if index == 0 else "",
            "highlights": highlights[:6],
        })
    return experiences


def build_database_projects(cv_master: Dict[str, Any], matching: Dict[str, Any], max_projects: int = 3) -> List[Dict[str, Any]]:
    """Sélectionne les projets les plus pertinents pour l'offre et les formate pour rendercv."""
    entries: List[Dict[str, Any]] = []
    for proj in select_relevant_projects(cv_master, matching, max_projects=max_projects):
        info = format_project_entry(proj)
        highlights: List[str] = []
        if info["technologies"]:
            highlights.append(f"Stack : {', '.join(info['technologies'])}")
        entries.append({
            "name": info["name"],
            "date": info["date"],
            "summary": info["description"],
            "highlights": highlights,
        })
    return entries


def build_database_education(cv_master: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for edu in cv_master.get("education", [])[:4]:
        entries.append({
            "institution": edu.get("school"),
            "area": edu.get("degree"),
            "degree": "",
            "date": format_cv_date(edu.get("startDate"), edu.get("endDate"), bool(edu.get("isCurrent"))),
        })
    return entries


def build_database_languages(cv_master: Dict[str, Any]) -> List[Dict[str, str]]:
    languages = []
    for lang in cv_master.get("languages", []):
        if lang.get("language") and lang.get("level"):
            languages.append(f"{lang['language']} : {lang['level']}")
    cert_names = [cert.get("name") for cert in cv_master.get("certifications", []) if cert.get("name")]
    if cert_names and len(languages) >= 2:
        languages[1] = f"{languages[1]} - {cert_names[0]}"
    # Séparateur " | " : le template OneLineEntry.j2.typ split sur " | " pour créer une badge par langue
    return [{"label": "Langues", "details": " | ".join(languages)}] if languages else []


def _clamp(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, low), high)


def _primary_color(value: Any) -> str:
    colors = {
        "blue": "rgb(0, 79, 144)",
        "slate": "rgb(51, 65, 85)",
        "green": "rgb(20, 120, 90)",
        "purple": "rgb(102, 76, 160)",
        "black": "rgb(20, 20, 20)",
    }
    return colors.get(str(value or "blue"), colors["blue"])


DESIGN_PRESETS: Dict[str, Dict[str, Any]] = {
    "compact": {
        "font_size": 8.75,
        "margin": "compact",
        "section_spacing": 0.16,
        "entry_spacing": 0.46,
        "bullet_spacing": 0.035,
        "name_delta": 14.5,
    },
    "classic": {
        "font_size": 9.25,
        "margin": "normal",
        "section_spacing": 0.20,
        "entry_spacing": 0.58,
        "bullet_spacing": 0.045,
        "name_delta": 15.75,
    },
    "tech": {
        "font_size": 9.15,
        "margin": "normal",
        "section_spacing": 0.18,
        "entry_spacing": 0.52,
        "bullet_spacing": 0.04,
        "name_delta": 15.2,
    },
    "airy": {
        "font_size": 9.75,
        "margin": "large",
        "section_spacing": 0.26,
        "entry_spacing": 0.72,
        "bullet_spacing": 0.06,
        "name_delta": 16.5,
    },
}


def _resolve_design_values(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalise les options UI en valeurs dérivées, partagées par tous les thèmes."""
    options = options or {}
    preset_name = str(options.get("preset") or "classic")
    preset = DESIGN_PRESETS.get(preset_name, DESIGN_PRESETS["classic"])
    merged_options = {**preset, **options}
    margins = {
        "compact": ("0.40in", "0.40in", "0.44in", "0.44in"),
        "normal": ("0.50in", "0.50in", "0.54in", "0.54in"),
        "large": ("0.62in", "0.62in", "0.66in", "0.66in"),
    }.get(str(merged_options.get("margin") or "normal"), ("0.50in", "0.50in", "0.54in", "0.54in"))
    return {
        "theme": str(merged_options.get("theme") or "engineeringclassic"),
        "margins": margins,
        "body_size": _clamp(merged_options.get("font_size"), 9.25, 8.2, 10.2),
        "section_spacing": _clamp(merged_options.get("section_spacing"), 0.20, 0.10, 0.45),
        "entry_spacing": _clamp(merged_options.get("entry_spacing"), 0.58, 0.32, 1.0),
        "bullet_spacing": _clamp(merged_options.get("bullet_spacing"), 0.045, 0.02, 0.12),
        "name_delta": _clamp(merged_options.get("name_delta"), 15.75, 12.0, 19.0),
        "primary": _primary_color(merged_options.get("primary_color")),
        "show_footer": bool(merged_options.get("show_footer", False)),
        "show_top_note": bool(merged_options.get("show_top_note", False)),
        "show_icons": bool(merged_options.get("show_icons", True)),
        "underline_links": bool(merged_options.get("underline_links", False)),
    }


def build_design(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    values = _resolve_design_values(options)
    if values["theme"] == "custom1":
        return _build_custom1_design(values)
    return _build_engineeringclassic_design(values)


def _build_custom1_design(v: Dict[str, Any]) -> Dict[str, Any]:
    """
    Design canonique custom1, basé sur le cv.yml de référence.
    Seule la taille de police est pilotée par le slider UI — tout le reste
    (marges 0cm, palette sombre, templates d'entrées) est figé dans l'identité
    visuelle du thème.
    """
    body_size = v["body_size"]
    # Ratio de la taille de référence (8.6pt) pour scaler les autres tailles
    scale = body_size / 8.6
    return {
        "theme": "custom1",
        "page": {
            "size": "a4",
            "top_margin": "0cm",
            "bottom_margin": "0cm",
            "left_margin": "0cm",
            "right_margin": "0cm",
            "show_footer": False,
            "show_top_note": False,
        },
        "colors": {
            "body": "rgb(57, 64, 85)",
            "name": "rgb(255, 255, 255)",
            "headline": "rgb(255, 255, 255)",
            "connections": "rgb(255, 255, 255)",
            "section_titles": "rgb(239, 86, 112)",
            "links": "rgb(255, 255, 255)",
            "footer": "rgb(128, 128, 128)",
            "top_note": "rgb(128, 128, 128)",
        },
        "typography": {
            "line_spacing": "0.50em",
            "alignment": "left",
            "date_and_location_column_alignment": "right",
            "font_family": {
                "body": "Source Sans 3",
                "name": "Source Sans 3",
                "headline": "Source Sans 3",
                "connections": "Source Sans 3",
                "section_titles": "Source Sans 3",
            },
            "font_size": {
                "body": f"{body_size:.2f}pt",
                "name": f"{16 * scale:.2f}pt",
                "headline": f"{9.1 * scale:.2f}pt",
                "connections": f"{8.1 * scale:.2f}pt",
                "section_titles": "1.35em",
            },
            "small_caps": {"name": False, "headline": False, "connections": False, "section_titles": False},
            "bold": {"name": True, "headline": False, "connections": False, "section_titles": True},
        },
        "links": {"underline": False, "show_external_link_icon": False},
        "header": {
            "alignment": "left",
            "photo_width": "3.0cm",
            "photo_position": "left",
            "photo_space_left": "0cm",
            "photo_space_right": "0.65cm",
            "space_below_name": "0cm",
            "space_below_headline": "0cm",
            "space_below_connections": "0cm",
            "connections": {
                "phone_number_format": "national",
                "hyperlink": True,
                "show_icons": True,
                "display_urls_instead_of_usernames": False,
                "separator": "",
                "space_between_connections": "0.32cm",
            },
        },
        "section_titles": {
            "type": "without_line",
            "line_thickness": "0.5pt",
            "space_above": "0cm",
            "space_below": "0cm",
        },
        "sections": {
            "allow_page_break": False,
            "space_between_regular_entries": "0.22em",
            "space_between_text_based_entries": "0.08em",
            "show_time_spans_in": [],
        },
        "entries": {
            "date_and_location_width": "4.15cm",
            "side_space": "0.15cm",
            "space_between_columns": "0.18cm",
            "allow_page_break": False,
            "short_second_row": True,
            "highlights": {
                "space_left": "0.15cm",
                "space_above": "0cm",
                "space_between_items": "0cm",
                "space_between_bullet_and_text": "0.35em",
            },
        },
        "templates": {
            "single_date": "MONTH_IN_TWO_DIGITS/YEAR",
            "date_range": "START_DATE – END_DATE",
            "experience_entry": {
                "main_column": "**COMPANY**, *POSITION*\nSUMMARY\n**MISSION_TITLE**\nHIGHLIGHTS\n**Stack** STACK",
                "date_and_location_column": "DATE | LOCATION",
            },
            "education_entry": {
                "main_column": "**INSTITUTION**, *DEGREE en AREA*",
                "date_and_location_column": "DATE",
            },
            "one_line_entry": {
                "main_column": "**LABEL** (DETAILS)",
            },
        },
    }


def _build_engineeringclassic_design(v: Dict[str, Any]) -> Dict[str, Any]:
    margins = v["margins"]
    body_size = v["body_size"]
    section_spacing = v["section_spacing"]
    entry_spacing = v["entry_spacing"]
    bullet_spacing = v["bullet_spacing"]
    name_delta = v["name_delta"]
    primary = v["primary"]
    show_footer = v["show_footer"]
    show_top_note = v["show_top_note"]
    show_icons = v["show_icons"]
    underline_links = v["underline_links"]
    return {
        "theme": "engineeringclassic",
        "page": {
            "size": "a4",
            "top_margin": margins[0],
            "bottom_margin": margins[1],
            "left_margin": margins[2],
            "right_margin": margins[3],
            "show_footer": show_footer,
            "show_top_note": show_top_note,
        },
        "colors": {
            "body": "rgba(0, 0, 0, 1)",
            "name": primary,
            "headline": primary,
            "connections": primary,
            "section_titles": primary,
            "links": primary,
            "footer": "rgb(128, 128, 128)",
            "top_note": "rgb(128, 128, 128)",
        },
        "typography": {
            "line_spacing": "0.55em",
            "alignment": "justified",
            "date_and_location_column_alignment": "right",
            "font_family": {
                "body": "Raleway",
                "name": "Raleway",
                "headline": "Raleway",
                "connections": "Raleway",
                "section_titles": "Raleway",
            },
            "font_size": {
                "body": f"{body_size:.2f}pt",
                "name": f"{body_size + name_delta:.2f}pt",
                "headline": f"{body_size + 0.15:.2f}pt",
                "connections": f"{max(body_size - 0.45, 8.0):.2f}pt",
                "section_titles": "1.16em",
            },
            "small_caps": {
                "name": False,
                "headline": False,
                "connections": False,
                "section_titles": False,
            },
            "bold": {
                "name": False,
                "headline": False,
                "connections": False,
                "section_titles": False,
            },
        },
        "links": {
            "underline": underline_links,
            "show_external_link_icon": False,
        },
        "header": {
            "alignment": "left",
            "space_below_name": "0.18cm",
            "space_below_headline": "0.18cm",
            "space_below_connections": "0.22cm",
            "connections": {
                "phone_number_format": "national",
                "hyperlink": True,
                "show_icons": show_icons,
                "display_urls_instead_of_usernames": False,
                "separator": "",
                "space_between_connections": "0.24cm",
            },
        },
        "section_titles": {
            "type": "with_full_line",
            "line_thickness": "0.35pt",
            "space_above": f"{section_spacing:.2f}cm",
            "space_below": "0.10cm",
        },
        "sections": {
            "allow_page_break": True,
            "space_between_regular_entries": f"{entry_spacing:.2f}em",
            "space_between_text_based_entries": "0.16em",
            "show_time_spans_in": [],
        },
        "entries": {
            "date_and_location_width": "3.15cm",
            "side_space": "0.08cm",
            "space_between_columns": "0.08cm",
            "allow_page_break": False,
            "short_second_row": False,
            "degree_width": "1cm",
            "summary": {
                "space_above": "0.04cm",
                "space_left": "0cm",
            },
            "highlights": {
                "bullet": "•",
                "nested_bullet": "•",
                "space_left": "0cm",
                "space_above": "0.04cm",
                "space_between_items": f"{bullet_spacing:.3f}cm",
                "space_between_bullet_and_text": "0.35em",
            },
        },
        "templates": {
            "footer": "*NAME -- PAGE_NUMBER/TOTAL_PAGES*",
            "top_note": "*LAST_UPDATED CURRENT_DATE*",
            "single_date": "MONTH_ABBREVIATION YEAR",
            "date_range": "START_DATE – END_DATE",
            "time_span": "HOW_MANY_YEARS YEARS HOW_MANY_MONTHS MONTHS",
            "one_line_entry": {"main_column": "**LABEL:** DETAILS"},
            "education_entry": {
                "main_column": "**INSTITUTION**, AREA",
                "date_and_location_column": "DATE",
            },
            "normal_entry": {
                "main_column": "**NAME** -- **LOCATION**\nSUMMARY\nHIGHLIGHTS",
                "date_and_location_column": "DATE",
            },
            "experience_entry": {
                "main_column": "**POSITION**, COMPANY -- LOCATION\nSUMMARY\nHIGHLIGHTS",
                "date_and_location_column": "DATE",
            },
            "publication_entry": {
                "main_column": "**TITLE**\nSUMMARY\nAUTHORS\nURL (JOURNAL)",
                "date_and_location_column": "DATE",
            },
        },
    }


def build_rendercv_yaml_data(
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    id_to_evidence: Dict[str, Dict[str, Any]],
    cv_master: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    static_sections = extract_static_cv_sections(id_to_evidence)
    identity = static_sections["identity"]
    contact = static_sections["contact"]
    database_mode = is_database_cv(cv_master)
    profile = cv_master.get("profile", {}) if database_mode else {}
    profile_contact = profile.get("contact", {}) if database_mode else {}

    if database_mode:
        name = " ".join(part for part in [profile.get("firstName"), profile.get("lastName")] if part) or None
        location = format_location(profile.get("location"))
        email = profile_contact.get("email")
        phone = profile_contact.get("phone")
        github = profile_contact.get("github") or None
        linkedin = profile_contact.get("linkedin") or None
    else:
        name = identity.get("nom") or None
        location = ", ".join(static_sections["locations"])
        email = contact.get("email")
        phone = contact.get("telephone")
        github = contact.get("github") or None
        linkedin = contact.get("linkedin") or None

    sections: Dict[str, List[Any]] = {
        "Résumé": [resolve_safe_summary(generated, audit, matching)],
    }

    if database_mode:
        skill_entries = build_database_skills(cv_master, audit)
        if skill_entries:
            sections["Compétences clés"] = skill_entries
    else:
        skills = [item.get("skill", "") for item in audit.get("valid_skills", []) if item.get("skill")]
        if skills:
            sections["Compétences clés"] = [{"label": "Compétences ciblées", "details": ", ".join(skills[:12])}]

    experiences = build_database_experiences(cv_master, matching) if database_mode else []
    if not experiences:
        for experience in group_experience_bullets(audit.get("valid_bullets", [])):
            source_parts = split_source(experience["source"])
            highlights = [make_xyz_bullet(bullet) for bullet in experience["bullets"][:6] if bullet]
            stack = experience_stack_for_source(experience["source"], id_to_evidence)
            if stack:
                highlights.append(f"Stack : {stack}")
            experiences.append({
                "company": source_parts["company"],
                "position": source_parts["position"] or "Expérience professionnelle",
                "date": clean_date(source_parts["date"]),
                "highlights": highlights,
            })
    if experiences:
        sections["Expérience"] = experiences

    # Projets personnels les plus pertinents (database mode uniquement)
    if database_mode:
        project_entries = build_database_projects(cv_master, matching, max_projects=3)
        if project_entries:
            sections["Projets"] = project_entries

    education_entries = build_database_education(cv_master) if database_mode else []
    if not education_entries:
        for item in static_sections["education"][:4]:
            title_parts = [part.strip() for part in item["title"].split(" - ") if part.strip()]
            education_entries.append({
                "institution": title_parts[0] if title_parts else item["title"],
                "area": title_parts[1] if len(title_parts) > 1 else "Formation",
                "degree": "",
                "date": clean_date(title_parts[2] if len(title_parts) > 2 else ""),
            })
    if education_entries:
        sections["Formation"] = education_entries

    language_entries = build_database_languages(cv_master) if database_mode else []
    if language_entries:
        sections["Langues"] = language_entries
    elif static_sections["languages"]:
        sections["Langues"] = [{"label": "Langues", "details": " | ".join(static_sections["languages"])}]

    social_networks = []
    if github:
        social_networks.append({"network": "GitHub", "username": social_username(github, "GitHub")})
    if linkedin:
        social_networks.append({"network": "LinkedIn", "username": social_username(linkedin, "LinkedIn")})

    return prune_empty({
        "cv": {
            "name": name,
            "headline": resolve_safe_title(matching, generated, audit),
            "location": location,
            "email": email,
            "phone": phone,
            "social_networks": social_networks or None,
            "sections": sections,
        },
        "design": build_design(),
        "locale": {
            "language": "french",
            "last_updated": "Dernière mise à jour",
            "present": "présent",
        },
    })


def prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: prune_empty(item)
            for key, item in value.items()
            if item not in [None, "", [], {}]
        }
    if isinstance(value, list):
        return [prune_empty(item) for item in value if item not in [None, "", [], {}]]
    return value


def _copy_photo_if_available(output_dir: Path) -> Optional[Path]:
    """
    Cherche photo.jpg / photo.jpeg / photo.png dans le répertoire data et la
    copie dans output_dir en préservant son extension réelle.
    Retourne le Path de destination, ou None si aucune photo trouvée.
    """
    data_dir = settings.cv_path.parent
    for candidate in ("photo.jpg", "photo.jpeg", "photo.png"):
        src = data_dir / candidate
        if src.exists():
            dest = output_dir / candidate
            shutil.copy2(src, dest)
            return dest
    return None


def _ensure_custom_theme_available(output_dir: Path, theme: Optional[str]) -> None:
    """
    RenderCV résout un thème custom en important un package nommé `<theme>` depuis
    le dossier du YAML (= cwd). On copie donc le thème depuis custom_themes_dir vers
    output_dir avant le rendu. No-op pour les thèmes intégrés (ex: engineeringclassic).
    """
    if not theme:
        return
    src = settings.custom_themes_dir / theme
    if not src.is_dir():
        return
    dest = output_dir / theme
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def render_rendercv_data(output_dir: Path, data: Dict[str, Any], base_name: str = "cv_targeted") -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    theme = (data.get("design") or {}).get("theme")
    _ensure_custom_theme_available(output_dir, theme)
    photo_dest = _copy_photo_if_available(output_dir) if theme == "custom1" else None
    if photo_dest:
        # Chemin absolu : rendercv.copy_photo_next_to_typst_file voit le fichier
        # déjà en place dans output_dir et le copie à côté du .typ avec son vrai nom.
        data.setdefault("cv", {})["photo"] = str(photo_dest)
    yaml_path = output_dir / "cv_targeted.yaml"
    pdf_path = output_dir / "cv_targeted.pdf"
    if pdf_path.exists():
        pdf_path.unlink()

    data["settings"] = {
        "render_command": {
            "pdf_path": str(pdf_path),
            "markdown_path": str(output_dir / "cv_targeted_rendercv.md"),
            "html_path": str(output_dir / "cv_targeted.html"),
            "typst_path": str(output_dir / "cv_targeted.typ"),
            "dont_generate_markdown": False,
            "dont_generate_html": True,
            "dont_generate_typst": False,
            "dont_generate_pdf": False,
            "dont_generate_png": True,
        }
    }

    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    rendercv_bin = shutil.which("rendercv")
    if not rendercv_bin:
        return {"cv_targeted.yaml": str(yaml_path)}

    try:
        completed = subprocess.run(
            [rendercv_bin, "render", str(yaml_path)],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        error_path = output_dir / "rendercv_error.txt"
        error_path.write_text("RenderCV a dépassé le délai de 180 secondes et a été interrompu.", encoding="utf-8")
        return {"cv_targeted.yaml": str(yaml_path), "rendercv_error.txt": str(error_path)}

    if completed.returncode != 0:
        error_path = output_dir / "rendercv_error.txt"
        error_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        return {"cv_targeted.yaml": str(yaml_path), "rendercv_error.txt": str(error_path)}

    if not pdf_path.exists():
        error_path = output_dir / "rendercv_error.txt"
        error_path.write_text(
            "RenderCV exited successfully but did not create the expected PDF.\n\n"
            f"Expected PDF: {pdf_path}\n\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}",
            encoding="utf-8",
        )
        return {"cv_targeted.yaml": str(yaml_path), "rendercv_error.txt": str(error_path)}

    files = {"cv_targeted.yaml": str(yaml_path), "cv_targeted.pdf": str(pdf_path)}
    dated_pdf = output_dir / f"{base_name}.pdf"
    if pdf_path.exists() and dated_pdf != pdf_path:
        dated_pdf.write_bytes(pdf_path.read_bytes())
        files[dated_pdf.name] = str(dated_pdf)
    return files


def export_rendercv_files(
    output_dir: Path,
    matching: Dict[str, Any],
    generated: Dict[str, Any],
    audit: Dict[str, Any],
    id_to_evidence: Dict[str, Dict[str, Any]],
    cv_master: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    title = resolve_safe_title(matching, generated, audit)
    base_name = clean_filename(title)
    data = build_rendercv_yaml_data(matching, generated, audit, id_to_evidence, cv_master=cv_master)
    return render_rendercv_data(output_dir, data, base_name=base_name)
