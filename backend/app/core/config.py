from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model: str = "qwen3:8b"          # fallback rétrocompat
    matching_model: str = "qwen3:8b"
    generation_model: str = "qwen3:14b"
    ollama_base_url: str = "http://host.docker.internal:11434"
    allowed_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    top_k: int = 45
    max_evidence_for_llm: int = 60
    cv_path: Path = Path("/app/data/cv_master.json")
    semantic_graph_path: Path = Path("/app/data/semantic_graph.json")
    sqlite_path: Path = Path("/app/storage/evidence.sqlite")
    history_db_path: Path = Path("/app/storage/history.sqlite")
    output_dir: Path = Path("/app/outputs")
    custom_themes_dir: Path = Path("/custom")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
