# CodeGuard — AI-assisted code integrity analyzer

Detects (1) AI-generated code, (2) plagiarism that survives renaming/reordering, (3) vulnerable code, in one dashboard.
Implements the 22ECM506 synopsis: FastAPI + SQLite backend, React + Monaco + Recharts frontend, XGBoost and CodeBERT
detectors, token-winnowing + AST-subtree plagiarism engine, rule + model vulnerability analysis.

```
codeguard/
├── backend/
│   ├── app/
│   │   ├── main.py · config.py · db.py · schemas.py        # app factory, env config, SQLAlchemy models, API schemas
│   │   ├── core/parsing.py                                  # lexer, normaliser, AST (ast + tree-sitter: py/java/c/cpp/js)
│   │   ├── core/features.py                                 # 45 stylometric features (comment ratio, naming, AST depth, entropy…)
│   │   ├── detectors/ai_detector.py                         # XGBoost + CodeBERT ensemble, block-level occlusion attribution
│   │   ├── detectors/plagiarism.py                          # k-gram winnowing + AST subtree matching, batch heatmap, clusters
│   │   ├── detectors/vulnerability.py                       # 30 CWE-tagged rules (line-level) + optional fine-tuned classifier
│   │   ├── services/analysis.py · services/jobs.py          # orchestration + thread-pool job queue
│   │   └── api/routes.py                                    # REST endpoints
│   ├── ml/                                                  # dataset building, training, evaluation (see below)
│   └── tests/                                               # 47 tests
├── frontend/                                                # Vite + React: Workspace, History, Evaluation
├── Makefile · .env.example
```

## Setup
```bash
make setup                 # backend venv + frontend deps         (Python 3.10+, Node 18+)
cp .env.example .env       # optional; every variable has a default
make backend               # http://localhost:8000  (docs at /docs)
make frontend              # http://localhost:5173  (proxies /api to :8000)
make test                  # 47 backend tests
```
Without trained models the app still runs: plagiarism and vulnerability analysis work immediately; the AI detector reports
`model_unavailable` until you train it (it never fabricates a score).

## Environment variables (all optional)
`CODEGUARD_DATABASE_URL`, `CODEGUARD_ARTIFACTS_DIR`, `CODEGUARD_CORS_ORIGINS`, `CODEGUARD_MAX_FILE_BYTES`,
`CODEGUARD_MAX_BATCH_FILES`, `CODEGUARD_JOB_WORKERS`, `CODEGUARD_WINNOW_K/W`, `CODEGUARD_AST_MIN_SUBTREE`,
`CODEGUARD_PLAGIARISM_THRESHOLD`, `CODEGUARD_ENABLE_CODEBERT`, `CODEGUARD_ENABLE_VULN_MODEL`.
Dataset generation only: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (and `OPENAI_BASE_URL`), `HF_TOKEN`.

## Training pipeline (run from `backend/`)
```bash
pip install -r requirements-ml.txt        # torch, transformers, datasets, LLM SDKs (use a Colab/Kaggle GPU for CodeBERT)
# 1. Dataset: same problem statements, human vs LLM solutions
python -m ml.build_dataset human-contests --out data/datasets/human.jsonl --max-problems 300 --per-problem 3
python -m ml.build_dataset generate --human data/datasets/human.jsonl --provider anthropic --model <model-id> --out data/datasets/ai_anthropic.jsonl
python -m ml.build_dataset merge --human data/datasets/human.jsonl --ai data/datasets/ai_anthropic.jsonl --out data/datasets/ai_dataset.jsonl
# 2. Detectors (splits are 70/15/15 BY PROBLEM, so no problem leaks across splits)
python -m ml.train_xgboost  --data data/datasets/ai_dataset.jsonl
python -m ml.train_codebert --task ai --data data/datasets/ai_dataset.jsonl
# 3. Plagiarism evaluation on obfuscated copies
python -m ml.eval_plagiarism --data data/datasets/ai_dataset.jsonl
# 4. Vulnerability classifier (stretch)
python -m ml.prepare_vuln --dataset devign --out data/datasets/vuln_dataset.jsonl
python -m ml.train_codebert --task vuln --data data/datasets/vuln_dataset.jsonl
```
Training writes models + `metrics.json` into `ml/artifacts/`; the API loads them at start-up (restart after training) and the
Evaluation page renders accuracy/precision/recall/F1/ROC-AUC/PR-AUC/FPR, confusion matrices, ROC curves, feature importance,
and breakdowns by code length and generating model. Decision thresholds are chosen on the validation split to cap the
false-positive rate (default 5%).

## API (`/api/v1`)
`POST /analyze` (sync) · `POST /jobs` (async, poll `GET /jobs/{id}`) · `POST /jobs/upload` (multipart) · `GET /analyses` ·
`DELETE /analyses/{id}` · `GET/DELETE /corpus` · `GET /metrics` · `GET /health`.
Uploaded code is **not stored** unless `options.persist=true`; submitted code is only parsed, never executed.

## Verification status (honest)
* Verified here: 47 passing tests (parsing in 5 languages, features, plagiarism under each obfuscation, vulnerability rules,
  API incl. jobs/privacy/validation, split leakage, metrics, XGBoost train→save→serve), live uvicorn smoke test, frontend production build.
* Plagiarism sanity benchmark (`--stdlib`, 100 real stdlib functions, my own obfuscators): recall 0.97–1.00, 0 false positives on random pairs. This is a
  mechanics check, not a thesis result — rerun on your dataset and report it with its limits.
* NOT verifiable in this sandbox: dataset downloads (Hugging Face, no network), LLM generation, CodeBERT training/inference (no torch/GPU), the Big-Vul column
  names in `prepare_vuln.py` (override with `--code-col/--label-col/--cwe-col`), and the UI in a real browser. Expect small fixes on first run of those.
* The XGBoost test uses synthetic stylistic data to prove the pipeline works; it says nothing about real-world accuracy.
* AI-code detection is probabilistic and weak on short or edited code. Treat results as decision support, never proof of misconduct.
