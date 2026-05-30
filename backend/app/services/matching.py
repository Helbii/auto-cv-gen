"""
Extraction et classification des exigences d'une offre d'emploi,
pipeline de matching et calcul du score ATS.
"""
import re
from typing import Any, Dict, List, Optional, Set

from .semantic_graph import find_best_semantic_evidence
from .text_utils import normalize_text


# ── Constantes ────────────────────────────────────────────────────────────────

GENERIC_STOPWORDS = {
    "avec", "afin", "ainsi", "alors", "autres", "avez", "avoir", "besoin", "bonne", "bonnes",
    "candidat", "candidature", "chez", "comme", "competence", "competences", "connaissance",
    "connaissances", "dans", "demande", "demandes", "emploi", "entreprise", "equipe",
    "equipes", "etre", "faire", "formation", "grace", "heures", "interne", "leurs", "mission",
    "missions", "nous", "offre", "outil", "outils", "participer", "poste", "pour", "profil",
    "projet", "projets", "recherche", "recherchons", "secteur", "selon", "travail", "vous",
    "developpeur", "developpeuse", "ingenieur", "ingenieure", "junior", "senior", "confirme",
    "confirmee", "souhaitant", "evoluer",
    "paris", "arrondissement", "localiser", "mappy", "publie", "publié", "localisation",
}

INVALID_REQUIREMENT_PHRASES = {
    "h/f", "hf", "75", "paris la", "paris", "arrondissement", "localiser", "mappy",
    "product owner", "developpement et l'evolution", "vos", "recueillir", "proposer",
    "creer ou modifier", "developper des composants specifiques avec",
}

LOCATION_NOISE_TERMS = {
    "paris", "lyon", "marseille", "toulouse", "nice", "nantes", "montpellier",
    "strasbourg", "bordeaux", "lille", "arrondissement", "localiser", "mappy",
    "publie", "publication", "localisation", "teletravail", "site",
}

# Termes contractuels qui ne sont jamais des exigences techniques
CONTRACTUAL_NOISE_TERMS = {
    "heures", "heure", "hebdomadaire", "semaine",
    "cdi", "cdd", "alternance", "apprentissage", "interim",
    "tjm", "salaire", "remuneration", "avantages", "rtt", "rtts",
    "risques", "contraintes", "ecran",
    "bts", "dut", "iut", "licence", "master",
    "handicap", "obligation", "beneficiaires",
}

GENERIC_REQUIREMENT_HINTS = [
    "support technique", "support applicatif", "analyse d'incidents", "documentation technique",
    "gestion de projet", "tests", "recette", "maintenance", "optimisation",
    "developpement logiciel", "developpement web", "developpement applicatif",
    "frontend", "front-end", "react", "javascript", "typescript", "interface web",
    "agile", "user stories", "ux", "design system", "accessibilite", "tests unitaires",
    "api", "rest", "soap", "sql", "cloud", "devops", "cybersecurite", "data", "ia",
    "crm", "erp", "automatisation", "anglais",
]

TITLE_UNSAFE_IF_NOT_CONFIRMED = {
    "sap", "peoplesoft", "jenkins", "ansible", "nexus", "xldeploy", "perl", "php",
    "peoplecode", "application engine", "component interface", "sqr", "pl/sql", "plsql",
    "react", "react.js", "typescript", "angular", "vue", "java", ".net", "c#",
    "javascript", "node.js", "nodejs", "ruby", "golang", "swift", "kotlin",
}

SAFE_TITLE_QUALIFIERS = [
    "react", "frontend", "front-end", "interface web", "javascript", "typescript",
    "full-stack", "backend", "api", "web", "ux", "agile", "support applicatif",
    "production informatique", "exploitation si", "automatisation", "linux", "devops",
    "python", "anglais", "maintenance",
]

SAFE_CONTEXT_TERMS = {
    "junior": ["junior", "profil junior"],
    "client": ["client", "intervenir chez un client"],
    "hybride": ["hybride", "teletravail", "télétravail"],
    "production informatique": ["production informatique", "ingenieur de production"],
    "support applicatif": ["support applicatif", "support technique applicatif"],
    "systeme d'information": ["systeme d'information", "système d'information", " si "],
    "anglais professionnel": ["anglais", "oral", "ecrit", "écrit"],
    "front-end": ["front-end", "frontend", "front end"],
    "react": ["react", "react.js", "reactjs"],
    "interface web": ["interface", "interfaces", "application metier", "application métier"],
    "agile": ["agile", "ceremonies agile", "cérémonies agile", "grooming"],
    "user stories": ["user stories", "user story"],
    "ux": ["ux", "experience utilisateur", "expérience utilisateur"],
    "design system": ["design system"],
    "accessibilite": ["accessibilite", "accessibilité"],
    "eco-conception": ["eco-conception", "éco-conception"],
    "performance web": ["performance"],
    "tests unitaires": ["tests unitaires", "test unitaire"],
    "rgpd": ["rgpd"],
    "mise en production": ["mise en production", "mises en production"],
}


# ── Score de matching ─────────────────────────────────────────────────────────

def _requirement_weight(requirement: str) -> float:
    """
    Pondère l'importance d'une exigence pour le scoring ATS.
    2.0 → outil/langage/plateforme spécifique (Jenkins, SAP, Python…)
    1.5 → domaine technique précis (DevOps, CI/CD, API REST…)
    1.0 → compétence fonctionnelle générique (documentation, analyse…)
    """
    # Outil ou langage nommé : contient des majuscules groupées ou des chars spéciaux
    if re.search(r"[A-Z]{2,}", requirement):                  # SQL, SAP, ERP, API…
        return 2.0
    if any(c in requirement for c in "+#./"):                  # C#, PL/SQL, React.js
        return 2.0
    if any(w[0].isupper() for w in requirement.split()[1:] if len(w) > 2):  # "framework React"
        return 2.0

    # Domaine technique précis
    tech_domains = {
        "api", "rest", "soap", "sql", "devops", "cicd", "cloud", "iot",
        "data", "machine learning", "deep learning", "microservices",
        "docker", "linux", "git", "python", "javascript", "java",
        "backend", "frontend", "pipeline", "automatisation",
    }
    normalized = normalize_text(requirement)
    if any(d in normalized for d in tech_domains):
        return 1.5

    return 1.0


