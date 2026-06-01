from __future__ import annotations

import json
import re
from typing import Any

from .ollama_client import call_ollama_json, OllamaError
from .grammar import correct_text

# ── Protected tech terms (never translated) ───────────────────────────────────
# Sorted longest-first so longer matches take priority over substrings.
PROTECTED_TERMS: list[str] = sorted([
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust",
    "C++", "C#", "PHP", "Ruby", "Swift", "Kotlin", "Scala",
    "MATLAB", "Bash", "Shell", "SQL", "HTML", "CSS", "SASS", "SCSS",
    # Web frameworks
    "FastAPI", "Django", "Flask", "Starlette",
    "React", "Vue.js", "Vue", "Angular", "Svelte",
    "Next.js", "Nuxt.js", "Gatsby",
    "Spring Boot", "Spring", "Express.js", "Express",
    "NestJS", "Laravel", "Symfony", "Rails",
    "ASP.NET", "Blazor",
    # Mobile
    "Flutter", "React Native",
    # Data / AI / ML
    "TensorFlow", "PyTorch", "Keras",
    "scikit-learn", "Scikit-learn", "sklearn",
    "pandas", "Pandas", "NumPy", "numpy", "SciPy", "Matplotlib", "Seaborn",
    "Apache Spark", "PySpark", "Spark", "Hadoop", "Flink",
    "Apache Kafka", "Kafka",
    "Apache Airflow", "Airflow",
    "Prefect", "Dagster", "Celery",
    "MLflow", "DVC",
    "Weights & Biases", "W&B",
    "Hugging Face", "LangChain", "LlamaIndex",
    "OpenAI", "Anthropic",
    "BERT", "GPT", "LLM", "RAG", "ONNX",
    "XGBoost", "LightGBM", "CatBoost",
    "OpenCV", "Dask", "Ray",
    # Databases
    "PostgreSQL", "MySQL", "SQLite", "MariaDB", "Oracle",
    "MongoDB", "Redis", "Elasticsearch", "OpenSearch",
    "Cassandra", "DynamoDB", "Firestore", "Firebase",
    "Neo4j", "ArangoDB",
    "InfluxDB", "TimescaleDB",
    "Pinecone", "Weaviate", "Chroma", "Qdrant",
    # Cloud
    "Amazon Web Services", "AWS",
    "Microsoft Azure", "Azure",
    "Google Cloud Platform", "Google Cloud", "GCP",
    "Amazon S3", "S3", "EC2", "Lambda", "ECS", "EKS", "RDS", "SQS", "SNS",
    "Cloud Run", "Cloud Functions", "BigQuery",
    "Blob Storage", "Azure Functions", "AKS",
    # DevOps / infra
    "Docker", "Kubernetes", "Helm", "Istio",
    "Terraform", "Ansible", "Puppet", "Chef",
    "Jenkins", "GitLab CI/CD", "GitLab CI", "GitHub Actions", "CircleCI", "ArgoCD",
    "Prometheus", "Grafana", "Datadog", "Sentry",
    "ELK Stack", "ELK", "Kibana", "Logstash",
    "Nginx", "Apache", "Traefik", "HAProxy",
    # Version control / tools
    "Git", "GitHub", "GitLab", "Bitbucket",
    "Jira", "Confluence", "Notion", "Trello", "Linear", "Slack",
    "Figma", "Sketch",
    "Postman", "Swagger", "OpenAPI",
    "VS Code", "IntelliJ", "PyCharm", "WebStorm",
    "Raspberry Pi", "SIEMENS IOT2040",
    # CSS frameworks
    "Tailwind CSS", "Bootstrap", "Material UI", "Chakra UI",
    # Protocols / formats
    "REST", "GraphQL", "gRPC", "WebSocket", "WebRTC",
    "OAuth 2.0", "OAuth", "JWT", "SAML", "LDAP", "OIDC",
    "HTTP", "HTTPS", "TCP", "UDP", "MQTT", "AMQP",
    "RabbitMQ", "Apache ActiveMQ",
    "JSON", "YAML", "XML", "CSV", "Parquet", "Avro", "Protobuf",
    # OS
    "Linux", "Ubuntu", "Debian", "CentOS", "Alpine", "Windows", "macOS",
    # Build / test
    "Webpack", "Vite", "Rollup", "Babel", "ESLint", "Prettier",
    "Pytest", "Jest", "Mocha", "Cypress",
    "Gunicorn", "Uvicorn", "uWSGI",
    "RenderCV", "LaTeX",
    # Acronyms
    "API", "SDK", "CLI", "SaaS", "PaaS", "IaaS",
    "CI/CD", "ORM", "OOP", "MVC", "MVP", "DDD", "TDD", "BDD",
    "ETL", "ELT", "NLP", "ML", "AI", "IA",
    "IoT", "SCADA", "PLC", "VPN", "APN", "SIM",
    "TOEIC", "IELTS", "TOEFL",
], key=lambda x: -len(x))


