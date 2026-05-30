from typing import Any, Dict, List


def add_evidence(bank: List[Dict[str, Any]], category: str, source: str, field: str, text: Any) -> None:
    if text is None:
        return
    text = str(text).strip()
    if not text:
        return
    bank.append({
        "id": f"EV{len(bank) + 1:03d}",
        "category": category,
        "source": source,
        "field": field,
        "text": text,
    })


def format_period(period: Dict[str, Any]) -> str:
    if not isinstance(period, dict):
        return ""
    start = period.get("debut")
    end = period.get("fin")
    if isinstance(end, str) and "en cours" in end.lower():
        end = None
    if start and end:
        return f"{start}-{end}"
    if start:
        return str(start)
    if end:
        return str(end)
    return ""


def format_date_range(start: Any, end: Any, is_current: bool = False) -> str:
    def year(value: Any) -> str:
        value = str(value or "").strip()
        return value[:4] if len(value) >= 4 else value

    start_year = year(start)
    end_year = "present" if is_current else year(end)
    if start_year and end_year:
        if start_year == end_year:
            return start_year
        return f"{start_year}-{end_year}"
    return start_year or end_year


def build_source(*parts: Any) -> str:
    return " - ".join(str(part).strip() for part in parts if part)


def add_list(bank: List[Dict[str, Any]], category: str, source: str, field: str, values: Any) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        if isinstance(value, dict):
            add_evidence(bank, category, source, field, value.get("nom") or value.get("name") or value)
        else:
            add_evidence(bank, category, source, field, value)


def build_legacy_evidence(cv: Dict[str, Any], bank: List[Dict[str, Any]]) -> None:
    profile = cv.get("profile", {})
    identity = profile.get("identity", {})
    positioning = profile.get("professional_positioning", {})

    add_evidence(bank, "identity", "profile.identity", "current_title", identity.get("current_title", ""))
    add_evidence(bank, "profile", "profile.professional_positioning", "main_positioning", positioning.get("main_positioning", ""))
    add_evidence(bank, "profile", "profile.professional_positioning", "short_pitch", positioning.get("short_pitch", ""))
    add_list(bank, "profile_strength", "profile.professional_positioning.key_strengths", "key_strength", positioning.get("key_strengths", []))

    for exp in cv.get("experiences", []):
        company = exp.get("company", "Experience")
        role = exp.get("role", "")
        source = f"{company} - {role}"

        add_evidence(bank, "experience", source, "role", role)
        add_evidence(bank, "experience", source, "context", exp.get("context", ""))
        add_evidence(bank, "experience", source, "description", exp.get("description", ""))
        add_list(bank, "experience_mission", source, "missions", exp.get("missions", []))
        add_list(bank, "experience_achievement", source, "achievements", exp.get("achievements", []))
        add_list(bank, "experience_tech", source, "technical_environment", exp.get("technical_environment", []))

    for edu in cv.get("education", []):
        school = edu.get("school", "Formation")
        degree = edu.get("degree", "")
        source = f"{school} - {degree}"
        add_evidence(bank, "education", source, "degree", degree)
        add_evidence(bank, "education", source, "field", edu.get("field", ""))
        add_list(bank, "education_skill", source, "skills", edu.get("skills", []))

    for skill_group, values in cv.get("skills", {}).items():
        if isinstance(values, list):
            add_list(bank, "skill", f"skills.{skill_group}", skill_group, values)

    for lang in cv.get("languages", []):
        language = lang.get("language", "")
        level = lang.get("level", "")
        add_evidence(bank, "language", "languages", language, f"{language} : {level}")
        add_list(bank, "language_detail", f"languages.{language}", "details", lang.get("details", []))

    for project in cv.get("projects_and_themes", []):
        name = project.get("name", "Projet")
        add_evidence(bank, "project", name, "description", project.get("description", ""))
        add_list(bank, "project_skill", name, "associated_skills", project.get("associated_skills", []))

    add_list(bank, "soft_skill", "soft_skills", "soft_skill", cv.get("soft_skills", []))