def compute_matching_score_details(matching: Dict[str, Any]) -> Dict[str, Any]:
    requirements = matching.get("requirements_analysis", [])
    if not requirements:
        return {
            "score": 0,
            "base_score": 0,
            "bonus_points": 0,
            "confirmed_points": 0,
            "transferable_points": 0,
            "weak_points": 0,
            "critical_missing_penalty": 0,
            "other_missing_penalty": 0,
            "confirmed_count": 0,
            "transferable_count": 0,
            "weak_count": 0,
            "absent_count": 0,
            "critical_missing": [],
            "formula": "Aucune exigence exploitable detectee dans l'offre.",
        }

    score = 0.0
    max_score = 0.0
    confirmed_score = 0.0
    transferable_score = 0.0
    weak_score = 0.0
    critical_missing_loss = 0.0
    other_missing_loss = 0.0
    counts = {"CONFIRMED": 0, "TRANSFERABLE": 0, "WEAK": 0, "ABSENT": 0}
    critical_missing: List[str] = []
    training_context = bool(matching.get("training_context"))

    for req in requirements:
        requirement = req.get("requirement", "")
        weight = _requirement_weight(requirement)
        potential = 8 * weight
        max_score += potential
        status = req.get("status")
        if status in counts:
            counts[status] += 1
        if status == "CONFIRMED":
            earned = potential
            score += earned
            confirmed_score += earned
        elif status == "TRANSFERABLE":
            earned = (7 if training_context else 6.5) * weight
            score += earned
            transferable_score += earned
        elif status == "WEAK":
            earned = (6 if training_context else 2) * weight
            score += earned
            weak_score += earned
            loss = max(potential - earned, 0)
            if weight >= 1.5:
                critical_missing_loss += loss
                critical_missing.append(str(requirement))
            else:
                other_missing_loss += loss
        elif status == "ABSENT":
            if weight >= 1.5:
                critical_missing_loss += potential
                critical_missing.append(str(requirement))
            else:
                other_missing_loss += potential

    def pct(value: float) -> int:
        return round((value / max_score) * 100) if max_score else 0

    base_score = pct(score)
    final_score = base_score
    bonus_points = 0
    if training_context and base_score >= 55:
        final_score = min(88, base_score + 8)
        bonus_points = final_score - base_score

    return {
        "score": final_score,
        "base_score": base_score,
        "bonus_points": bonus_points,
        "confirmed_points": pct(confirmed_score),
        "transferable_points": pct(transferable_score),
        "weak_points": pct(weak_score),
        "critical_missing_penalty": -pct(critical_missing_loss),
        "other_missing_penalty": -pct(other_missing_loss),
        "confirmed_count": counts["CONFIRMED"],
        "transferable_count": counts["TRANSFERABLE"],
        "weak_count": counts["WEAK"],
        "absent_count": counts["ABSENT"],
        "critical_missing": critical_missing[:8],
        "formula": "Score = points acquis / potentiel total, avec bonus junior/formation si detecte.",
    }


def compute_matching_score(matching: Dict[str, Any]) -> int:
    return int(compute_matching_score_details(matching).get("score", 0))


# ── Utilitaires texte/titre ───────────────────────────────────────────────────

def _contains_phrase(text: str, phrases: List[str]) -> bool:
    normalized = normalize_text(text)
    for phrase in phrases:
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            continue
        if len(normalized_phrase) <= 4:
            if re.search(r"\b" + re.escape(normalized_phrase) + r"\b", normalized):
                return True
        elif normalized_phrase in normalized:
            return True
    return False


def _display_text(value: str) -> str:
    replacements = {
        "devops": "DevOps", "api": "API", "rest": "REST", "sql": "SQL", "sap": "SAP",
        "si": "SI", "python": "Python", "linux": "Linux", "developpeur": "Développeur",
        "ingenieur": "Ingénieur", "ingenieure": "Ingénieure", "react": "React",
        "react.js": "React.js", "javascript": "JavaScript", "typescript": "TypeScript",
        "frontend": "Front-End", "front-end": "Front-End", "full-stack": "Full-Stack",
        "ux": "UX", "rgpd": "RGPD", "ci/cd": "CI/CD",
    }
    normalized_value = normalize_text(value)
    if normalized_value in replacements:
        return replacements[normalized_value]
    words = []
    for word in str(value).split():
        clean = normalize_text(word)
        words.append(replacements.get(clean, word))
    return " ".join(words).strip()


def _title_piece(value: str) -> str:
    value = _display_text(value)
    if not value:
        return value
    return value[:1].upper() + value[1:]


