from __future__ import annotations

import re
from typing import Any

# ── Section heading aliases (FR + EN) ────────────────────────────────────────

_SECTION_MAP: dict[str, str] = {
    "resume professionnel":    "Résumé",
    "résumé professionnel":    "Résumé",
    "professional summary":    "Résumé",
    "competences cles":        "Compétences clés",
    "compétences clés":        "Compétences clés",
    "key skills":              "Compétences clés",
    "experiences":             "Expérience",
    "expériences":             "Expérience",
    "experience":              "Expérience",
    "projets":                 "Projets",
    "projects":                "Projets",
    "formation":               "Formation",
    "education":               "Formation",
    "langues":                 "Langues",
    "languages":               "Langues",
}

# Tokens that signal a date component in an experience header
_DATE_TOKENS = re.compile(
    r"^(présent|present|aujourd'hui|today|\d{4}|"
    r"jan\.?|feb\.?|mar\.?|apr\.?|may\.?|jun\.?|jul\.?|aug\.?|sep\.?|oct\.?|nov\.?|dec\.?|"
    r"janv\.?|févr\.?|mars\.?|avr\.?|mai\.?|juin\.?|juil\.?|août\.?|sept\.?|"
    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"january|february|march|april|june|july|august|september|october|november|december"
    r")$",
    re.IGNORECASE,
)


def _is_date_token(s: str) -> bool:
    return bool(_DATE_TOKENS.match(s.strip()))


def _split_experience_header(header: str) -> dict[str, str]:
    """
    Parse "Position - Company - Location - Jan. 2022 - présent"
    back into {position, company, location, date}.

    Strategy: scan parts from the right; collect date tokens until we hit
    something that is clearly not a date, then attribute remaining parts.
    """
    parts = [p.strip() for p in header.split(" - ") if p.strip()]
    if not parts:
        return {"position": header, "company": "", "location": "", "date": ""}

    # Collect date from the right
    date_parts: list[str] = []
    i = len(parts) - 1
    while i >= 0 and (_is_date_token(parts[i]) or (date_parts and _is_date_token(parts[i]))):
        date_parts.insert(0, parts[i])
        i -= 1
        # stop collecting after we've grabbed 2 likely date tokens
        if len(date_parts) >= 2 and not _is_date_token(parts[i] if i >= 0 else ""):
            break

    non_date = parts[: i + 1]
    date = " - ".join(date_parts)

    position = non_date[0] if len(non_date) > 0 else ""
    company  = non_date[1] if len(non_date) > 1 else ""
    location = " - ".join(non_date[2:]) if len(non_date) > 2 else ""

    return {"position": position, "company": company, "location": location, "date": date}


# ── Section parsers ───────────────────────────────────────────────────────────

def _parse_resume(lines: list[str]) -> list[str]:
    text = "\n".join(lines).strip()
    return [text] if text else []


def _parse_skills(lines: list[str]) -> list[dict[str, str]]:
    """
    Parse skill lines into [{label, details}].
    Handles:
      - **Label :** details  →  {label, details}
      - simple text         →  accumulated into {label: "Compétences", details: ...}
    """
    entries: list[dict[str, str]] = []
    loose: list[str] = []

    for raw in lines:
        line = raw.lstrip("- ").strip()
        if not line:
            continue
        # bold label pattern: **Label :** details
        m = re.match(r"^\*\*(.+?)\s*:?\*\*\s*:?\s*(.*)", line)
        if m:
            label   = m.group(1).strip()
            details = m.group(2).strip()
            entries.append({"label": label, "details": details})
        else:
            loose.append(line.lstrip("- ").strip())

    if loose:
        entries.insert(0, {"label": "Compétences", "details": ", ".join(loose)})

    return entries