# ── Section header translation map ────────────────────────────────────────────
_SECTION_EN_MD: dict[str, str] = {
    "resume professionnel":  "Professional Summary",
    "résumé professionnel":  "Professional Summary",
    "resumé professionnel":  "Professional Summary",
    "competences cles":      "Key Skills",
    "compétences clés":      "Key Skills",
    "competences clés":      "Key Skills",
    "experiences":           "Experience",
    "expériences":           "Experience",
    "projets":               "Projects",
    "formation":             "Education",
    "langues":               "Languages",
    "certifications":        "Certifications",
}

# ── Deterministic word-level pre-processing (applied before LLM) ──────────────
# Handles common FR words that LLMs sometimes miss at T°=0.
_FR_EN_WORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bEnvironnement\b"), "Environment"),
    (re.compile(r"\benvironnement\b"), "environment"),
    (re.compile(r"\bDéveloppement\b"), "Development"),
    (re.compile(r"\bdéveloppement\b"), "development"),
    (re.compile(r"\bDéveloppeur\b"), "Developer"),
    (re.compile(r"\bdéveloppeur\b"), "developer"),
    (re.compile(r"\bIngénieur\b"), "Engineer"),
    (re.compile(r"\bingénieur\b"), "engineer"),
    (re.compile(r"\bLogiciel\b"), "Software"),
    (re.compile(r"\blogiciel\b"), "software"),
    (re.compile(r"\bLogiciels\b"), "Software"),
    (re.compile(r"\blogiciels\b"), "software"),
    (re.compile(r"\bDonnées\b"), "Data"),
    (re.compile(r"\bdonnées\b"), "data"),
    (re.compile(r"\bRéseau\b"), "Network"),
    (re.compile(r"\bréseau\b"), "network"),
    (re.compile(r"\bRéseaux\b"), "Networks"),
    (re.compile(r"\bréseaux\b"), "networks"),
    (re.compile(r"\bAutomatisation\b"), "Automation"),
    (re.compile(r"\bautomatisation\b"), "automation"),
    (re.compile(r"\bMise à jour\b"), "Update"),
    (re.compile(r"\bmise à jour\b"), "update"),
    (re.compile(r"\bArchitecture logicielle\b"), "Software Architecture"),
    (re.compile(r"\barchitecture logicielle\b"), "software architecture"),
    (re.compile(r"\bMicro-services\b"), "Microservices"),
    (re.compile(r"\bmicro-services\b"), "microservices"),
    (re.compile(r"\bOutils de monitoring\b"), "Monitoring tools"),
    (re.compile(r"\boutils de monitoring\b"), "monitoring tools"),
    (re.compile(r"\bDocumentation technique\b"), "Technical documentation"),
    (re.compile(r"\bdocumentation technique\b"), "technical documentation"),
    (re.compile(r"\bModélisation de données\b"), "Data modeling"),
    (re.compile(r"\bmodélisation de données\b"), "data modeling"),
    (re.compile(r"\bCartes SIM IoT\b"), "IoT SIM cards"),
    (re.compile(r"\bcartes SIM IoT\b"), "IoT SIM cards"),
    (re.compile(r"\bMachines connectées\b"), "Connected machines"),
    (re.compile(r"\bmachines connectées\b"), "connected machines"),
    (re.compile(r"\bGestion de parc\b"), "Fleet management"),
    (re.compile(r"\bgestion de parc\b"), "fleet management"),
]

