from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .core.parsing import SUPPORTED_LANGUAGES


class FileIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1)
    language: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.replace("\\", "/").split("/")[-1].strip()  # never keep client-side directory paths
        if not v or v in (".", ".."):
            raise ValueError("invalid file name")
        return v

    @field_validator("code")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code is empty")
        return v.replace("\r\n", "\n")  # Windows line endings must not shift line numbers

    @field_validator("language")
    @classmethod
    def _known_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "" or v.lower() == "auto":
            return None
        if v.lower() not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language '{v}' (supported: {', '.join(SUPPORTED_LANGUAGES)})")
        return v.lower()


class Options(BaseModel):
    run_ai: bool = True
    run_plagiarism: bool = True
    run_vulnerability: bool = True
    compare_corpus: bool = False   # also compare against previously persisted submissions
    persist: bool = False          # store code + fingerprints (opt-in)
    explain: bool = True


class AnalyzeRequest(BaseModel):
    files: list[FileIn] = Field(min_length=1)
    options: Options = Options()
    title: Optional[str] = Field(default=None, max_length=200)


class JobOut(BaseModel):
    id: str
    status: str
    mode: str
    n_files: int
    title: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict] = None
    summary: Optional[dict] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