def _parse_experiences(lines: list[str]) -> list[dict[str, Any]]:
    """
    Parse H3-delimited experience blocks.
    Also handles bold-source format used by generate_en_markdown (no H3, uses **source**).
    """
    experiences: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush():
        if current is not None:
            experiences.append(current)

    for raw in lines:
        line = raw.rstrip()

        # H3 header: ### Position - Company - Location - Date
        if line.startswith("### "):
            flush()
            header = line[4:].strip()
            parsed = _split_experience_header(header)
            current = {**parsed, "summary": "", "highlights": []}
            continue

        # Bold source (EN format): **source**  (standalone line, no trailing text)
        bold_source = re.match(r"^\*\*([^*]+)\*\*\s*$", line)
        if bold_source and current is None:
            flush()
            current = {"position": bold_source.group(1).strip(), "company": "", "location": "", "date": "", "summary": "", "highlights": []}
            continue

        if current is None:
            continue

        if line.startswith("- "):
            bullet = line[2:].strip()
            if bullet:
                current["highlights"].append(bullet)
        elif line and not current["summary"]:
            current["summary"] = line.strip()

    flush()
    return experiences


def _parse_projects(lines: list[str]) -> list[dict[str, Any]]:
    """Parse H3 project blocks into [{name, date, summary, highlights}]."""
    projects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush():
        if current is not None:
            projects.append(current)

    for raw in lines:
        line = raw.rstrip()

        if line.startswith("### "):
            flush()
            header = line[4:].strip()
            # "Name - Date" or "Name — Date"
            m = re.match(r"^(.+?)\s*[-—]\s*(\S.*)$", header)
            if m:
                current = {"name": m.group(1).strip(), "date": m.group(2).strip(), "summary": "", "highlights": []}
            else:
                current = {"name": header, "date": "", "summary": "", "highlights": []}
            continue

        # Bold name (EN format): **name** — date
        bold_proj = re.match(r"^\*\*([^*]+)\*\*(?:\s*[-—]\s*(.+))?$", line)
        if bold_proj and current is None:
            flush()
            current = {"name": bold_proj.group(1).strip(), "date": (bold_proj.group(2) or "").strip(), "summary": "", "highlights": []}
            continue

        if current is None:
            continue

        if line.startswith("- "):
            current["highlights"].append(line[2:].strip())
        elif line and not current["summary"]:
            current["summary"] = line.strip()
        elif line.startswith("Stack:") or line.startswith("Stack :"):
            current["highlights"].append(line.strip())

    flush()
    return projects


def _parse_formation(lines: list[str]) -> list[dict[str, str]]:
    """
    Parse formation lines:
      - **School - Degree - Date**
      - School | Degree | Date  (pipe-delimited, used by some renderers)
    """
    entries: list[dict[str, str]] = []
    for raw in lines:
        line = raw.strip().lstrip("- ").strip()
        # Remove surrounding bold markers
        line = re.sub(r"^\*\*|\*\*$", "", line).strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"\s*[|\-—]\s*", line) if p.strip()]
        entries.append({
            "institution": parts[0] if len(parts) > 0 else "",
            "area":        parts[1] if len(parts) > 1 else "",
            "degree":      "",
            "date":        parts[2] if len(parts) > 2 else "",
        })
    return entries


