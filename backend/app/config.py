"""Central configuration. Every value can be overridden with a CODEGUARD_* env var."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODEGUARD_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'codeguard.db'}"
    artifacts_dir: Path = BACKEND_DIR / "ml" / "artifacts"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    max_file_bytes: int = 500_000
    max_batch_files: int = 100
    job_workers: int = 2

    # plagiarism engine
    winnow_k: int = 8
    winnow_w: int = 5
    ast_min_subtree: int = 6
    plagiarism_threshold: float = 0.5
    token_weight: float = 0.5  # combined = w*token + (1-w)*ast

    # AI detector ensemble
    ai_weight_xgb: float = 0.4
    ai_weight_codebert: float = 0.6
    enable_codebert: bool = True
    enable_vuln_model: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
