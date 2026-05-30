# AutoCV — Générateur de CV intelligent

Génère automatiquement un CV ciblé et une lettre de motivation à partir d'une offre d'emploi, en s'appuyant sur votre CV source et un LLM local via Ollama. Tout tourne en local, aucune donnée ne quitte votre machine.

---

## Sommaire

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Préparer votre CV source](#préparer-votre-cv-source)
  - [Format Database (recommandé)](#format-database-recommandé)
  - [Format Rich (francophone)](#format-rich-francophone)
  - [Format Legacy](#format-legacy)
- [Ajouter une photo](#ajouter-une-photo)
- [Utiliser l'application](#utiliser-lapplication)
- [Fichiers générés](#fichiers-générés)
- [Thèmes PDF](#thèmes-pdf)
- [Thème custom (custom1)](#thème-custom-custom1)
- [Variables d'environnement](#variables-denvironnement)
- [Structure du projet](#structure-du-projet)
- [API](#api)
- [Dépannage](#dépannage)

---

## Prérequis

| Outil | Version minimum | Rôle |
|-------|----------------|------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 24+ | Conteneurs backend + frontend |
| [Ollama](https://ollama.com/) | dernière | Serveur LLM local |
| `qwen3:8b` | — | Modèle matching (analyse) |
| `qwen3:14b` | — | Modèle génération (rédaction) |

Ollama doit tourner **sur l'hôte** (pas dans Docker). Les conteneurs le joignent via `host.docker.internal`.

---

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/votre-utilisateur/auto-cv-gen-docker.git
cd auto-cv-gen-docker
```

### 2. Télécharger les modèles Ollama

```bash
ollama pull qwen3:8b
ollama pull qwen3:14b
```

> **Note :** `qwen3:8b` fait ~5 Go, `qwen3:14b` ~9 Go. Le preset *Rapide* (8b/8b) permet de se limiter à un seul modèle.

### 3. Configurer l'environnement

```bash
cp .env.example .env
```

Éditez `.env` si nécessaire (voir [Variables d'environnement](#variables-denvironnement)).

### 4. Lancer les conteneurs

```bash
docker compose up -d --build
```

Première exécution : Docker télécharge et compile les images (~2–3 min).

### 5. Ouvrir l'application

```
http://localhost:3000
```

---

## Configuration

### `.env` (à la racine)

```env
# Modèles Ollama
MATCHING_MODEL=qwen3:8b
GENERATION_MODEL=qwen3:14b

# URL Ollama — ne pas modifier sauf si Ollama tourne dans Docker
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Nombre de preuves récupérées depuis votre CV (défaut : 45)
TOP_K=45
```

Après toute modification du `.env` : `docker compose up -d`.

---

## Préparer votre CV source

Le fichier doit s'appeler **`cv_master.json`** et se placer dans le dossier `data/` :

```
auto-cv-gen-docker/
└── data/
    └── cv_master.json   ← votre CV
```

Le système accepte **trois formats** JSON. Il détecte automatiquement lequel vous utilisez.

---

### Format Database (recommandé)

Format le plus complet. Champs en **anglais**, dates ISO (`YYYY-MM-DD` ou `YYYY-MM`).

```json
{
  "profile": {
    "firstName": "Prénom",
    "lastName": "Nom",
    "title": "Titre professionnel actuel",
    "summary": "Résumé professionnel en quelques phrases.",
    "location": {
      "city": "Paris",
      "country": "France"
    },
    "contact": {
      "email": "vous@exemple.fr",
      "phone": "+33 6 00 00 00 00",
      "linkedin": "https://linkedin.com/in/votre-profil",
      "github": "https://github.com/votre-pseudo"
    }
  },

  "targetRoles": [
    "Développeur Python Backend",
    "Ingénieur Data"
  ],

  "skills": {
    "technical": {
      "programmingLanguages": ["Python", "SQL", "Bash"],
      "backend":              ["FastAPI", "Flask", "API REST"],
      "dataEngineering":      ["Pandas", "NumPy", "ETL"],
      "databases":            ["PostgreSQL", "MySQL", "MongoDB"],
      "devOpsTools":          ["Docker", "Git", "Linux"],
      "frontend":             ["React", "JavaScript"],
      "embeddedIoT":          ["Arduino", "MQTT"]
    },
    "softSkills":    ["Rigueur", "Autonomie", "Communication"],
    "methodologies": ["Agile", "Scrum", "TDD"]
  },

  "experiences": [
    {
      "company":      "Nom de l'entreprise",
      "position":     "Titre du poste",
      "startDate":    "2022-09",
      "endDate":      "2024-06",
      "isCurrent":    false,
      "contractType": "CDI",
      "location": {
        "city": "Paris",
        "country": "France"
      },
      "summary": "Description synthétique du poste.",
      "missions": [
        "Mission 1 — action concrète réalisée.",
        "Mission 2 — résultat ou impact mesurable."
      ],
      "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"],
      "keywords":     ["backend", "API", "données"],
      "achievements": [
        {
          "description": "Réduction du temps de traitement de 40 %.",
          "impact":      "Économie de 2h/jour sur le pipeline de données."
        }
      ]
    }
  ],

  "education": [
    {
      "school":          "Nom de l'école",
      "degree":          "Master Informatique",
      "field":           "Génie logiciel",
      "startDate":       "2020-09",
      "endDate":         "2022-06",
      "isCurrent":       false,
      "relevantCourses": ["Algorithmes", "Machine Learning", "Systèmes distribués"]
    }
  ],

  "languages": [
    { "language": "Français", "level": "Natif"   },
    { "language": "Anglais",  "level": "Courant" },
    { "language": "Arabe",    "level": "Parlé"   }
  ],

  "certifications": [
    { "name": "TOEIC 850" },
    { "name": "AWS Cloud Practitioner" }
  ],

  "projects": [
    {
      "name":         "Nom du projet",
      "startDate":    "2023-01",
      "endDate":      "2023-06",
      "description":  "Description du projet et de son objectif.",
      "problemSolved":"Problème résolu ou besoin couvert.",
      "features":     ["Fonctionnalité A", "Fonctionnalité B"],
      "highlights":   ["Résultat clé 1", "Résultat clé 2"],
      "technologies": ["Python", "React", "Docker"]
    }
  ]
}
```

---

### Format Rich (francophone)

Champs en **français**. Adapté si votre CV source est déjà rédigé en français.

```json
{
  "profil": {
    "prenom": "Prénom",
    "nom":    "Nom",
    "titre_cible_principal": "Titre professionnel",
    "titres_alternatifs":    ["Titre alternatif 1", "Titre alternatif 2"],
    "resume_court": "Résumé court (2-3 phrases).",
    "resume_long":  "Résumé détaillé.",
    "mots_cles":    ["Python", "API", "Data"],
    "localisation": { "ville": "Paris", "pays": "France" },
    "contact": {
      "email":     "vous@exemple.fr",
      "telephone": "06 00 00 00 00",
      "linkedin":  "https://linkedin.com/in/profil",
      "github":    "https://github.com/pseudo"
    }
  },

  "experiences": [
    {
      "entreprise":   "Nom entreprise",
      "poste":        "Titre du poste",
      "localisation": "Paris, France",
      "periode":      { "debut": "09/2022", "fin": "06/2024" },
      "contexte":     "Contexte de la mission.",
      "missions": [
        "Mission réalisée 1.",
        "Mission réalisée 2."
      ],
      "stack":             ["Python", "Docker", "PostgreSQL"],
      "competences_clefs": ["API REST", "ETL", "CI/CD"],
      "notes":             ["Note complémentaire optionnelle."]
    }
  ],

  "formations": [
    {
      "ecole":     "Nom de l'école",
      "intitule":  "Master Informatique",
      "specialite":"Génie logiciel",
      "modalite":  "Formation initiale",
      "periode":   { "debut": "09/2020", "fin": "06/2022" },
      "competences_associees": ["Python", "Machine Learning"],
      "memoire": {
        "titre":  "Titre du mémoire (optionnel)",
        "themes": ["Thème A", "Thème B"]
      }
    }
  ],

  "competences": {
    "langages": ["Python", "SQL", "JavaScript"],
    "backend":  ["FastAPI", "Flask", "API REST"],
    "devops":   ["Docker", "Git", "Linux"]
  },

  "langues": [
    {
      "langue":  "Français",
      "niveau":  "Natif",
      "preuves": ["Langue maternelle"]
    },
    {
      "langue":  "Anglais",
      "niveau":  "Courant",
      "certification": { "nom": "TOEIC", "score": "850" },
      "preuves": ["Lu, écrit, parlé"]
    }
  ],

  "projets_realises": [
    {
      "nom":         "Nom du projet",
      "description": "Description.",
      "stack":       ["Python", "React"]
    }
  ]
}
```

---

### Format Legacy

Format simplifié. Utile pour un premier test rapide.

```json
{
  "profile": {
    "identity": {
      "current_title": "Titre professionnel"
    },
    "professional_positioning": {
      "main_positioning": "Description de votre positionnement.",
      "short_pitch":      "Pitch court en 1-2 phrases.",
      "key_strengths":    ["Force 1", "Force 2", "Force 3"]
    }
  },

  "experiences": [
    {
      "company":              "Nom entreprise",
      "role":                 "Titre du poste",
      "context":              "Contexte de la mission.",
      "description":          "Description générale.",
      "missions":             ["Mission 1.", "Mission 2."],
      "achievements":         ["Réalisation 1.", "Réalisation 2."],
      "technical_environment":["Python", "Docker", "Linux"]
    }
  ],

  "education": [
    {
      "school": "Nom de l'école",
      "degree": "Master Informatique",
      "field":  "Génie logiciel",
      "skills": ["Python", "Algo"]
    }
  ],

  "skills": {
    "programmingLanguages": ["Python", "SQL"],
    "backend":              ["FastAPI", "API REST"],
    "databases":            ["PostgreSQL"]
  },

  "languages": [
    { "language": "Français", "level": "Natif"   },
    { "language": "Anglais",  "level": "Courant" }
  ],

  "projects_and_themes": [
    {
      "name":               "Nom du projet",
      "description":        "Description courte.",
      "associated_skills":  ["Python", "Docker"]
    }
  ],

  "soft_skills": ["Rigueur", "Autonomie"]
}
```

> Un exemple complet est disponible dans `data/cv_master.example.json`.

---

## Ajouter une photo

La photo s'affiche uniquement avec le thème **Custom 1**. Elle est ignorée pour les autres thèmes.

**Formats acceptés :** `.jpg`, `.jpeg`, `.png`

**Emplacement :**

```
auto-cv-gen-docker/
└── data/
    ├── cv_master.json
    └── photo.jpg        ← votre photo (ou .png / .jpeg)
```

**Règles :**
- Si plusieurs fichiers existent, la priorité est : `photo.jpg` > `photo.jpeg` > `photo.png`
- Aucune configuration supplémentaire : la photo est copiée automatiquement au moment du rendu
- Format recommandé : portrait, ratio 1:1, minimum 300×300 px

---

## Utiliser l'application

### Workflow en 3 étapes

**1. Charger votre CV**

Cliquez sur **↑ Charger CV JSON** dans la sidebar et sélectionnez votre `cv_master.json`. L'indexation est automatique (~45 preuves extraites).

**2. Coller une offre d'emploi**

Copiez le texte complet de l'offre dans la zone principale. L'URL de l'offre est optionnelle (conservée dans l'historique).

**3. Générer**

Cliquez sur **Générer →**. Le pipeline s'exécute en 5 étapes visibles dans la sidebar :

| Étape | Durée estimée | Description |
|-------|--------------|-------------|
| Récupération des preuves | < 1 s | Recherche FTS5 + TF-IDF dans votre CV |
| Analyse de matching | 30–90 s | LLM 8b analyse l'offre vs votre profil |
| Génération du CV | 60–180 s | LLM 14b rédige bullets, résumé, lettre |
| Audit anti-hallucination | < 1 s | Vérifie que rien n'est inventé |
| Export PDF | 5–15 s | RenderCV compile le PDF via Typst |

### Presets modèles

| Preset | Matching | Génération | Usage |
|--------|----------|-----------|-------|
| **Équilibré** (défaut) | qwen3:8b | qwen3:14b | Meilleur rapport qualité/vitesse |
| Rapide | qwen3:8b | qwen3:8b | VRAM limitée ou test rapide |
| Qualité | qwen3:14b | qwen3:30b | Meilleure qualité, plus lent |

---

## Fichiers générés

Tous les fichiers sont créés dans `outputs/` :

| Fichier | Format | Contenu |
|---------|--------|---------|
| `cv_targeted.pdf` | PDF | CV mis en forme via RenderCV |
| `cv_targeted.docx` | Word | CV éditable |
| `cv_recruiter.md` | Markdown | CV texte (copier-coller ATS) |
| `email.md` | Markdown | Lettre de motivation structurée |
| `audit_report.md` | Markdown | Rapport anti-hallucination |
| `cv_targeted.yaml` | YAML | Données brutes RenderCV (éditables) |
| `matching_analysis.json` | JSON | Analyse matching complète |
| `generated_cv.json` | JSON | CV généré brut |

L'**éditeur inline** (section "Édition PDF") permet de modifier titre, résumé, compétences et bullets directement dans l'interface, puis de régénérer le PDF sans relancer la génération LLM.

---

## Thèmes PDF

Deux thèmes disponibles dans l'éditeur :

| Thème | Description |
|-------|-------------|
| **Engineering Classic** | Thème intégré RenderCV. Sobre, noir sur blanc. |
| **Custom 1** | Thème custom. En-tête sombre avec photo, accents colorés. |

### Presets de mise en page

| Preset | Police | Marges | Usage |
|--------|--------|--------|-------|
| Classique | 9.25 pt | Normales | Standard |
| Tech | 9.15 pt | Normales | Profils techniques |
| Dense ATS | 8.75 pt | Compactes | Maximiser le contenu |
| Aéré | 9.75 pt | Larges | Peu d'expérience |

---

## Thème custom (custom1)

### Emplacement

```
auto-cv-gen-docker/
└── customcv/
    └── custom1/
        ├── __init__.py              ← modèle de design (tokens Pydantic)
        ├── Preamble.j2.typ          ← configuration Typst globale
        ├── Header.j2.typ            ← en-tête avec photo
        ├── SectionBeginning.j2.typ  ← titre de section avec icône
        ├── SectionEnding.j2.typ
        └── entries/
            ├── ExperienceEntry.j2.typ
            ├── EducationEntry.j2.typ
            ├── OneLineEntry.j2.typ
            └── ...
```

### Modifier le thème

Les fichiers `.j2.typ` utilisent la syntaxe **Jinja2 + Typst**. Modifiez-les directement dans `customcv/custom1/`. Le dossier est monté en volume read-only (`./customcv:/custom:ro`), donc **les changements prennent effet sans rebuild** — relancez simplement une génération.

### Ajouter un thème custom

1. Créez `customcv/mon-theme/` avec les fichiers templates `.j2.typ`
2. Créez `__init__.py` avec `class MonThemeTheme(BaseModelWithoutExtraKeys)` et `theme: Literal["mon-theme"]`
3. Ajoutez le routing dans `backend/app/services/rendercv_export.py` → `build_design()`
4. Ajoutez l'option dans `frontend/src/main.jsx` → sélecteur thème

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MATCHING_MODEL` | `qwen3:8b` | LLM pour l'analyse matching |
| `GENERATION_MODEL` | `qwen3:14b` | LLM pour la rédaction |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | URL du serveur Ollama |
| `TOP_K` | `45` | Preuves extraites du CV pour la recherche |
| `MAX_EVIDENCE_FOR_LLM` | `60` | Plafond envoyé au LLM |
| `CV_PATH` | `/app/data/cv_master.json` | Chemin interne du CV |
| `OUTPUT_DIR` | `/app/outputs` | Dossier de sortie |

---

## Structure du projet

```
auto-cv-gen-docker/
│
├── data/                          ← vos fichiers personnels (volume)
│   ├── cv_master.json             ← votre CV source  (obligatoire)
│   ├── cv_master.example.json     ← exemple de référence
│   ├── photo.jpg                  ← photo Custom 1  (optionnel)
│   └── semantic_graph.json        ← graphe sémantique (auto-généré)
│
├── customcv/                      ← thèmes PDF custom (volume)
│   └── custom1/
│
├── outputs/                       ← fichiers générés (volume)
├── storage/                       ← SQLite : index CV + historique (volume)
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                ← routes FastAPI
│       ├── prompts.py             ← prompts LLM
│       ├── schemas.py             ← modèles Pydantic
│       ├── core/config.py         ← Settings
│       └── services/
│           ├── evidence.py        ← extraction preuves depuis cv_master
│           ├── retrieval.py       ← recherche FTS5 + TF-IDF
│           ├── matching.py        ← pipeline matching + score ATS
│           ├── audit.py           ← anti-hallucination
│           ├── rendercv_export.py ← export PDF/DOCX
│           ├── ollama_client.py   ← client Ollama
│           └── history.py         ← historique
│
├── frontend/
│   ├── Dockerfile
│   └── src/
│       ├── main.jsx               ← interface React
│       └── style.css              ← design system
│
├── docker-compose.yml
├── .env                           ← votre configuration
└── .env.example                   ← modèle
```

---

## API

Le backend expose une API REST sur `http://localhost:8000`.

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/health` | Statut + modèles configurés |
| `POST` | `/api/upload-cv` | Charger un nouveau `cv_master.json` |
| `POST` | `/api/index-cv` | Ré-indexer le CV |
| `GET` | `/api/evidence` | Lister les preuves indexées |
| `POST` | `/api/generate-cv` | Générer un CV (réponse synchrone) |
| `POST` | `/api/generate-cv/stream` | Générer un CV (Server-Sent Events) |
| `POST` | `/api/update-pdf` | Régénérer le PDF avec CV édité |
| `GET` | `/api/download/pdf` | Télécharger le dernier PDF |
| `GET` | `/api/download/docx` | Télécharger le dernier DOCX |
| `GET` | `/api/preview/pdf` | Prévisualiser le dernier PDF |
| `GET` | `/api/history` | Historique des générations |
| `GET` | `/api/history/{id}` | Détail d'une entrée |
| `GET` | `/api/history/{id}/pdf` | PDF d'une entrée historique |
| `DELETE` | `/api/history/{id}` | Supprimer une entrée |

Documentation interactive Swagger : `http://localhost:8000/docs`

---

## Dépannage

**Le PDF n'est pas généré**

Vérifiez `outputs/rendercv_error.txt`. Causes fréquentes :
- Photo dans un format invalide ou corrompue (voir [Ajouter une photo](#ajouter-une-photo))
- Erreur de syntaxe dans un template Typst custom

**Ollama non joignable**

```bash
# Vérifier qu'Ollama tourne sur l'hôte
ollama list

# Tester la connexion depuis le conteneur
docker exec auto-cv-backend curl -s http://host.docker.internal:11434/api/tags
```

**CV non chargé après redémarrage**

Le CV est persisté dans `data/cv_master.json` mais l'index SQLite est dans `storage/`. Si `storage/` est vide, cliquez sur **Re-indexer** dans l'interface.

**Rebuild après modification du code backend ou frontend**

```bash
docker compose up -d --build
```

Les modifications dans `customcv/` et `data/` **ne nécessitent pas de rebuild** (volumes montés).

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| LLM | Ollama (qwen3:8b / qwen3:14b) |
| Index CV | SQLite FTS5, TF-IDF maison |
| Export PDF | [RenderCV](https://github.com/sinaatalay/rendercv) 2.8 + Typst |
| Export DOCX | python-docx |
| Frontend | React 18, CSS custom (Plus Jakarta Sans) |
| Conteneurs | Docker Compose — backend FastAPI + frontend Nginx |
