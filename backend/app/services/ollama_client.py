import json
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests


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


def clean_json_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1:
        return text[first:last + 1]
    return text


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
    """Parse et valide le JSON accumulé depuis un stream Ollama."""
    cleaned = clean_json_text(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise OllamaError(
            f"Réponse Ollama streaming invalide ou tronquée. Début : {raw[:500]}"
        ) from exc
    if data == {}:
        raise OllamaError("Ollama a renvoyé un JSON vide {}.")
    if required_keys:
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise OllamaError(f"JSON Ollama incomplet. Clés manquantes : {missing}")
    return data


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
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Erreur Ollama : {exc}") from exc

    response_data = response.json()
    raw = response_data.get("response", "")
    cleaned = clean_json_text(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        done_reason = response_data.get("done_reason")
        suffix = f" Raison Ollama : {done_reason}." if done_reason else ""
        raise OllamaError(
            f"Réponse Ollama JSON invalide ou tronquée.{suffix} Début réponse : {raw[:1000]}"
        ) from exc

    if data == {}:
        raise OllamaError("Ollama a renvoyé un JSON vide {}.")

    if required_keys:
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise OllamaError(f"JSON Ollama incomplet. Clés manquantes : {missing}")

    return data