# ── Country name translations (applied to exp header location parts) ──────────
_FR_EN_COUNTRIES: dict[str, str] = {
    "États-Unis": "United States",
    "Etats-Unis": "United States",
    "Royaume-Uni": "United Kingdom",
    "Allemagne": "Germany",
    "Espagne": "Spain",
    "Italie": "Italy",
    "Pays-Bas": "Netherlands",
    "Suisse": "Switzerland",
    "Belgique": "Belgium",
    "Australie": "Australia",
    "Chine": "China",
    "Japon": "Japan",
    "Inde": "India",
    "Brésil": "Brazil",
    "Mexique": "Mexico",
    "Maroc": "Morocco",
    "Tunisie": "Tunisia",
    "Algérie": "Algeria",
    "Sénégal": "Senegal",
    "Côte d'Ivoire": "Ivory Coast",
    "Portugal": "Portugal",
    "Pologne": "Poland",
    "Suède": "Sweden",
    "Norvège": "Norway",
    "Danemark": "Denmark",
    "Finlande": "Finland",
    "Autriche": "Austria",
    "Grèce": "Greece",
    "Hongrie": "Hungary",
    "République tchèque": "Czech Republic",
    "Roumanie": "Romania",
    "Ukraine": "Ukraine",
    "Russie": "Russia",
    "Turquie": "Turkey",
    "Émirats arabes unis": "United Arab Emirates",
    "Arabie saoudite": "Saudi Arabia",
    "Nouvelle-Zélande": "New Zealand",
    "Afrique du Sud": "South Africa",
    "Corée du Sud": "South Korea",
    "Singapour": "Singapore",
    "Hong Kong": "Hong Kong",
}

# ── French month name translations ───────────────────────────────────────────
_FR_EN_MONTHS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bjanvier\b", re.IGNORECASE),    "January"),
    (re.compile(r"\bjanv\.\b", re.IGNORECASE),     "Jan."),
    (re.compile(r"\bjanv\b", re.IGNORECASE),       "Jan"),
    (re.compile(r"\bfévrier\b", re.IGNORECASE),    "February"),
    (re.compile(r"\bfévr\.\b", re.IGNORECASE),     "Feb."),
    (re.compile(r"\bfévr\b", re.IGNORECASE),       "Feb"),
    (re.compile(r"\bfevrier\b", re.IGNORECASE),    "February"),
    (re.compile(r"\bmars\b", re.IGNORECASE),       "March"),
    (re.compile(r"\bavril\b", re.IGNORECASE),      "April"),
    (re.compile(r"\bavr\.\b", re.IGNORECASE),      "Apr."),
    (re.compile(r"\bavr\b", re.IGNORECASE),        "Apr"),
    (re.compile(r"\bmai\b", re.IGNORECASE),        "May"),
    (re.compile(r"\bjuin\b", re.IGNORECASE),       "June"),
    (re.compile(r"\bjuillet\b", re.IGNORECASE),    "July"),
    (re.compile(r"\bjuil\.\b", re.IGNORECASE),     "Jul."),
    (re.compile(r"\bjuil\b", re.IGNORECASE),       "Jul"),
    (re.compile(r"\baoût\b", re.IGNORECASE),       "August"),
    (re.compile(r"\baout\b", re.IGNORECASE),       "August"),
    (re.compile(r"\bseptembre\b", re.IGNORECASE),  "September"),
    (re.compile(r"\bsept\.\b", re.IGNORECASE),     "Sep."),
    (re.compile(r"\bsept\b", re.IGNORECASE),       "Sep"),
    (re.compile(r"\boctobre\b", re.IGNORECASE),    "October"),
    (re.compile(r"\boct\.\b", re.IGNORECASE),      "Oct."),
    (re.compile(r"\boct\b", re.IGNORECASE),        "Oct"),
    (re.compile(r"\bnovembre\b", re.IGNORECASE),   "November"),
    (re.compile(r"\bnov\.\b", re.IGNORECASE),      "Nov."),
    (re.compile(r"\bnov\b", re.IGNORECASE),        "Nov"),
    (re.compile(r"\bdécembre\b", re.IGNORECASE),   "December"),
    (re.compile(r"\bdéc\.\b", re.IGNORECASE),      "Dec."),
    (re.compile(r"\bdéc\b", re.IGNORECASE),        "Dec"),
    (re.compile(r"\bdecembre\b", re.IGNORECASE),   "December"),
]

# ── Language name & level translations (for Languages section) ────────────────
_FR_EN_LANG_NAMES: dict[str, str] = {
    "Français": "French", "français": "French",
    "Anglais": "English", "anglais": "English",
    "Arabe": "Arabic", "arabe": "Arabic",
    "Espagnol": "Spanish", "espagnol": "Spanish",
    "Allemand": "German", "allemand": "German",
    "Italien": "Italian", "italien": "Italian",
    "Portugais": "Portuguese", "portugais": "Portuguese",
    "Chinois": "Chinese", "chinois": "Chinese",
    "Japonais": "Japanese", "japonais": "Japanese",
    "Russe": "Russian", "russe": "Russian",
    "Néerlandais": "Dutch", "néerlandais": "Dutch",
    "Turc": "Turkish", "turc": "Turkish",
    "Coréen": "Korean", "coréen": "Korean",
    "Polonais": "Polish", "polonais": "Polish",
    "Hébreu": "Hebrew", "hébreu": "Hebrew",
    "Suédois": "Swedish", "suédois": "Swedish",
    "Darija": "Darija",
}

