from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FileIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1)
    language: Optional[str] = None

    @field_validator("code")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code is empty")
        return v


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


class JobOut(BaseModel):
    id: str
    status: str
    mode: str
    n_files: int
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: Optional[str] = None