def build_database_evidence(cv: Dict[str, Any], bank: List[Dict[str, Any]]) -> None:
    profile = cv.get("profile", {})
    full_name = " ".join(part for part in [profile.get("firstName"), profile.get("lastName")] if part)
    add_evidence(bank, "identity", "profile", "nom", full_name)
    add_evidence(bank, "identity", "profile", "titre", profile.get("title"))
    add_evidence(bank, "profile", "profile", "summary", profile.get("summary"))

    location = profile.get("location", {})
    if isinstance(location, dict):
        add_evidence(bank, "location", "profile.location", "city", location.get("city"))
        add_evidence(bank, "location", "profile.location", "country", location.get("country"))

    contact = profile.get("contact", {})
    if isinstance(contact, dict):
        add_evidence(bank, "contact", "profile.contact", "email", contact.get("email"))
        add_evidence(bank, "contact", "profile.contact", "telephone", contact.get("phone"))
        add_evidence(bank, "contact", "profile.contact", "linkedin", contact.get("linkedin"))
        add_evidence(bank, "contact", "profile.contact", "github", contact.get("github"))

    add_list(bank, "profile_title", "targetRoles", "targetRoles", cv.get("targetRoles", []))

    skills = cv.get("skills", {})
    technical = skills.get("technical", {}) if isinstance(skills, dict) else {}
    if isinstance(technical, dict):
        for group, values in technical.items():
            add_list(bank, "skill", f"skills.technical.{group}", group, values)
    if isinstance(skills, dict):
        add_list(bank, "soft_skill", "skills.softSkills", "softSkills", skills.get("softSkills", []))
        add_list(bank, "methodology", "skills.methodologies", "methodologies", skills.get("methodologies", []))

    for exp in cv.get("experiences", []):
        company = exp.get("company") or "Experience"
        role = exp.get("position") or ""
        period = format_date_range(exp.get("startDate"), exp.get("endDate"), bool(exp.get("isCurrent")))
        location_data = exp.get("location", {})
        location = ""
        if isinstance(location_data, dict):
            location = ", ".join(part for part in [location_data.get("city"), location_data.get("country")] if part)
        source = build_source(company, role, period)

        add_evidence(bank, "experience", source, "position", role)
        add_evidence(bank, "experience", source, "company", company)
        add_evidence(bank, "experience", source, "periode", period)
        add_evidence(bank, "experience", source, "location", location)
        add_evidence(bank, "experience", source, "contractType", exp.get("contractType"))
        add_evidence(bank, "experience", source, "summary", exp.get("summary"))
        add_list(bank, "experience_mission", source, "missions", exp.get("missions", []))
        add_list(bank, "experience_tech", source, "technologies", exp.get("technologies", []))
        add_list(bank, "experience_skill", source, "keywords", exp.get("keywords", []))
        for achievement in exp.get("achievements", []):
            if isinstance(achievement, dict):
                add_evidence(bank, "experience_achievement", source, "description", achievement.get("description"))
                add_evidence(bank, "experience_achievement", source, "impact", achievement.get("impact"))
            else:
                add_evidence(bank, "experience_achievement", source, "achievement", achievement)

    for edu in cv.get("education", []):
        school = edu.get("school", "Formation")
        degree = edu.get("degree", "")
        period = format_date_range(edu.get("startDate"), edu.get("endDate"), bool(edu.get("isCurrent")))
        source = build_source(school, degree, period)
        add_evidence(bank, "education", source, "ecole", school)
        add_evidence(bank, "education", source, "intitule", degree)
        add_evidence(bank, "education", source, "periode", period)
        add_evidence(bank, "education", source, "field", edu.get("field"))
        add_list(bank, "education_skill", source, "relevantCourses", edu.get("relevantCourses", []))

    for lang in cv.get("languages", []):
        language = lang.get("language", "")
        level = lang.get("level", "")
        add_evidence(bank, "language", "languages", language, f"{language} : {level}")

    for cert in cv.get("certifications", []):
        add_evidence(bank, "certification", "certifications", "name", cert.get("name"))

    for project in cv.get("projects", []):
        name = project.get("name", "Projet")
        period = format_date_range(project.get("startDate"), project.get("endDate"))
        source = build_source(name, period)
        add_evidence(bank, "project", source, "description", project.get("description"))
        add_evidence(bank, "project", source, "problemSolved", project.get("problemSolved"))
        add_list(bank, "project_action", source, "features", project.get("features", []))
        add_list(bank, "project_result", source, "highlights", project.get("highlights", []))
        add_list(bank, "project_tech", source, "technologies", project.get("technologies", []))