_FR_EN_LANG_LEVELS: dict[str, str] = {
    "Langue maternelle": "Native language",
    "langue maternelle": "native language",
    "Natif": "Native", "natif": "native",
    "Bilingue": "Bilingual", "bilingue": "bilingual",
    "Courant": "Fluent", "courant": "fluent",
    "Avancé": "Advanced", "avancé": "advanced",
    "Intermédiaire": "Intermediate", "intermédiaire": "intermediate",
    "Seuil": "Threshold", "seuil": "threshold",
    "Opérationnel": "Professional", "opérationnel": "professional",
    "Professionnel": "Professional", "professionnel": "professional",
    "Débutant": "Beginner", "débutant": "beginner",
    "Notions": "Basic", "notions": "basic",
    "Parlé": "Spoken", "parlé": "spoken",
    "Lu et écrit": "Reading & writing",
    "lu et écrit": "reading & writing",
    "Lu, écrit et parlé": "Reading, writing & speaking",
}


# ── JSON schema for LLM translation call ──────────────────────────────────────
_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {"type": "array", "items": {"type": "string"}},
    },
}


# ── Utility functions ─────────────────────────────────────────────────────────

def _apply_word_dict(text: str) -> str:
    """Apply deterministic FR→EN word replacements before LLM (Fix #1)."""
    for pattern, replacement in _FR_EN_WORDS:
        text = pattern.sub(replacement, text)
    return text


def _translate_countries_months(text: str) -> str:
    """Translate country names and French month names in-place (Fix #5+6)."""
    for fr, en in _FR_EN_COUNTRIES.items():
        text = text.replace(fr, en)
    for pattern, replacement in _FR_EN_MONTHS:
        text = pattern.sub(replacement, text)
    return text


def _translate_language_line(text: str) -> str:
    """Translate a single Languages section line using dicts (Fix #4)."""
    for fr, en in _FR_EN_LANG_NAMES.items():
        text = re.sub(r"\b" + re.escape(fr) + r"\b", en, text)
    for fr, en in _FR_EN_LANG_LEVELS.items():
        text = re.sub(r"\b" + re.escape(fr) + r"\b", en, text)
    return text


def fix_indefinite_article(text: str) -> str:
    """Fix 'a API', 'a ETL', 'a IoT' → 'an API' etc. (Fix #7).
    Targets uppercase-initial acronyms/initialisms after masking restoration."""
    def _fix(m: re.Match) -> str:
        article = "An" if m.group(1)[0].isupper() else "an"
        return f"{article} {m.group(2)}"
    # Match 'a'/'A' followed by a vowel-initial word (handles acronyms & common words)
    return re.sub(r"\b([aA]) ([AEIOU][A-Za-z])", _fix, text)


def mask_terms(text: str) -> tuple[str, list[str]]:
    """Replace protected tech terms with ⟦T0⟧ placeholders, longest-first."""
    used: list[str] = []
    masked = text
    for term in PROTECTED_TERMS:
        pattern = re.compile(
            r"(?<![A-Za-z0-9._/-])" + re.escape(term) + r"(?![A-Za-z0-9._/-])"
        )

        def _replace(m: re.Match, _term: str = term) -> str:
            idx = len(used)
            used.append(_term)
            return f"⟦T{idx}⟧"

        masked = pattern.sub(_replace, masked)
    return masked, used


def restore_terms(text: str, terms: list[str]) -> str:
    """Restore ⟦Tn⟧ placeholders back to original tech terms."""
    def _replace(m: re.Match) -> str:
        idx = int(m.group(1))
        return terms[idx] if idx < len(terms) else m.group(0)
    return re.sub(r"⟦T(\d+)⟧", _replace, text)


# ── LLM translation call ──────────────────────────────────────────────────────