def _clean_requirement(value: str) -> str:
    value = re.sub(r"^[\s*•\-•:;,.]+", "", value.strip())
    value = re.sub(r"[\s:;,.]+$", "", value)
    value = re.sub(r"\s+(?:du|de|des|d')$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value


def _clean_offer_title(value: str) -> str:
    # "Sia recrute un ...", "entreprise recherche une ...", etc.
    value = re.sub(r"^\s*\S+\s+(?:recrute|recherche|cherche|embauche|recrutons)\s+(?:un|une)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s*(?:nous\s+)?recherchons\s+(?:un|une)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\([^)]*h\s*/?\s*f[^)]*\)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bH\s*/?\s*F\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bIng[eé]nieur\s*/\s*Ing[eé]nieure\b", "Ingénieur", value, flags=re.IGNORECASE)
    value = re.split(r"\s+(?:pour|afin|au sein|dans|avec|qui|dont)\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+[—–-]\s+", value, maxsplit=1)[0]
    value = re.sub(r"\b(?:a|à|sur|chez)\s+[A-ZÉÈÀÂÎÏÔÛÙÇ][\w'ÉÈÀÂÎÏÔÛÙÇ-]*(?:\s+\d{1,2}(?:er|e|eme|ème)?(?:\s+arrondissement)?)?", "", value)
    value = re.sub(r"\b(?:Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Montpellier|Strasbourg|Bordeaux|Lille|La Défense|La Defense)\b(?:\s+\d{1,2}(?:er|e|eme|ème)?)?", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:0[1-9]|[1-8]\d|9[0-8])\b", "", value)
    value = re.sub(r"\b\d{5}\b", "", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" -–—,.;:")
    return value


# ── Extraction du titre de l'offre ────────────────────────────────────────────

def extract_offer_title(job_offer: str) -> str:
    text = str(job_offer or "").strip()
    if not text:
        return ""
    candidates = []
    first_sentence = re.split(r"\.\s+", text, maxsplit=1)[0]
    first_chunk = re.split(r"\s+[—–-]\s+", first_sentence, maxsplit=1)[0]
    if 5 <= len(first_chunk) <= 100:
        candidates.append(_clean_offer_title(first_chunk))

    normalized = normalize_text(text)
    patterns = [
        r"nous recherchons\s+(?:un|une)\s+([^.\n]{4,90})",
        r"recherchons\s+(?:un|une)\s+([^.\n]{4,90})",
        r"(administrateur|ingenieur|developpeur|consultant|technicien|analyste)[^.\n]{0,80}",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            candidates.append(_clean_offer_title(match.group(1) if match.groups() else match.group(0)).capitalize())

    candidates = [c for c in dict.fromkeys(candidates) if c]
    if not candidates:
        return ""

    specific_terms = [
        "front", "frontend", "front-end", "react", "javascript", "typescript",
        "python", "backend", "sap", "devops", "data", "full-stack", "fullstack", "agile",
    ]

    def score(candidate: str) -> tuple:
        nc = normalize_text(candidate)
        specificity = sum(1 for t in specific_terms if t in nc)
        generic_penalty = 1 if nc in {"developpeur", "developpeur web", "ingenieur"} else 0
        return (specificity - generic_penalty, len(candidate))

    return sorted(candidates, key=score, reverse=True)[0]


def _unsafe_title_terms(matching: Dict[str, Any]) -> Set[str]:
    unsafe: Set[str] = set()
    confirmed_text = " ".join(
        normalize_text(req.get("requirement", ""))
        for req in matching.get("requirements_analysis", [])
        if req.get("status") == "CONFIRMED"
    )
    for req in matching.get("requirements_analysis", []):
        requirement = normalize_text(req.get("requirement", ""))
        if req.get("status") != "CONFIRMED":
            for term in TITLE_UNSAFE_IF_NOT_CONFIRMED:
                if term in requirement and normalize_text(term) not in confirmed_text:
                    unsafe.add(term)
    return unsafe


def _safe_title_segment(title: str, unsafe_terms: Set[str]) -> str:
    segments = [s.strip() for s in re.split(r"\s*/\s*|\s+\|\s+", title) if s.strip()]
    if not segments:
        segments = [title]
    ranked = sorted(
        segments,
        key=lambda s: (
            sum(1 for t in unsafe_terms if t in normalize_text(s)),
            0 if "ingenieur" in normalize_text(s) else 1,
            len(s),
        ),
    )
    selected = ranked[0]
    for term in unsafe_terms:
        selected = re.sub(r"\b" + re.escape(term) + r"\b", "", selected, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", selected).strip(" -–—,.;:/")


def build_dynamic_title(matching: Dict[str, Any], job_offer: str) -> str:
    offer_title = extract_offer_title(job_offer)
    base = _safe_title_segment(offer_title, _unsafe_title_terms(matching)) if offer_title else ""
    if not base:
        recommended = matching.get("recommended_title", "")
        # Guard : un recommended_title > 10 mots est un résumé professionnel, pas un titre
        base = recommended if recommended and len(recommended.split()) <= 10 else "CV cible"

    normalized_offer = normalize_text(job_offer)
    if "junior" in normalized_offer and "junior" not in normalize_text(base):
        base = f"{base} junior"

    safe_requirements = [
        normalize_text(req.get("requirement", ""))
        for req in matching.get("requirements_analysis", [])
        if req.get("status") in {"CONFIRMED", "TRANSFERABLE"}
    ]
    normalized_base = normalize_text(base)
    frontend_title = any(t in normalized_base for t in ["front", "frontend", "react", "web"])
    production_title = any(t in normalized_base for t in ["production", "exploitation", "support"])
    qualifiers = []
    for qualifier in SAFE_TITLE_QUALIFIERS:
        if frontend_title and any(t in normalized_base for t in ["react", "front-end", "frontend"]):
            break
        if frontend_title and qualifier in {"devops", "linux", "automatisation", "support applicatif", "production informatique", "exploitation si"}:
            continue
        if production_title and qualifier in {"production informatique", "exploitation si"}:
            continue
        if production_title and qualifier in {"frontend", "front-end", "react", "javascript", "ux", "interface web"}:
            continue
        if any(qualifier in req for req in safe_requirements) and qualifier not in normalized_base:
            qualifiers.append(_title_piece(qualifier))
        max_q = 1 if any(t in normalized_base for t in ["front", "react", "python", "devops", "production", "backend"]) else 2
        if len(qualifiers) >= max_q:
            break

    if qualifiers:
        return f"{_title_piece(base)} - {' & '.join(qualifiers)}"
    return _title_piece(base)


def extract_safe_context_terms(job_offer: str, matching: Dict[str, Any]) -> List[str]:
    normalized_offer = normalize_text(job_offer)
    terms = []
    for label, variants in SAFE_CONTEXT_TERMS.items():
        if any(normalize_text(v) in normalized_offer for v in variants):
            terms.append(label)
    for req in matching.get("requirements_analysis", []):
        if req.get("status") not in {"CONFIRMED", "TRANSFERABLE"}:
            continue
        requirement = normalize_text(req.get("requirement", ""))
        for label in [
            "front-end", "react", "interface web", "agile", "user stories", "ux", "design system",
            "accessibilite", "performance web", "tests unitaires", "rgpd", "mise en production",
            "support applicatif", "production informatique", "automatisation", "maintenance", "devops",
        ]:
            if label in requirement:
                terms.append(label)
    return list(dict.fromkeys(terms))[:8]


# ── Exigences implicites (années d'expérience, niveau d'études) ────────────────

def _exp_months(start: Any, end: Any, is_current: bool = False) -> tuple:
    """Retourne (start_months, end_months) en mois absolus, ou (None, None)."""
    def to_months(v):
        v = str(v or "").strip()
        m = re.match(r"^(\d{4})-(\d{1,2})", v)
        if m:
            return int(m.group(1)) * 12 + int(m.group(2)) - 1
        m = re.match(r"^(\d{4})", v)
        if m:
            return int(m.group(1)) * 12
        return None
    import datetime
    s = to_months(start)
    e = (datetime.date.today().year * 12 + datetime.date.today().month - 1) if is_current else to_months(end)
    return s, e


def candidate_total_years(cv_master: Optional[Dict[str, Any]]) -> float:
    """Années d'expérience professionnelle totales (intervalles fusionnés, sans double-comptage)."""
    if not isinstance(cv_master, dict):
        return 0.0
    intervals = []
    for exp in cv_master.get("experiences", []):
        s, e = _exp_months(exp.get("startDate"), exp.get("endDate"), bool(exp.get("isCurrent")))
        if s is not None and e is not None and e >= s:
            intervals.append((s, e))
    if not intervals:
        return 0.0
    intervals.sort()
    total, cur_s, cur_e = 0, intervals[0][0], intervals[0][1]
    for s, e in intervals[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return round(total / 12, 1)


# Diplôme → niveau Bac+N
_DEGREE_LEVELS = [
    (5, ["bac+5", "bac +5", "master", "ingenieur", "ingénieur", "mastere", "msc", "mba", "doctorat", "phd"]),
    (3, ["bac+3", "bac +3", "licence", "bachelor", "but"]),
    (2, ["bac+2", "bac +2", "dut", "bts", "deug"]),
]


def candidate_max_education(cv_master: Optional[Dict[str, Any]]) -> int:
    """Niveau de diplôme le plus élevé du candidat (Bac+N), 0 si inconnu."""
    if not isinstance(cv_master, dict):
        return 0
    best = 0
    for edu in cv_master.get("education", []):
        text = normalize_text(f"{edu.get('degree', '')} {edu.get('field', '')}")
        for level, keywords in _DEGREE_LEVELS:
            if any(kw in text for kw in keywords):
                best = max(best, level)
    return best


def _required_years_from_offer(normalized_offer: str) -> Optional[int]:
    """Extrait le nombre minimum d'années d'expérience demandé par l'offre."""
    patterns = [
        r"(\d+)\s*(?:a|à)\s*\d+\s*ans?\s+d",        # "3 à 5 ans d'..."
        r"(\d+)\s*ans?\s+(?:d['e]\s*)?(?:experience|exp)",
        r"experience\s+(?:de\s+|d['e]\s*)?(?:minimum\s+)?(\d+)\s*ans?",
        r"minimum\s+(?:de\s+)?(\d+)\s*ans?",
        r"(\d+)\s*\+\s*ans?",
        r"(\d+)\s*ans?\s+minimum",
        r"au moins\s+(\d+)\s*ans?",
    ]
    for pattern in patterns:
        m = re.search(pattern, normalized_offer)
        if m:
            try:
                val = int(m.group(1))
                if 1 <= val <= 20:
                    return val
            except (ValueError, IndexError):
                continue
    return None


def _required_education_from_offer(normalized_offer: str) -> Optional[int]:
    """Extrait le niveau de diplôme minimum demandé (Bac+N), ou None."""
    # "Bac+2 à Bac+5" → minimum acceptable = 2
    range_match = re.search(r"bac\s*\+?\s*(\d)\s*(?:a|à|-)\s*bac\s*\+?\s*(\d)", normalized_offer)
    if range_match:
        return min(int(range_match.group(1)), int(range_match.group(2)))
    for level, keywords in _DEGREE_LEVELS:
        if any(kw in normalized_offer for kw in keywords):
            return level
    return None


def extract_implicit_requirements(job_offer: str, cv_master: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Génère des exigences implicites scorées : années d'expérience et niveau d'études,
    comparées au profil réel du candidat. Honnête : statut basé sur des faits calculés.
    """
    normalized = normalize_text(job_offer)
    out: List[Dict[str, Any]] = []

    # ── Années d'expérience ──
    required_years = _required_years_from_offer(normalized)
    if required_years:
        actual = candidate_total_years(cv_master)
        if actual >= required_years:
            status, usage = "CONFIRMED", "USE"
            expl = f"Le candidat totalise {actual:g} ans d'expérience (≥ {required_years} requis)."
        elif actual >= required_years - 1:
            status, usage = "TRANSFERABLE", "USE_CAREFULLY"
            expl = f"Le candidat totalise {actual:g} ans (proche des {required_years} requis)."
        else:
            status, usage = "WEAK", "DO_NOT_CLAIM"
            expl = f"Le candidat totalise {actual:g} ans (< {required_years} requis)."
        out.append({
            "requirement": f"Expérience {required_years}+ ans",
            "category": "seniority",
            "status": status,
            "evidence_ids": [],
            "explanation": expl,
            "cv_usage": usage,
        })

    # ── Niveau d'études ──
    required_edu = _required_education_from_offer(normalized)
    if required_edu:
        actual_edu = candidate_max_education(cv_master)
        if actual_edu and actual_edu >= required_edu:
            status, usage = "CONFIRMED", "USE"
            expl = f"Diplôme Bac+{actual_edu} (≥ Bac+{required_edu} requis)."
        elif actual_edu and actual_edu >= required_edu - 1:
            status, usage = "TRANSFERABLE", "USE_CAREFULLY"
            expl = f"Diplôme Bac+{actual_edu} (proche du Bac+{required_edu} requis)."
        else:
            status, usage = "WEAK", "DO_NOT_CLAIM"
            expl = f"Niveau d'études en deçà du Bac+{required_edu} requis." if actual_edu else "Niveau d'études non déterminé."
        out.append({
            "requirement": f"Formation Bac+{required_edu}",
            "category": "education",
            "status": status,
            "evidence_ids": [],
            "explanation": expl,
            "cv_usage": usage,
        })

    return out


def enrich_matching_with_implicit_requirements(
    matching: Dict[str, Any],
    job_offer: str,
    cv_master: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Ajoute les exigences implicites (années, études) à l'analyse, sans doublon."""
    reqs = matching.setdefault("requirements_analysis", [])
    existing = {_requirement_key(str(r.get("requirement", ""))) for r in reqs}
    for implicit in extract_implicit_requirements(job_offer, cv_master):
        key = _requirement_key(implicit["requirement"])
        if key and key not in existing:
            reqs.append(implicit)
            existing.add(key)
    return matching


def extract_offer_sector(job_offer: str) -> str:
    """
    Extrait le secteur/domaine métier de l'offre pour contextualiser
    les bullets TRANSFERABLE (ex: 'IoT industriel', 'secteur bancaire', 'ERP').
    Retourne une chaîne courte ou "".
    """
    text = job_offer or ""
    normalized = normalize_text(text)

    # 1) Pattern explicite "secteur de ... / dans le domaine de ..."
    patterns = [
        r"secteur\s+(?:de\s+(?:la\s+|l')?|du\s+|d')?([^.\n(]{4,80})",
        r"domaine\s+(?:de\s+(?:la\s+|l')?|du\s+|d')?([^.\n(]{4,80})",
        r"(?:dans|pour)\s+(?:le|la|l')\s+(?:secteur|domaine|industrie)\s+(?:de\s+)?([^.\n(]{4,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            sector = _clean_requirement(match.group(1))
            # On coupe à la première parenthèse ou énumération longue
            sector = re.split(r"\s*[(,;]\s*", sector)[0].strip()
            if 3 <= len(sector) <= 70:
                return sector

    # 2) Mots-clés de domaine métier courants
    domain_keywords = {
        "iot industriel":        ["iot", "objets connectes", "capteurs", "embarque industriel"],
        "système d'information":  ["systeme d'information", "exploitation du si", "support applicatif"],
        "ERP":                   ["erp", "peoplesoft", "sap", "progiciel de gestion"],
        "data / IA":             ["data science", "machine learning", "intelligence artificielle", "data engineering"],
        "cybersécurité":         ["cybersecurite", "securite informatique", "soc", "pentest"],
        "fintech / bancaire":    ["banque", "bancaire", "finance", "fintech", "assurance"],
        "santé / médical":       ["sante", "medical", "hospitalier", "e-sante"],
        "e-commerce / web":      ["e-commerce", "marketplace", "site web", "plateforme web"],
        "industrie / production":["production industrielle", "usine", "manufacturing", "genie civil", "btp", "construction"],
        "cloud / DevOps":        ["cloud", "devops", "infrastructure", "kubernetes"],
    }
    for label, keywords in domain_keywords.items():
        if any(kw in normalized for kw in keywords):
            return label

    return ""


def enrich_matching_with_offer_context(matching: Dict[str, Any], job_offer: str) -> Dict[str, Any]:
    matching["offer_title"] = extract_offer_title(job_offer)
    matching["safe_recommended_title"] = build_dynamic_title(matching, job_offer)
    matching["safe_context_terms"] = extract_safe_context_terms(job_offer, matching)
    matching["offer_sector"] = extract_offer_sector(job_offer)
    return matching


# ── Extraction et validation des exigences ────────────────────────────────────

def _requirement_key(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def _add_requirement(requirements: List[str], seen: Set[str], value: str) -> None:
    value = _clean_requirement(value)
    if not is_valid_requirement(value) or len(value) > 80:
        return
    normalized = normalize_text(value)
    if normalized in GENERIC_STOPWORDS or normalized in LOCATION_NOISE_TERMS:
        return
    key = _requirement_key(value)
    if key and key not in seen:
        seen.add(key)
        requirements.append(value)


def compact_requirements(requirements: List[str], max_items: int) -> List[str]:
    cleaned: List[str] = []
    for req in requirements:
        normalized_req = normalize_text(req)
        if any(
            normalized_req != normalize_text(other)
            and re.search(r"\b" + re.escape(normalized_req) + r"\b", normalize_text(other))
            and len(other.split()) <= 5
            for other in requirements
        ):
            continue
        if req not in cleaned:
            cleaned.append(req)
    return cleaned[:max_items]


def extract_requirements_from_offer(job_offer: str, max_items: int = 12) -> List[str]:
    requirements: List[str] = []
    seen: Set[str] = set()

    for raw_line in job_offer.splitlines():
        line = _clean_requirement(raw_line)
        if not line:
            continue
        bullet_match = re.match(r"^(?:[*\-•]|\d+[.)])\s*(.+)$", raw_line.strip())
        if bullet_match and len(line) <= 140:
            candidate = _clean_requirement(bullet_match.group(1))
            if 3 <= len(candidate) <= 60 and len(candidate.split()) <= 6:
                _add_requirement(requirements, seen, candidate)
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+#./-]{1,20}\b", line):
            if token.lower() == token and len(token) < 5:
                continue
            if normalize_text(token) in GENERIC_STOPWORDS:
                continue
            if any(char.isupper() for char in token) or any(char in token for char in "+#./-"):
                _add_requirement(requirements, seen, token)
        for phrase in re.findall(r"\b[A-Z][A-Za-z0-9+#/-]+(?:\s+[A-Z][A-Za-z0-9+#/-]+){1,3}\b", line):
            _add_requirement(requirements, seen, phrase)
        for phrase in re.findall(
            r"\b(?:developpement|maintenance|support|documentation|analyse|gestion|optimisation|integration|tests?)\s+[\w'/-]+(?:\s+[\w'/-]+)?",
            normalize_text(line),
        ):
            _add_requirement(requirements, seen, phrase)
        if len(requirements) >= max_items * 2:
            break

    for hint in GENERIC_REQUIREMENT_HINTS:
        if _contains_phrase(job_offer, [hint]):
            _add_requirement(requirements, seen, hint)

    return compact_requirements(requirements, max_items)


def is_transferable_requirement(requirement: str) -> bool:
    if re.search(r"[A-Z]{2,}|[+#/]", requirement):
        return False
    words = requirement.split()
    if any(word[:1].isupper() for word in words[1:]):
        return False
    return _contains_phrase(
        requirement,
        ["support", "documentation", "analyse", "maintenance", "tests", "recette", "gestion", "developpement"],
    )


def split_requirement_parts(requirement: str) -> List[str]:
    parts = re.split(r"\s*(?:/|,|;|\bou\b|\bor\b)\s*", requirement)
    return [_clean_requirement(part) for part in parts if _clean_requirement(part)]


def is_valid_requirement(requirement: str) -> bool:
    cleaned = _clean_requirement(requirement)
    normalized = normalize_text(cleaned)
    if len(cleaned) < 3:
        return False
    if normalized in GENERIC_STOPWORDS or normalized in INVALID_REQUIREMENT_PHRASES:
        return False
    if normalized in LOCATION_NOISE_TERMS:
        return False
    # Nombres seuls ou codes postaux
    if re.fullmatch(r"\d{1,2}(?:er|e|eme|ème)?", normalized) or re.fullmatch(r"\d{5}", normalized):
        return False
    if cleaned.endswith("-") or normalized in {"technico", "fonctionnelles"}:
        return False
    if "score de matching" in normalized:
        return False
    if normalized.endswith(" avec"):
        return False
    if len(cleaned.split()) == 1 and normalized in {
        "recueillir", "proposer", "etudier", "creer", "modifier", "participer", "collaborer",
    }:
        return False
    # Conditions contractuelles : durée hebdomadaire, type de contrat, rémunération, etc.
    words = set(normalized.split())
    if words & CONTRACTUAL_NOISE_TERMS:
        return False
    # Pattern "35 heures", "35h", "39h/semaine"...
    if re.search(r"\d+\s*h(?:eures?)?(?:\s*/\s*semaine)?", normalized):
        return False
    return True


def infer_recommended_title(job_offer: str, evidence_bank: List[Dict[str, Any]]) -> str:
    title_patterns = [
        r"(?:poste|profil|candidature)\s+(?:de|d'|pour)\s+([^.\n]{4,70})",
        r"nous recherchons\s+(?:un|une)\s+([^.\n]{4,70})",
        r"(?:developpeur|ingenieur|consultant|technicien|analyste|chef de projet|data analyst|data engineer)[^.\n]{0,50}",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, normalize_text(job_offer), flags=re.IGNORECASE)
        if match:
            candidate = _clean_requirement(match.group(1) if match.groups() else match.group(0))
            if candidate:
                return candidate.capitalize()
    # Cherche uniquement les champs qui contiennent un vrai titre court,
    # pas le résumé professionnel qui peut être un long paragraphe.
    for ev in evidence_bank:
        if (
            ev.get("category") == "identity"
            and ev.get("field") in {"titre", "current_title", "titre_cible_principal"}
            and ev.get("text")
        ):
            text = ev["text"].strip()
            if text and len(text.split()) <= 12:
                return text
    return "CV cible"


# ── Expansion sémantique : vocabulaire offre → vocabulaire CV ────────────────
# Clé = terme normalisé d'une offre d'emploi
# Valeur = termes alternatifs susceptibles d'apparaître dans le CV du candidat
REQUIREMENT_EXPANSIONS: Dict[str, List[str]] = {
    # CI/CD & DevOps outils
    "jenkins":              ["CI/CD", "pipeline", "automatisation", "déploiement", "DevOps"],
    "gitlab ci":            ["CI/CD", "Git", "pipeline", "DevOps", "intégration continue"],
    "github actions":       ["CI/CD", "Git", "pipeline", "automatisation", "DevOps"],
    "ansible":              ["automatisation", "infrastructure", "déploiement", "configuration", "DevOps"],
    "terraform":            ["infrastructure", "cloud", "déploiement", "DevOps", "automatisation"],
    "kubernetes":           ["Docker", "orchestration", "cloud", "conteneur", "DevOps"],
    "docker":               ["conteneur", "Linux", "infrastructure", "DevOps", "déploiement"],
    "nexus":                ["artifacts", "CI/CD", "DevOps", "dépendances"],
    "xldeploy":             ["déploiement", "CI/CD", "automatisation", "DevOps"],
    "helm":                 ["Kubernetes", "DevOps", "déploiement", "cloud"],
    # Domaines DevOps génériques
    "devops":               ["CI/CD", "Jenkins", "Docker", "Git", "Linux", "automatisation", "déploiement"],
    "ci/cd":                ["Jenkins", "pipeline", "automatisation", "déploiement", "intégration continue"],
    "cicd":                 ["Jenkins", "pipeline", "automatisation", "déploiement"],
    "automatisation":       ["script", "Python", "Bash", "CI/CD", "pipeline"],
    "infrastructure":       ["Linux", "Docker", "cloud", "DevOps", "serveur", "déploiement"],
    # Python ecosystem
    "flask":                ["Python", "API", "REST", "backend", "web", "serveur"],
    "django":               ["Python", "API", "REST", "backend", "web", "ORM"],
    "fastapi":              ["Python", "API", "REST", "backend", "asynchrone"],
    "celery":               ["Python", "tâches asynchrones", "pipeline", "backend"],
    "sqlalchemy":           ["Python", "ORM", "base de données", "SQL"],
    "pandas":               ["Python", "données", "data", "analyse", "traitement"],
    "numpy":                ["Python", "calcul", "données", "scientifique"],
    "opencv":               ["Python", "traitement d'images", "vision", "C++"],
    "scikit-learn":         ["Machine Learning", "Python", "données", "modèle"],
    "pytorch":              ["Deep Learning", "IA", "Python", "réseau de neurones"],
    "tensorflow":           ["Deep Learning", "IA", "Python", "réseau de neurones"],
    "pytest":               ["Python", "tests", "qualité", "TDD"],
    "pydantic":             ["Python", "validation", "API", "backend"],
    # JavaScript ecosystem
    "react":                ["JavaScript", "TypeScript", "frontend", "interface", "web", "composants"],
    "react.js":             ["JavaScript", "TypeScript", "frontend", "interface", "web"],
    "vue":                  ["JavaScript", "TypeScript", "frontend", "interface", "web"],
    "angular":              ["JavaScript", "TypeScript", "frontend", "interface", "web"],
    "node.js":              ["JavaScript", "backend", "API", "web", "serveur"],
    "nodejs":               ["JavaScript", "backend", "API", "web"],
    "express":              ["JavaScript", "Node.js", "backend", "API", "REST"],
    "typescript":           ["JavaScript", "frontend", "typage", "interface"],
    "next.js":              ["React", "JavaScript", "frontend", "web", "SSR"],
    # Java ecosystem
    "spring":               ["Java", "backend", "API", "REST", "microservices"],
    "hibernate":            ["Java", "ORM", "base de données", "SQL"],
    "maven":                ["Java", "build", "dépendances", "CI/CD"],
    # Bases de données
    "postgresql":           ["SQL", "base de données", "requête", "schéma"],
    "mysql":                ["SQL", "base de données", "requête"],
    "oracle":               ["SQL", "PL/SQL", "base de données", "requête"],
    "mongodb":              ["NoSQL", "base de données", "document", "JavaScript"],
    "redis":                ["cache", "NoSQL", "base de données", "performance"],
    "elasticsearch":        ["recherche", "indexation", "logs", "NoSQL"],
    "influxdb":             ["time-series", "monitoring", "IoT", "métriques"],
    "sql":                  ["base de données", "requête", "PostgreSQL", "MySQL", "Oracle"],
    "nosql":                ["MongoDB", "Redis", "Elasticsearch", "base de données"],
    "pl/sql":               ["SQL", "Oracle", "procédure stockée", "base de données"],
    "plsql":                ["SQL", "Oracle", "procédure stockée", "base de données"],
    # Cloud
    "aws":                  ["cloud", "infrastructure", "S3", "EC2", "déploiement"],
    "azure":                ["cloud", "infrastructure", "Microsoft", "déploiement"],
    "gcp":                  ["cloud", "infrastructure", "Google", "déploiement"],
    "cloud":                ["AWS", "Azure", "GCP", "infrastructure", "déploiement", "serveur"],
    # ERP & CRM
    "sap":                  ["ERP", "gestion", "système d'information"],
    "peoplesoft":           ["ERP", "gestion", "système d'information"],
    "salesforce":           ["CRM", "gestion client"],
    "odoo":                 ["ERP", "gestion", "Python", "système d'information"],
    "erp":                  ["SAP", "gestion", "système d'information"],
    "crm":                  ["Salesforce", "gestion client"],
    # ERP-specific tools
    "peoplecode":           ["ERP", "développement", "PeopleSoft"],
    "application engine":   ["ERP", "batch", "PeopleSoft", "traitement"],
    "integration broker":   ["ERP", "intégration", "API", "échanges", "PeopleSoft"],
    "sqr":                  ["ERP", "reporting", "PeopleSoft", "SQL"],
    "component interface":  ["ERP", "intégration", "PeopleSoft", "composant"],
    # IoT & embarqué
    "iot":                  ["embarqué", "capteurs", "acquisition", "temps réel", "industriel"],
    "embarque":             ["IoT", "capteurs", "acquisition", "temps réel", "Arduino"],
    "arduino":              ["embarqué", "IoT", "capteurs", "C++", "temps réel"],
    "raspberry":            ["embarqué", "Linux", "IoT", "Python"],
    "mqtt":                 ["IoT", "protocole", "embarqué", "messagerie", "capteurs"],
    # Data & IA
    "machine learning":     ["IA", "modèle", "données", "Python", "scikit", "apprentissage"],
    "deep learning":        ["réseau de neurones", "IA", "PyTorch", "TensorFlow"],
    "data engineering":     ["pipeline", "ETL", "données", "Python", "SQL", "Spark"],
    "mlops":                ["DevOps", "Machine Learning", "pipeline", "déploiement", "modèle"],
    "spark":                ["big data", "données", "Python", "Java", "traitement distribué"],
    "airflow":              ["pipeline", "orchestration", "Python", "ETL", "données"],
    # Langages
    "perl":                 ["script", "automatisation", "Linux", "traitement texte"],
    "php":                  ["web", "backend", "API", "serveur"],
    "c#":                   [".NET", "Microsoft", "backend", "API"],
    ".net":                 ["C#", "Microsoft", "backend", "API"],
    "golang":               ["Go", "backend", "microservices", "API"],
    "bash":                 ["Linux", "shell", "script", "automatisation"],
    "shell":                ["Linux", "Bash", "script", "automatisation"],
    "powershell":           ["Windows", "script", "automatisation", "administration"],
    # Monitoring & observabilité
    "prometheus":           ["monitoring", "métriques", "observabilité", "Grafana"],
    "grafana":              ["monitoring", "métriques", "observabilité", "visualisation"],
    "elk":                  ["logs", "Elasticsearch", "monitoring", "analyse"],
    "datadog":              ["monitoring", "observabilité", "APM", "métriques"],
    # Tests
    "selenium":             ["tests", "automatisation", "frontend", "qualité", "navigateur"],
    "cypress":              ["tests", "frontend", "JavaScript", "qualité"],
    "junit":                ["tests", "Java", "qualité", "TDD"],
    "sonarqube":            ["qualité", "code", "analyse statique", "CI/CD"],
    # Architecture & protocoles
    "microservices":        ["API", "REST", "Docker", "Kubernetes", "architecture"],
    "soap":                 ["XML", "web service", "intégration", "API"],
    "graphql":              ["API", "JavaScript", "React", "backend"],
    "kafka":                ["messagerie", "streaming", "pipeline", "données", "microservices"],
    "rabbitmq":             ["messagerie", "file", "microservices", "asynchrone"],
    # Support & exploitation
    "support applicatif":   ["analyse d'incidents", "diagnostic", "résolution", "support"],
    "support technique":    ["analyse d'incidents", "diagnostic", "résolution", "support"],
    "analyse incidents":    ["support", "diagnostic", "logs", "résolution"],
    "production informatique": ["support", "exploitation", "monitoring", "infrastructure"],
    # Collaboration & Agile
    "jira":                 ["gestion de projet", "Agile", "Scrum", "tickets"],
    "confluence":           ["documentation", "wiki", "collaboration", "Agile"],
    "scrum":                ["Agile", "sprint", "gestion de projet", "ceremonies"],
}


def _expand_requirement(normalized_requirement: str) -> List[str]:
    """Retourne les termes d'expansion pour un requirement normalisé."""
    extra: List[str] = []
    seen: Set[str] = {normalized_requirement}
    for key, expansions in REQUIREMENT_EXPANSIONS.items():
        norm_key = normalize_text(key)
        # Clé multi-mots : correspondance exacte uniquement
        # Clé mono-mot : correspondance si contenu dans le requirement (length >= 3)
        if " " in norm_key:
            is_match = norm_key == normalized_requirement
        else:
            is_match = norm_key == normalized_requirement or (
                len(norm_key) >= 3 and norm_key in normalized_requirement
            )
        if is_match:
            for term in expansions:
                norm_term = normalize_text(term)
                if norm_term not in seen:
                    seen.add(norm_term)
                    extra.append(term)
    return extra


def classify_requirement(requirement: str, evidence_bank: List[Dict[str, Any]]) -> Dict[str, Any]:
    parts = split_requirement_parts(requirement)
    requirement_aliases = [requirement]
    normalized_requirement = normalize_text(requirement)
    alias_map = {
        "react.js": "React", "react js": "React", "reactjs": "React",
        "front end": "frontend", "front-end": "frontend",
        "node js": "Node.js", "pl sql": "PL/SQL",
    }
    if normalized_requirement in alias_map:
        requirement_aliases.append(alias_map[normalized_requirement])

    direct_matches = [
        ev["id"] for ev in evidence_bank
        if _contains_phrase(ev.get("text", ""), requirement_aliases)
    ][:3]

    partial_matches: List[str] = []
    if not direct_matches and len(parts) > 1:
        for part in parts:
            partial_matches.extend(
                ev["id"] for ev in evidence_bank
                if _contains_phrase(ev.get("text", ""), [part])
            )
        partial_matches = list(dict.fromkeys(partial_matches))[:3]

    status = "ABSENT"
    cv_usage = "DO_NOT_CLAIM"
    explanation = "Aucune preuve directe dans le CV."
    evidence_ids = direct_matches

    if evidence_ids:
        status = "CONFIRMED"
        cv_usage = "USE"
        explanation = "Preuve directe presente dans le CV."
    elif partial_matches:
        status = "TRANSFERABLE"
        cv_usage = "USE_CAREFULLY"
        explanation = "Preuve partielle presente dans le CV."
        evidence_ids = partial_matches

    if status == "ABSENT":
        semantic_match = find_best_semantic_evidence(requirement, evidence_bank)
        if semantic_match:
            status = semantic_match["status"]
            cv_usage = "USE_CAREFULLY"
            explanation = (
                f"Lien semantique {semantic_match['relation']} avec {semantic_match['matched_node']} "
                "prouve dans le CV ; a formuler sans revendiquer la competence demandee."
            )
            evidence_ids = semantic_match["evidence_ids"]

    # Expansion : cherche les termes du domaine associé si toujours ABSENT
    if status == "ABSENT":
        expansion_terms = _expand_requirement(normalized_requirement)
        if expansion_terms:
            expansion_matches = [
                ev["id"] for ev in evidence_bank
                if _contains_phrase(ev.get("text", ""), expansion_terms)
            ][:3]
            if expansion_matches:
                status = "TRANSFERABLE"
                cv_usage = "USE_CAREFULLY"
                explanation = "Compétence du même domaine détectée dans le CV (correspondance par expansion sémantique)."
                evidence_ids = expansion_matches

    if status == "ABSENT" and is_transferable_requirement(requirement):
        evidence_ids = [
            ev["id"] for ev in evidence_bank
            if ev.get("category") in {"experience", "experience_mission", "experience_achievement", "skill"}
            and _contains_phrase(
                ev.get("text", ""),
                ["support", "connectivite", "donnees", "developper", "validation", "documentation"],
            )
        ][:3]
        if evidence_ids:
            status = "TRANSFERABLE"
            cv_usage = "USE_CAREFULLY"
            explanation = "Experience proche mais pas une preuve directe."

    return {
        "requirement": requirement,
        "category": "skill",
        "status": status,
        "evidence_ids": evidence_ids,
        "explanation": explanation,
        "cv_usage": cv_usage,
    }


# ── Groupement de preuves par exigence (Chemin B : LLM arbitre) ──────────────

def find_candidate_evidence_for_requirement(
    requirement: str,
    evidence_bank: List[Dict[str, Any]],
    top_n: int = 12,
) -> Dict[str, List[str]]:
    """
    Retourne les preuves candidates pour une exigence, groupées par proximité.
    Prépare le contexte pour un LLM-arbitre (il juge, il ne cherche pas).
    """
    parts = split_requirement_parts(requirement)
    requirement_aliases = [requirement]
    normalized_requirement = normalize_text(requirement)
    alias_map = {
        "react.js": "React", "react js": "React", "reactjs": "React",
        "front end": "frontend", "front-end": "frontend",
        "node js": "Node.js", "pl sql": "PL/SQL",
    }
    if normalized_requirement in alias_map:
        requirement_aliases.append(alias_map[normalized_requirement])

    per_bucket = max(3, top_n // 3)

    direct = [
        ev["id"] for ev in evidence_bank
        if _contains_phrase(ev.get("text", ""), requirement_aliases)
    ][:per_bucket]
    seen: Set[str] = set(direct)

    near: List[str] = []
    if len(parts) > 1:
        for part in parts:
            for ev in evidence_bank:
                if ev["id"] not in seen and _contains_phrase(ev.get("text", ""), [part]):
                    near.append(ev["id"])
                    seen.add(ev["id"])
        near = near[:per_bucket]

    if not direct and not near:
        semantic = find_best_semantic_evidence(requirement, evidence_bank)
        if semantic:
            for eid in semantic["evidence_ids"][:per_bucket]:
                if eid not in seen:
                    near.append(eid)
                    seen.add(eid)

    expansion_terms = _expand_requirement(normalized_requirement)
    context: List[str] = []
    if expansion_terms:
        for ev in evidence_bank:
            if ev["id"] not in seen and _contains_phrase(ev.get("text", ""), expansion_terms):
                context.append(ev["id"])
                seen.add(ev["id"])
                if len(context) >= per_bucket:
                    break

    # Filet pour exigences génériques (support, docs...) sans preuve directe
    if not direct and not near and not context and is_transferable_requirement(requirement):
        for ev in evidence_bank:
            if ev["id"] not in seen and ev.get("category") in {
                "experience", "experience_mission", "experience_achievement", "skill",
            } and _contains_phrase(
                ev.get("text", ""),
                ["support", "connectivite", "donnees", "developper", "validation", "documentation"],
            ):
                context.append(ev["id"])
                seen.add(ev["id"])
                if len(context) >= 3:
                    break

    return {"direct": direct, "near": near, "context": context}


def build_requirement_groups(
    job_offer: str,
    evidence_bank: List[Dict[str, Any]],
    max_requirements: int = 14,
    top_n: int = 12,
) -> Dict[str, Dict[str, List[str]]]:
    """
    Extrait les exigences de l'offre et groupe les preuves candidates par exigence.
    Entrée du prompt LLM-arbitre (Chemin B).
    """
    requirements = extract_requirements_from_offer(job_offer, max_items=max_requirements)
    return {
        req: find_candidate_evidence_for_requirement(req, evidence_bank, top_n=top_n)
        for req in requirements
    }


# ── Pipeline de matching ──────────────────────────────────────────────────────

def build_fallback_matching(job_offer: str, evidence_bank: List[Dict[str, Any]]) -> Dict[str, Any]:
    requirements = []
    confirmed_ids: Set[str] = set()
    transferable_ids: Set[str] = set()
    weak_or_missing = []
    forbidden_claims = []

    for requirement in extract_requirements_from_offer(job_offer):
        req = classify_requirement(requirement, evidence_bank)
        status = req["status"]
        if status == "CONFIRMED":
            confirmed_ids.update(req["evidence_ids"])
        elif status == "TRANSFERABLE":
            transferable_ids.update(req["evidence_ids"])
        if status in {"WEAK", "ABSENT"}:
            weak_or_missing.append(requirement)
            forbidden_claims.append(requirement)
        requirements.append(req)
        if len(requirements) >= 12:
            break

    return {
        "recommended_title": infer_recommended_title(job_offer, evidence_bank),
        "matching_score": 0,
        "job_keywords": [req["requirement"] for req in requirements[:15]],
        "requirements_analysis": requirements,
        "confirmed_skill_evidence_ids": sorted(confirmed_ids),
        "transferable_skill_evidence_ids": sorted(transferable_ids),
        "weak_or_missing_requirements": weak_or_missing,
        "forbidden_claims": forbidden_claims,
        "strategy": "Valoriser les preuves directes et presenter le reste comme axe d'apprentissage.",
    }


def enrich_matching_with_extracted_requirements(
    matching: Dict[str, Any],
    job_offer: str,
    evidence_bank: List[Dict[str, Any]],
    max_items: int = 16,
) -> Dict[str, Any]:
    requirements = matching.setdefault("requirements_analysis", [])
    existing = {
        _requirement_key(str(req.get("requirement", "")))
        for req in requirements if req.get("requirement")
    }
    confirmed_ids = set(matching.get("confirmed_skill_evidence_ids", []))
    transferable_ids = set(matching.get("transferable_skill_evidence_ids", []))

    for requirement in extract_requirements_from_offer(job_offer, max_items=max_items):
        key = _requirement_key(requirement)
        if not key or key in existing:
            continue
        req = classify_requirement(requirement, evidence_bank)
        requirements.append(req)
        existing.add(key)
        if req["status"] == "CONFIRMED":
            confirmed_ids.update(req["evidence_ids"])
        elif req["status"] == "TRANSFERABLE":
            transferable_ids.update(req["evidence_ids"])
        if len(requirements) >= max_items:
            break

    matching["confirmed_skill_evidence_ids"] = sorted(confirmed_ids)
    matching["transferable_skill_evidence_ids"] = sorted(transferable_ids)
    matching["job_keywords"] = [req.get("requirement", "") for req in requirements[:15]]
    return matching


def normalize_matching_requirements(
    matching: Dict[str, Any],
    evidence_bank: List[Dict[str, Any]],
    trust_llm_evidence: bool = False,
) -> Dict[str, Any]:
    """
    trust_llm_evidence=True (Chemin B) : conserve les décisions du LLM quand les IDs
    sont valides. Reclassifie uniquement si le statut ou les IDs sont incohérents.
    trust_llm_evidence=False (défaut) : reclassifie tout via Python (comportement original).
    """
    valid_ids = {ev["id"] for ev in evidence_bank}
    normalized_requirements = []
    seen: Set[str] = set()
    confirmed_ids: Set[str] = set()
    transferable_ids: Set[str] = set()

    for req in matching.get("requirements_analysis", []):
        requirement = _clean_requirement(str(req.get("requirement", "")))
        if not is_valid_requirement(requirement):
            continue
        key = _requirement_key(requirement)
        if not key or key in seen:
            continue
        seen.add(key)

        if trust_llm_evidence:
            llm_status = req.get("status", "ABSENT")
            llm_ids = [eid for eid in (req.get("evidence_ids") or []) if eid in valid_ids]
            llm_cv_usage = req.get("cv_usage", "DO_NOT_CLAIM")
            if llm_status not in {"CONFIRMED", "TRANSFERABLE", "WEAK", "ABSENT"}:
                classified = classify_requirement(requirement, evidence_bank)
            elif llm_status in {"CONFIRMED", "TRANSFERABLE"} and not llm_ids:
                # LLM a dit CONFIRMED/TRANSFERABLE mais sans preuve valide → reclassifie
                classified = classify_requirement(requirement, evidence_bank)
            else:
                classified = {
                    "requirement": requirement,
                    "category": req.get("category", "skill"),
                    "status": llm_status,
                    "evidence_ids": llm_ids,
                    "explanation": req.get("explanation", ""),
                    "cv_usage": llm_cv_usage,
                }
        else:
            classified = classify_requirement(requirement, evidence_bank)

        normalized_requirements.append(classified)
        if classified["status"] == "CONFIRMED":
            confirmed_ids.update(classified["evidence_ids"])
        elif classified["status"] == "TRANSFERABLE":
            transferable_ids.update(classified["evidence_ids"])

    matching["requirements_analysis"] = normalized_requirements[:20]
    matching["confirmed_skill_evidence_ids"] = sorted(confirmed_ids)
    matching["transferable_skill_evidence_ids"] = sorted(transferable_ids)
    matching["job_keywords"] = [req["requirement"] for req in normalized_requirements[:15]]
    return matching


def adjust_for_training_context(matching: Dict[str, Any], job_offer: str) -> Dict[str, Any]:
    normalized_offer = normalize_text(job_offer)
    training_context = any(
        phrase in normalized_offer
        for phrase in [
            "sera forme", "formation interne", "ne possedant pas necessairement",
            "pas necessairement d'experience", "souhaitant evoluer",
            "profil junior", "developpeur junior",
        ]
    )
    matching["training_context"] = training_context
    if not training_context:
        return matching
    for req in matching.get("requirements_analysis", []):
        requirement = str(req.get("requirement", ""))
        if req.get("status") != "ABSENT":
            continue
        if (
            re.search(r"[A-Z]{2,}|[+#/]", requirement)
            or re.search(r"[a-z][A-Z]", requirement)
            or any(word[:1].isupper() for word in requirement.split()[1:])
        ):
            req["status"] = "WEAK"
            req["cv_usage"] = "DO_NOT_CLAIM"
            req["explanation"] = "Non prouve dans le CV, mais l'offre junior/formante permet une montee en competence."
    return matching


def apply_cross_requirement_reasoning(matching: Dict[str, Any]) -> Dict[str, Any]:
    """
    Raisonnement inter-exigences : une exigence ABSENT/WEAK dont la famille
    technologique contient une exigence CONFIRMED devient TRANSFERABLE.
    Ex : Python CONFIRMED → FastAPI ABSENT devient TRANSFERABLE (framework Python),
    en héritant des preuves du parent confirmé (transfert honnête, pas d'invention).
    """
    reqs = matching.get("requirements_analysis", [])
    # Map terme normalisé d'une exigence CONFIRMED → l'exigence elle-même
    confirmed = {
        normalize_text(r.get("requirement", "")): r
        for r in reqs if r.get("status") == "CONFIRMED" and r.get("requirement")
    }
    if not confirmed:
        return matching

    transferable_ids = set(matching.get("transferable_skill_evidence_ids", []))
    for req in reqs:
        if req.get("status") not in {"ABSENT", "WEAK"}:
            continue
        norm = normalize_text(req.get("requirement", ""))
        expansion_terms = [normalize_text(t) for t in _expand_requirement(norm)]
        # Cherche un parent confirmé dans la famille technologique
        sibling = next((confirmed[t] for t in expansion_terms if t in confirmed), None)
        if not sibling:
            continue
        sibling_name = sibling.get("requirement", "")
        sibling_ids = list(sibling.get("evidence_ids", []))[:3]
        req["status"] = "TRANSFERABLE"
        req["cv_usage"] = "USE_CAREFULLY"
        req["evidence_ids"] = sibling_ids
        req["explanation"] = (
            f"Même famille technologique que {sibling_name} (confirmé) : "
            "montée en compétence rapide attendue, à formuler comme transférable."
        )
        transferable_ids.update(sibling_ids)

    matching["transferable_skill_evidence_ids"] = sorted(transferable_ids)
    return matching


def complete_matching_safety_fields(matching: Dict[str, Any]) -> Dict[str, Any]:
    forbidden: Set[str] = set()
    weak_or_missing: Set[str] = set()
    for req in matching.get("requirements_analysis", []):
        if req.get("status") in {"WEAK", "ABSENT"}:
            requirement = req.get("requirement")
            if requirement:
                forbidden.add(requirement)
                weak_or_missing.add(requirement)
    matching["forbidden_claims"] = sorted(forbidden)
    matching["weak_or_missing_requirements"] = sorted(weak_or_missing)
    return matching


def allowed_evidence_from_matching(matching: Dict[str, Any], evidence_bank: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    allowed_ids = set(matching.get("confirmed_skill_evidence_ids", [])) | set(matching.get("transferable_skill_evidence_ids", []))
    for req in matching.get("requirements_analysis", []):
        if req.get("status") in {"CONFIRMED", "TRANSFERABLE"}:
            allowed_ids.update(req.get("evidence_ids", []))
    return [ev for ev in evidence_bank if ev["id"] in allowed_ids]
