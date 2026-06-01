from __future__ import annotations

import logging
import os
import re

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

# En Docker : pointe vers le chromium Debian installé via apt.
# En dev local : None → Playwright utilise son propre browser managé.
_CHROMIUM_EXE: str | None = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None

# Sites qui bloquent le scraping headless de façon systématique
_BLOCKED_DOMAINS = {
    "linkedin.com":  "LinkedIn exige une connexion — copie-colle le texte de l'offre manuellement.",
    "indeed.com":    "Indeed est protégé par Cloudflare — copie-colle le texte de l'offre manuellement.",
    "indeed.fr":     "Indeed est protégé par Cloudflare — copie-colle le texte de l'offre manuellement.",
    "glassdoor.com": "Glassdoor exige une connexion — copie-colle le texte de l'offre manuellement.",
    "glassdoor.fr":  "Glassdoor exige une connexion — copie-colle le texte de l'offre manuellement.",
}

logger = logging.getLogger(__name__)

# Sélecteurs de contenu principal, du plus spécifique au plus générique
_SELECTORS: dict[str, list[str]] = {
    "apec.fr": [
        "[class*='job-description']",
        "[class*='offre-detail']",
        "[class*='job-details']",
        "main",
    ],
    "indeed": [
        "#jobDescriptionText",
        "[class*='jobsearch-JobComponent-description']",
        "[class*='job-description']",
        "main",
    ],
    "linkedin.com": [
        ".description__text",
        "[class*='job-view-layout']",
        "[class*='jobs-description']",
        "main",
    ],
    "_default": ["main", "article", "[role='main']", "#content", "body"],
}


def _site_key(url: str) -> str:
    m = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", url.lower())
    return m.group(1) if m else ""


def _selectors_for(url: str) -> list[str]:
    domain = _site_key(url)
    for key, sels in _SELECTORS.items():
        if key != "_default" and key in domain:
            return sels
    return _SELECTORS["_default"]


def check_blocked(url: str) -> None:
    """Lève RuntimeError immédiatement si le domaine est connu pour bloquer le scraping."""
    domain = _site_key(url)
    for blocked, msg in _BLOCKED_DOMAINS.items():
        if blocked in domain:
            raise RuntimeError(msg)


async def scrape_offer(url: str, timeout_ms: int = 25_000) -> str:
    """
    Récupère le texte principal d'une page offre d'emploi via Playwright headless.
    Retourne le texte brut nettoyé, prêt à envoyer au LLM.
    Lève RuntimeError si la page est inaccessible ou trop courte.
    """
    check_blocked(url)
    async with async_playwright() as pw:
        launch_kwargs: dict = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        }
        if _CHROMIUM_EXE:
            launch_kwargs["executable_path"] = _CHROMIUM_EXE
        browser = await pw.chromium.launch(**launch_kwargs)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            )
            page = await ctx.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Laisser le JS se terminer, sans bloquer trop longtemps
            try:
                await page.wait_for_load_state("networkidle", timeout=7_000)
            except PlaywrightTimeout:
                pass

            # Essaye les sélecteurs dans l'ordre : s'arrête dès qu'on a un texte riche
            text = ""
            for selector in _selectors_for(url):
                try:
                    el = await page.query_selector(selector)
                    if el:
                        candidate = (await el.inner_text()).strip()
                        if len(candidate) > len(text):
                            text = candidate
                        if len(text) > 500:
                            break
                except Exception:
                    continue

            if len(text) < 100:
                raise RuntimeError(
                    "Texte trop court après récupération — la page nécessite peut-être une connexion, "
                    "ou est protégée anti-bot."
                )

            return _clean(text)
        finally:
            await browser.close()


def _clean(text: str) -> str:
    """Réduit le bruit : répétitions de sauts de ligne et espaces, troncature à 8 000 chars."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text[:8_000].strip()