def translate_items(
    items: list[str],
    model: str,
    base_url: str,
    lt_url: str,
    use_no_think: bool = True,
) -> list[str]:
    """Translate a list of (masked) FR items to EN via LLM + LT en-US."""
    if not items:
        return items

    n = len(items)
    prompt = f"""{"/no_think" if use_no_think else ""}

You are a professional CV translator: French → English.

MANDATORY RULES:
- Translate each item from French to professional English
- Return EXACTLY {n} items in the SAME order
- Copy placeholders ⟦T0⟧ ⟦T1⟧ etc. VERBATIM — never modify them
- Preserve all markdown syntax (**, -, :, ###) exactly as-is
- Translate faithfully: do NOT rewrite, expand, summarize, or merge items
- Use professional, ATS-optimized English vocabulary

Return JSON: {{"items": ["translation1", "translation2", ...]}}

Input:
{json.dumps({"items": items}, ensure_ascii=False)}
"""

    try:
        result = call_ollama_json(
            base_url=base_url,
            model=model,
            prompt=prompt,
            format_schema=_TRANSLATION_SCHEMA,
            required_keys=["items"],
            temperature=0.0,
            timeout=600,
        )
    except OllamaError:
        return items

    translated = result.get("items", [])
    if len(translated) != n:
        return items

    corrected = []
    for t in translated:
        try:
            corrected.append(correct_text(t, lt_url, lang="en-US"))
        except Exception:
            corrected.append(t)
    return corrected


# ── Main translation pipeline ─────────────────────────────────────────────────

