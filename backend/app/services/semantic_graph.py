import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .text_utils import normalize_text


GRAPH_DOCKER_PATH = Path("/app/data/semantic_graph.json")
GRAPH_FALLBACK_PATH = Path("data/semantic_graph.json")


def _graph_path() -> Path:
    env_path = os.getenv("SEMANTIC_GRAPH_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    if GRAPH_DOCKER_PATH.exists():
        return GRAPH_DOCKER_PATH
    return GRAPH_FALLBACK_PATH


@lru_cache(maxsize=1)
def load_semantic_graph() -> Dict[str, Any]:
    path = _graph_path()
    if not path.exists():
        return {"schema_version": "1.0", "nodes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def node_terms(name: str, node: Dict[str, Any]) -> List[str]:
    terms = [name]
    terms.extend(node.get("aliases", []) if isinstance(node.get("aliases"), list) else [])
    terms.extend(node.get("ats_terms", []) if isinstance(node.get("ats_terms"), list) else [])
    return [term for term in terms if str(term).strip()]


def contains_term(text: str, term: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    if len(normalized_term) <= 4:
        return re.search(r"\b" + re.escape(normalized_term) + r"\b", normalized_text) is not None
    return normalized_term in normalized_text


def nodes_mentioned_in_text(text: str) -> List[str]:
    graph = load_semantic_graph()
    nodes = graph.get("nodes", {})
    mentioned = []
    for name, node in nodes.items():
        if any(contains_term(text, term) for term in node_terms(name, node)):
            mentioned.append(name)
    return mentioned


def related_terms_for_node(name: str, min_weight: float = 0.4) -> List[str]:
    graph = load_semantic_graph()
    nodes = graph.get("nodes", {})
    node = nodes.get(name, {})
    terms: List[str] = []

    for related_name, relation in node.get("related", {}).items():
        if not isinstance(relation, dict):
            continue
        weight = float(relation.get("weight", 0))
        if weight < min_weight:
            continue
        related_node = nodes.get(related_name, {})
        terms.append(related_name)
        terms.extend(node_terms(related_name, related_node))

    return list(dict.fromkeys(term for term in terms if str(term).strip()))


def expand_text_with_graph(text: str, min_weight: float = 0.4) -> str:
    additions: List[str] = []
    for node_name in nodes_mentioned_in_text(text):
        additions.extend(related_terms_for_node(node_name, min_weight=min_weight))
    additions = list(dict.fromkeys(additions))
    if not additions:
        return text
    return f"{text}\n{' '.join(additions)}"


def find_best_semantic_evidence(
    requirement: str,
    evidence_bank: List[Dict[str, Any]],
    min_weight: float = 0.4,
    limit: int = 3,
) -> Optional[Dict[str, Any]]:
    graph = load_semantic_graph()
    nodes = graph.get("nodes", {})
    requirement_nodes = nodes_mentioned_in_text(requirement)
    if not requirement_nodes:
        return None

    candidates: List[Dict[str, Any]] = []
    for req_node_name in requirement_nodes:
        req_node = nodes.get(req_node_name, {})
        for related_name, relation in req_node.get("related", {}).items():
            if not isinstance(relation, dict):
                continue
            weight = float(relation.get("weight", 0))
            if weight < min_weight:
                continue
            terms = [related_name]
            terms.extend(node_terms(related_name, nodes.get(related_name, {})))
            matches = [
                ev["id"]
                for ev in evidence_bank
                if any(contains_term(ev.get("text", ""), term) for term in terms)
            ][:limit]
            if matches:
                candidates.append({
                    "requirement_node": req_node_name,
                    "matched_node": related_name,
                    "weight": weight,
                    "relation": relation.get("relation", "transferable"),
                    "evidence_ids": matches,
                })

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item["weight"], len(item["evidence_ids"])), reverse=True)
    best = candidates[0]
    if best["weight"] >= 0.6:
        status = "TRANSFERABLE"
    else:
        status = "WEAK"

    best["status"] = status
    return best