def build_rich_evidence(cv: Dict[str, Any], bank: List[Dict[str, Any]]) -> None:
    profile = cv.get("profil", {})
    full_name = " ".join(part for part in [profile.get("prenom"), profile.get("nom")] if part)
    add_evidence(bank, "identity", "profil", "nom", full_name)
    add_evidence(bank, "identity", "profil", "titre_cible_principal", profile.get("titre_cible_principal"))
    location = profile.get("localisation", {})
    if isinstance(location, dict):
        add_evidence(bank, "location", "profil.localisation", "ville", location.get("ville"))
        add_evidence(bank, "location", "profil.localisation", "pays", location.get("pays"))
    contact = profile.get("contact", {})
    if isinstance(contact, dict):
        add_evidence(bank, "contact", "profil.contact", "email", contact.get("email"))
        add_evidence(bank, "contact", "profil.contact", "telephone", contact.get("telephone"))
        add_evidence(bank, "contact", "profil.contact", "linkedin", contact.get("linkedin"))
        add_evidence(bank, "contact", "profil.contact", "github", contact.get("github"))
    add_evidence(bank, "profile", "profil", "resume_court", profile.get("resume_court"))
    add_evidence(bank, "profile", "profil", "resume_long", profile.get("resume_long"))
    add_list(bank, "profile_title", "profil.titres_alternatifs", "titres_alternatifs", profile.get("titres_alternatifs", []))
    add_list(bank, "skill", "profil.mots_cles", "mots_cles", profile.get("mots_cles", []))

    for exp in cv.get("experiences", []):
        company = exp.get("entreprise") or exp.get("company") or "Experience"
        role = exp.get("poste") or exp.get("role") or ""
        period = format_period(exp.get("periode", {}))
        location = exp.get("localisation", "")
        source = build_source(company, role, period)

        add_evidence(bank, "experience", source, "poste", role)
        add_evidence(bank, "experience", source, "entreprise", company)
        add_evidence(bank, "experience", source, "periode", period)
        add_evidence(bank, "experience", source, "localisation", location)
        add_evidence(bank, "experience", source, "contexte", exp.get("contexte"))
        add_list(bank, "experience_mission", source, "missions", exp.get("missions", []))
        add_list(bank, "experience_tech", source, "stack", exp.get("stack", []))
        add_list(bank, "experience_skill", source, "competences_clefs", exp.get("competences_clefs", []))
        add_list(bank, "experience_note", source, "notes", exp.get("notes", []))

    for edu in cv.get("formations", []):
        school = edu.get("ecole", "Formation")
        degree = edu.get("intitule", "")
        period = format_period(edu.get("periode", {}))
        source = build_source(school, degree, period)

        add_evidence(bank, "education", source, "intitule", degree)
        add_evidence(bank, "education", source, "ecole", school)
        add_evidence(bank, "education", source, "periode", period)
        add_evidence(bank, "education", source, "specialite", edu.get("specialite"))
        add_evidence(bank, "education", source, "modalite", edu.get("modalite"))
        add_list(bank, "education_skill", source, "competences_associees", edu.get("competences_associees", []))

        thesis = edu.get("memoire", {})
        if isinstance(thesis, dict):
            add_evidence(bank, "education_thesis", source, "memoire_titre", thesis.get("titre"))
            add_list(bank, "education_thesis", source, "memoire_themes", thesis.get("themes", []))

    for lang in cv.get("langues", []):
        language = lang.get("langue", "")
        level = lang.get("niveau", "")
        cert = lang.get("certification", {})
        cert_text = ""
        if isinstance(cert, dict) and cert.get("nom"):
            cert_score = cert.get("score", "")
            cert_text = f" - {cert.get('nom')} {cert_score}".rstrip()
        add_evidence(bank, "language", "langues", language, f"{language} : {level}{cert_text}")
        add_list(bank, "language_detail", f"langues.{language}", "preuves", lang.get("preuves", []))

    for group, values in cv.get("competences", {}).items():
        if not isinstance(values, list):
            continue
        for skill in values:
            if isinstance(skill, dict):
                name = skill.get("nom")
                level = skill.get("niveau")
                source = f"competences.{group}"
                add_evidence(bank, "skill", source, group, f"{name} ({level})" if level else name)
                add_list(bank, "skill_evidence", f"{source}.{name}", "preuves", skill.get("preuves", []))
            else:
                add_evidence(bank, "skill", f"competences.{group}", group, skill)

    for project in cv.get("projets_realises", []):
        name = project.get("nom", "Projet")
        period = format_period(project.get("periode", {}))
        source = build_source(name, project.get("entreprise"), period)
        add_evidence(bank, "project", source, "nom", name)
        add_evidence(bank, "project", source, "contexte", project.get("contexte"))
        add_evidence(bank, "project", source, "role", project.get("role"))
        add_list(bank, "project_action", source, "actions", project.get("actions", []))
        add_list(bank, "project_result", source, "resultats", project.get("resultats", []))
        add_list(bank, "project_tech", source, "stack", project.get("stack", []))
        add_list(bank, "project_skill", source, "competences_associees", project.get("competences_associees", []))
        add_list(bank, "project_proof", source, "preuves_cv", project.get("preuves_cv", []))

    valid_bullets = cv.get("preuves_et_bullets_cv", {}).get("bullets_generiques_valides", [])
    for item in valid_bullets:
        if isinstance(item, dict):
            add_evidence(bank, "cv_bullet", item.get("orientation", "bullets_generiques_valides"), "bullet", item.get("bullet"))

    ats_keywords = cv.get("preuves_et_bullets_cv", {}).get("mots_cles_ats", [])
    add_list(bank, "skill", "preuves_et_bullets_cv.mots_cles_ats", "mots_cles_ats", ats_keywords)


def build_evidence_bank(cv: Dict[str, Any]) -> List[Dict[str, Any]]:
    bank: List[Dict[str, Any]] = []
    is_database_schema = isinstance(cv.get("profile"), dict) and (
        "firstName" in cv.get("profile", {}) or "lastName" in cv.get("profile", {})
    )
    if is_database_schema:
        build_database_evidence(cv, bank)
    elif any(key in cv for key in ["profil", "formations", "langues", "competences", "projets_realises"]):
        build_rich_evidence(cv, bank)
    elif any(key in cv for key in ["profile", "education", "skills", "languages", "projects_and_themes"]):
        build_legacy_evidence(cv, bank)
    return bank


def evidence_by_id(bank: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in bank}
