import json
import logging
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


def _num_ctx_for_model(model: str) -> int:
    name = model.lower()
    for size, ctx in [
        ("72b", 32768), ("70b", 32768),
        ("34b", 16384), ("32b", 16384),
        ("30b", 16384),
        ("22b", 16384),
        ("14b", 12288), ("13b", 12288),
    ]:
        if size in name:
            return ctx
    return 8192


def _strip_think_tags(text: str) -> str:
    """Supprime les balises <think>…</think> produites par les modèles Qwen3."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json_braces(text: str) -> str:
    """Fallback : extrait le premier objet JSON {...} trouvé dans du texte libre."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        return text[first:last + 1]
    return text


def _parse_ollama_response(raw: str, required_keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Parse la réponse Ollama en deux passes :
    1. Strip <think> + json.loads direct  (chemin rapide — Ollama avec schéma garanti)
    2. Extraction brace {…}               (fallback — Ollama sans contrainte ou ancienne version)
    """
    cleaned = _strip_think_tags(raw)

    # Chemin rapide : le schéma Ollama garantit un JSON valide
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback : le modèle a quand même ajouté du texte autour
        logger.warning("JSON direct invalide — fallback extraction brace. Début : %.200s", raw)
        try:
            data = json.loads(_extract_json_braces(cleaned))
        except json.JSONDecodeError as exc:
            raise OllamaError(
                f"Réponse Ollama invalide même après fallback. Début : {raw[:500]}"
            ) from exc

    if data == {}:
        raise OllamaError("Ollama a renvoyé un JSON vide {}.")

    if required_keys:
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise OllamaError(f"JSON Ollama incomplet. Clés manquantes : {missing}")

    return data


def clean_json_text(text: str) -> str:
    """Conservé pour compatibilité — préférer _parse_ollama_response."""
    return _extract_json_braces(_strip_think_tags(text))


def iter_ollama_stream(
    base_url: str,
    model: str,
    prompt: str,
    format_schema: Optional[Dict[str, Any]] = None,
    temperature: float = 0.1,
    timeout: int = 900,
    num_ctx: Optional[int] = None,
    num_predict: int = 8192,
) -> Generator[Tuple[str, bool], None, None]:
    """
    Stream les tokens Ollama un par un.
    Yields (token: str, is_done: bool) pour chaque chunk reçu.
    Raises OllamaError sur erreur HTTP ou réseau.
    """
    resolved_ctx = num_ctx if num_ctx is not None else _num_ctx_for_model(model)
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "format": format_schema if format_schema else "json",
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_ctx": resolved_ctx,
            "num_predict": num_predict,
        },
    }
    try:
        response = requests.post(url, json=payload, stream=True, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Erreur Ollama : {exc}") from exc

    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield chunk.get("response", ""), chunk.get("done", False)
        if chunk.get("done"):
            break


def parse_streaming_result(
    raw: str,
    required_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parse le JSON accumulé depuis un stream Ollama."""
    return _parse_ollama_response(raw, required_keys=required_keys)


def call_ollama_json(
    base_url: str,
    model: str,
    prompt: str,
    format_schema: Optional[Dict[str, Any]] = None,
    required_keys: Optional[List[str]] = None,
    temperature: float = 0.1,
    timeout: int = 900,
    num_ctx: Optional[int] = None,
    num_predict: int = 8192,
    max_retries: int = 1,
) -> Dict[str, Any]:
    resolved_ctx = num_ctx if num_ctx is not None else _num_ctx_for_model(model)
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": format_schema if format_schema else "json",
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_ctx": resolved_ctx,
            "num_predict": num_predict,
        },
    }
    last_exc: Optional[OllamaError] = None
    for attempt in range(1 + max_retries):
        if attempt > 0:
            logger.warning("Retry Ollama JSON (tentative %d/%d) : %s", attempt + 1, 1 + max_retries, last_exc)
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Erreur Ollama : {exc}") from exc
        raw = response.json().get("response", "")
        try:
            return _parse_ollama_response(raw, required_keys=required_keys)
        except OllamaError as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]
