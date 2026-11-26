"""Central configuration. Every value can be overridden with a CODEGUARD_* env var or a .env file.

`.env` is looked up in the backend folder and in the repository root, so it works no matter which directory
uvicorn is started from (important on Windows where people often launch from the repo root).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODEGUARD_", env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore")

    # as_posix() keeps the URL valid on Windows (sqlite:///C:/Users/...)
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'codeguard.db').as_posix()}"
    artifacts_dir: Path = BACKEND_DIR / "ml" / "artifacts"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"   # served at / when it exists (after `npm run build`)
    log_level: str = "INFO"

    # limits / abuse protection
    max_file_bytes: int = 500_000
    max_batch_files: int = 100
    max_request_bytes: int = 25_000_000
    rate_limit_per_minute: int = 120   # analysis/training POSTs per client IP; 0 disables
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
    ai_weight_heuristic: float = 0.2   # used only when a trained model is present; alone it gets the full weight
    enable_codebert: bool = True
    enable_heuristic: bool = True
    enable_vuln_model: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