def _parse_langues(lines: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw in lines:
        line = raw.strip().lstrip("- ").strip()
        if line:
            entries.append({"label": "Langues", "details": line})
    # Merge all into one entry to mirror the original format
    if entries:
        details = " | ".join(e["details"] for e in entries)
        return [{"label": "Langues", "details": details}]
    return []


# ── Contact line helper ───────────────────────────────────────────────────────

def _parse_contact_line(line: str, base_cv: dict) -> dict[str, Any]:
    """Extract email/location/github/linkedin from the pipe-separated contact line."""
    result: dict[str, Any] = {
        "location":       base_cv.get("location", ""),
        "email":          base_cv.get("email", ""),
        "phone":          base_cv.get("phone", ""),
        "social_networks": base_cv.get("social_networks", []),
    }
    for item in [p.strip() for p in line.split("|") if p.strip()]:
        if "@" in item:
            result["email"] = item
        elif "github" in item.lower():
            result["social_networks"] = [
                sn for sn in result["social_networks"] if sn.get("network") != "GitHub"
            ] + [{"network": "GitHub", "username": item.replace("https://github.com/", "").strip("/")}]
        elif "linkedin" in item.lower():
            result["social_networks"] = [
                sn for sn in result["social_networks"] if sn.get("network") != "LinkedIn"
            ] + [{"network": "LinkedIn", "username": item.replace("https://www.linkedin.com/in/", "").strip("/")}]
        elif not result["location"]:
            result["location"] = item
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_markdown_to_rendercv(md: str, base_cv: dict) -> dict:
    """
    Parse a markdown string (as produced by generate_*_markdown) back into
    a rendercv cv dict. Fields not present in the markdown are preserved
    from base_cv (phone, social_networks, etc.).

    Returns the `cv` dict (without the wrapping design/locale keys).
    """
    lines = md.splitlines()

    name    = base_cv.get("name", "")
    headline = base_cv.get("headline", "")
    contact_fields: dict[str, Any] = {
        "location":        base_cv.get("location", ""),
        "email":           base_cv.get("email", ""),
        "phone":           base_cv.get("phone", ""),
        "social_networks": base_cv.get("social_networks", []),
    }

    # ── Parse header (name, headline, contact line) ───────────────────────────
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    # H1 → name
    if idx < len(lines) and lines[idx].startswith("# "):
        name = lines[idx][2:].strip()
        idx += 1

    # Next non-empty line: **headline** or contact line
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines):
        m = re.match(r"^\*\*(.+)\*\*\s*$", lines[idx].strip())
        if m:
            headline = m.group(1).strip()
            idx += 1

    # Contact line (pipe-separated, no markdown prefix)
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines) and "|" in lines[idx] and not lines[idx].startswith("#"):
        contact_fields = _parse_contact_line(lines[idx], base_cv)
        idx += 1

    # ── Split remaining lines into ## sections ────────────────────────────────
    sections_raw: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in lines[idx:]:
        if line.startswith("## "):
            raw_heading = line[3:].strip().lower()
            current_section = _SECTION_MAP.get(raw_heading, raw_heading)
            sections_raw.setdefault(current_section, [])
        elif current_section is not None:
            sections_raw[current_section].append(line)

    # ── Parse each section ────────────────────────────────────────────────────
    sections: dict[str, Any] = {}

    resume_lines = sections_raw.get("Résumé", [])
    if resume_lines:
        parsed = _parse_resume(resume_lines)
        if parsed:
            sections["Résumé"] = parsed

    skills_lines = sections_raw.get("Compétences clés", [])
    if skills_lines:
        parsed_skills = _parse_skills(skills_lines)
        if parsed_skills:
            sections["Compétences clés"] = parsed_skills

    exp_lines = sections_raw.get("Expérience", [])
    if exp_lines:
        parsed_exp = _parse_experiences(exp_lines)
        if parsed_exp:
            sections["Expérience"] = parsed_exp

    proj_lines = sections_raw.get("Projets", [])
    if proj_lines:
        parsed_proj = _parse_projects(proj_lines)
        if parsed_proj:
            sections["Projets"] = parsed_proj

    form_lines = sections_raw.get("Formation", [])
    if form_lines:
        parsed_form = _parse_formation(form_lines)
        if parsed_form:
            sections["Formation"] = parsed_form

    lang_lines = sections_raw.get("Langues", [])
    if lang_lines:
        parsed_lang = _parse_langues(lang_lines)
        if parsed_lang:
            sections["Langues"] = parsed_lang

    # ── Assemble cv dict ──────────────────────────────────────────────────────
    cv: dict[str, Any] = {
        "name":     name,
        "headline": headline,
        **contact_fields,
        "sections": sections,
    }

    # Remove None / empty fields
    return {k: v for k, v in cv.items() if v not in (None, "", [], {})}