def translate_markdown_to_en(
    md_fr: str,
    model: str,
    base_url: str,
    lt_url: str,
) -> str:
    """
    Translate a FR CV markdown to EN, preserving structure exactly:
    1. Pre-process deterministic word substitutions
    2. Mask protected tech terms
    3. Single LLM call (JSON array)
    4. LanguageTool en-US correction
    5. Restore tech terms + fix indefinite articles
    6. Rebuild markdown with EN section headers, translated country/month names
    Languages section translated via dict (no LLM).
    """
    use_no_think = "qwen" in model.lower()
    lines = md_fr.splitlines()

    # ── Pass 1: identify translatable items and their positions ───────────────
    translatable: list[str] = []
    line_to_item: dict[int, int] = {}
    section_header_en: dict[int, str] = {}
    # exp header: line_idx → (rest_of_header, item_idx_for_position)
    exp_header_info: dict[int, tuple[str, int]] = {}
    # proj header: line_idx → (date_part, item_idx_for_title)
    proj_header_info: dict[int, tuple[str, int]] = {}
    # language lines: line_idx → translated string (dict-based, no LLM)
    lang_line_direct: dict[int, str] = {}

    STATE_HEADER = "header"
    current_state: str = STATE_HEADER
    saw_headline = False
    headline_line_idx: int | None = None

    for i, line in enumerate(lines):
        s = line.rstrip()

        # H1 name: skip
        if s.startswith("# "):
            continue

        # ## Section header
        if s.startswith("## "):
            heading_raw = s[3:].strip()
            heading_key = heading_raw.lower()
            en = _SECTION_EN_MD.get(heading_key, heading_raw)
            section_header_en[i] = en
            current_state = heading_key
            continue

        # Empty lines
        if not s:
            continue

        # ── HEADER state ──────────────────────────────────────────────────────
        if current_state == STATE_HEADER:
            if not saw_headline:
                m = re.match(r"^\*\*(.+)\*\*\s*$", s)
                if m:
                    saw_headline = True
                    headline_line_idx = i
                    line_to_item[i] = len(translatable)
                    translatable.append(m.group(1).strip())
                    continue
            # contact line or anything else in header: skip
            continue

        # ── RÉSUMÉ ────────────────────────────────────────────────────────────
        if current_state in ("resume professionnel", "résumé professionnel",
                              "resumé professionnel", "professional summary"):
            if not s.startswith("#"):
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(s))
            continue

        # ── COMPÉTENCES ───────────────────────────────────────────────────────
        if current_state in ("competences cles", "compétences clés",
                              "competences clés", "key skills"):
            if s.startswith("- "):
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(s[2:].strip()))
            continue

        # ── EXPÉRIENCES ───────────────────────────────────────────────────────
        if current_state in ("experiences", "expériences", "experience"):
            if s.startswith("### "):
                header = s[4:].strip()
                parts = header.split(" - ")
                position = parts[0].strip()
                rest = " - ".join(parts[1:]) if len(parts) > 1 else ""
                item_idx = len(translatable)
                exp_header_info[i] = (rest, item_idx)
                line_to_item[i] = item_idx
                translatable.append(_apply_word_dict(position))
            elif s.startswith("- "):
                # Fix #2: translate ALL bullets including Stack lines
                # Tech terms are protected by masking; FR descriptive terms get translated
                bullet = s[2:].strip()
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(bullet))
            elif not s.startswith("#"):
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(s))
            continue

        # ── PROJETS ───────────────────────────────────────────────────────────
        if current_state in ("projets", "projects"):
            if s.startswith("### "):
                # Fix #3: translate project titles (they are descriptive, not proper nouns)
                header = s[4:].strip()
                # Try to split off a trailing date (e.g. "Title - 2023-2024")
                m_date = re.search(
                    r"\s*[-—]\s*(\d{4}[-–/]\w.*|\w+[-–]\w+\s*\d{4}.*)$", header
                )
                if m_date:
                    title_part = header[:m_date.start()].strip()
                    date_part = m_date.group(0).strip(" -—")
                else:
                    title_part = header
                    date_part = ""
                item_idx = len(translatable)
                proj_header_info[i] = (date_part, item_idx)
                line_to_item[i] = item_idx
                translatable.append(_apply_word_dict(title_part))
            elif s.startswith("- "):
                # Fix #2: translate project bullets including Stack lines
                bullet = s[2:].strip()
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(bullet))
            elif not s.startswith("#") and not re.match(r"^\*\*[^*]+\*\*\s*$", s):
                line_to_item[i] = len(translatable)
                translatable.append(_apply_word_dict(s))
            continue

        # ── FORMATION: skip (proper nouns — schools, degrees, dates) ──────────
        if current_state in ("formation", "education"):
            continue

        # ── LANGUES: Fix #4 — dict-based translation, no LLM ─────────────────
        if current_state in ("langues", "languages"):
            if s.startswith("- "):
                translated_lang = _translate_language_line(s[2:].strip())
                lang_line_direct[i] = f"- {translated_lang}"
            continue

    if not translatable:
        # Still apply language translations and section headers even with no LLM items
        output = list(lines)
        for i, en_head in section_header_en.items():
            output[i] = f"## {en_head}"
        for i, lang_line in lang_line_direct.items():
            output[i] = lang_line
        return "\n".join(output)

    # ── Pass 2: mask protected terms ──────────────────────────────────────────
    masked_items: list[str] = []
    terms_per_item: list[list[str]] = []
    for item in translatable:
        masked, terms = mask_terms(item)
        masked_items.append(masked)
        terms_per_item.append(terms)

    # ── Pass 3: LLM translate + LT en-US ──────────────────────────────────────
    translated = translate_items(masked_items, model, base_url, lt_url, use_no_think)

    # ── Pass 4: restore tech terms + fix indefinite article ───────────────────
    restored: list[str] = [
        fix_indefinite_article(restore_terms(t, terms))
        for t, terms in zip(translated, terms_per_item)
    ]

    # ── Pass 5: rebuild markdown ──────────────────────────────────────────────
    output = list(lines)

    for i, line in enumerate(lines):
        s = line.rstrip()

        # EN section headers
        if i in section_header_en:
            output[i] = f"## {section_header_en[i]}"
            continue

        # Language lines (dict-translated, no LLM)
        if i in lang_line_direct:
            output[i] = lang_line_direct[i]
            continue

        # Headline **text** (tracked by headline_line_idx)
        if i == headline_line_idx and i in line_to_item:
            output[i] = f"**{restored[line_to_item[i]]}**"
            continue

        # ### Experience header: translate position, apply country+month to rest
        if i in exp_header_info:
            rest, item_idx = exp_header_info[i]
            translated_pos = restored[item_idx]
            rest_en = _translate_countries_months(rest)
            output[i] = f"### {translated_pos} - {rest_en}" if rest_en else f"### {translated_pos}"
            continue

        # ### Project header: translated title + date
        if i in proj_header_info:
            date_part, item_idx = proj_header_info[i]
            translated_title = restored[item_idx]
            date_en = _translate_countries_months(date_part)
            output[i] = f"### {translated_title} - {date_en}" if date_en else f"### {translated_title}"
            continue

        # Regular translatable lines
        if i in line_to_item:
            t = restored[line_to_item[i]]
            if s.startswith("- "):
                output[i] = f"- {t}"
            elif re.match(r"^\*\*.+\*\*\s*$", s):
                output[i] = f"**{t}**"
            else:
                output[i] = t

    return "\n".join(output)
