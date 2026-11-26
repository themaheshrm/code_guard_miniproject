# CodeGuard: AI-assisted code integrity analyzer

CodeGuard runs one analysis that answers three questions about source code:

1. **Was it AI-generated?** It uses an ensemble of an explainable stylometric heuristic, an XGBoost model over 45 features and an optional fine-tuned CodeBERT. It also attributes the score to individual blocks of code.
2. **Was it copied?** It uses k-gram winnowing on normalized tokens and AST-subtree matching. Matches survive identifier renaming, statement reordering, comment edits and dead-code insertion. The output includes a batch heatmap, clusters, a side-by-side compare view and an opt-in reference corpus.
3. **Is it insecure?** It applies 50 CWE- and OWASP-tagged static rules, each with a concrete fix. An optional fine-tuned classifier can add function-level checks.

It supports Python, Java, C, C++ and JavaScript. The stack is FastAPI, SQLite, React 18, Monaco and Recharts.

```
code_guard_miniproject/
├── setup.bat · start.bat · dev.bat · test.bat      # one-click Windows scripts
├── backend/
│   ├── app/
│   │   ├── main.py            # app factory, security headers, rate limit, serves the built UI
│   │   ├── config.py · db.py · schemas.py
│   │   ├── core/parsing.py    # lexer, normaliser, AST (stdlib ast + tree-sitter)
│   │   ├── core/features.py   # 45 stylometric features
│   │   ├── detectors/ai_detector.py    # heuristic + XGBoost + CodeBERT ensemble, occlusion attribution
│   │   ├── detectors/plagiarism.py     # winnowing + AST subtree matching, clusters
│   │   ├── detectors/vulnerability.py  # comment-aware rule engine (+ optional model)
│   │   ├── services/analysis.py · services/jobs.py   # orchestration, job queue, background tasks
│   │   └── api/routes.py      # REST API (/api/v1)
│   ├── ml/                    # dataset building, training, evaluation scripts
│   └── tests/                 # 67 pytest tests
└── frontend/                  # Vite + React: Dashboard, Analyze, Reports, Models, Rules
```

---

## Windows setup (exact steps)

### 1. Install the prerequisites (once)

| Tool | Version | Where |
|---|---|---|
| Python | 3.10 – 3.13 (64-bit) | https://www.python.org/downloads/. In the installer, tick **"Add python.exe to PATH"**. |
| Node.js | 18 LTS or newer | https://nodejs.org/ (the LTS installer adds `npm` to PATH). |
| Git | any | https://git-scm.com/download/win (only needed to clone). |

Open a **new** Command Prompt or PowerShell window and check the versions:

```bat
python --version
node --version
npm --version
```

### 2. Get the code

```bat
git clone https://github.com/themaheshrm/code_guard_miniproject.git
cd code_guard_miniproject
```

### 3. One-click setup

Double-click `setup.bat`, or run it from the project folder:

```bat
setup.bat
```

This script:

- creates `backend\.venv`;
- installs the Python packages (FastAPI, XGBoost, tree-sitter and the rest; no GPU or PyTorch needed);
- runs `npm install`;
- builds the UI into `frontend\dist`;
- copies `.env.example` to `.env`.

The first run takes 2–5 minutes.

### 4. Run

```bat
start.bat
```

Your browser opens **http://localhost:8000**. One process serves both the API and the UI. Interactive API docs are at http://localhost:8000/docs. Press `Ctrl+C` in the window to stop the server. To use another port, run `start.bat 8080`.

### 5. Development mode (optional, hot reload)

```bat
dev.bat
```

This opens two windows: the API on :8000 with auto-reload, and the Vite UI on **http://localhost:5173**, which proxies `/api` to :8000.

### 6. Tests

```bat
test.bat
```

This runs all backend tests and a production build of the frontend.

### Manual commands (if you prefer typing them; PowerShell)

```powershell
# backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements-dev.txt
python -m pytest                       # 67 tests
uvicorn app.main:app --port 8000       # API (+ UI if frontend\dist exists)

# frontend (second terminal)
cd frontend
npm install
npm run dev                            # http://localhost:5173  (or: npm run build, then use :8000)
```

In `cmd.exe`, activate with `backend\.venv\Scripts\activate.bat` instead.

### Troubleshooting on Windows

| Symptom | Fix |
|---|---|
| `'python' is not recognized` | Re-run the Python installer, tick *Add to PATH*, and open a new terminal. You can also use `py -3` instead of `python`. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use `start.bat`, which needs no activation. |
| `pip` fails building `tree-sitter` | Upgrade pip (`python -m pip install -U pip`). Wheels exist for Python 3.10–3.13 x64; on other versions install *Microsoft C++ Build Tools*. |
| Port 8000 already in use | `start.bat 8080`, or find the process: `netstat -ano \| findstr :8000`. |
| UI says **API offline** | Make sure the backend window is running and shows `Uvicorn running on http://127.0.0.1:8000`. |
| Page is blank at :8000 | The UI was not built. Run `cd frontend && npm run build` (or `setup.bat` again). |

macOS/Linux users can run `make setup`, then `make start` (or `make backend` + `make frontend`), and `make test`.

---

## Using the app

| Page | What you can do |
|---|---|
| **Dashboard** | KPIs, 14-day activity, verdict mix, findings by severity, top CWEs, languages, recent reports and engine status. *Try the demo* loads sample submissions. |
| **Analyze** | Monaco editor with multiple files, upload of files or a whole folder, drag-and-drop, rename (the extension sets the language), analysis toggles, and **Ctrl+Enter** to run. The report panel has Overview (score rings and verdict), AI detection (signal chart and block attribution), Similarity (heatmap, token/AST breakdown and a **side-by-side Compare** view) and Security (findings by severity with CWE links, OWASP category and fix). Gutter highlights in the editor can be toggled per layer. |
| **Reports** | Search and filter past analyses; open, export JSON, print to PDF, or delete them. The *Saved corpus* tab lets you view, reopen or remove stored submissions. |
| **Models** | Engine status, **train XGBoost from a JSONL upload** (hot-loaded, no restart), **run the plagiarism benchmark**, and view ROC curves, confusion matrices, feature importance and threshold sweeps. |
| **Rules** | The full vulnerability rule catalogue, filterable by language and severity. |

Light and dark themes are available (the sun/moon button), and the layout adapts down to phone width. Workspace files persist in the browser across reloads.

### How the AI score works without training

When no trained model is present, the **heuristic stylometry** engine gives an explainable estimate from 15 signals. These include comment and docstring density, type-hint coverage, identifier length, single-letter names, spacing and blank-line uniformity, naming consistency, main guards and defensive error handling. Its decision threshold is 60%, and every result is labelled with the engine that produced it.

The heuristic has a known limit: polished, heavily documented human code (for example library code) also scores high. In a check against 120 Python standard-library functions, most scored above 50%. For a data-driven score, train XGBoost on a real labelled dataset (Models page, or the scripts below). The heuristic then drops to a 20% ensemble weight.

---

## Training pipeline (optional; run from `backend/` with the venv active)

```bash
pip install -r requirements-ml.txt        # torch, transformers, datasets, LLM SDKs (use a GPU box for CodeBERT)
# 1. Dataset: same problem statements, human vs LLM solutions
python -m ml.build_dataset human-contests --out data/datasets/human.jsonl --max-problems 300 --per-problem 3
python -m ml.build_dataset generate --human data/datasets/human.jsonl --provider anthropic --model <model-id> --out data/datasets/ai_anthropic.jsonl
python -m ml.build_dataset merge --human data/datasets/human.jsonl --ai data/datasets/ai_anthropic.jsonl --out data/datasets/ai_dataset.jsonl
# 2. Detectors (70/15/15 split BY PROBLEM, so no problem leaks across splits)
python -m ml.train_xgboost  --data data/datasets/ai_dataset.jsonl          # or upload the .jsonl on the Models page
python -m ml.train_codebert --task ai --data data/datasets/ai_dataset.jsonl
# 3. Plagiarism evaluation
python -m ml.eval_plagiarism --stdlib                                     # or "Run benchmark" on the Models page
# 4. Vulnerability classifier (optional)
python -m ml.prepare_vuln --dataset devign --out data/datasets/vuln_dataset.jsonl
python -m ml.train_codebert --task vuln --data data/datasets/vuln_dataset.jsonl
```

Each dataset row is one JSON object: `{"code": "...", "label": 0|1, "language": "python", "group_id": "problem-17", "generator": "gpt-4o"}`. Artifacts go to `backend/ml/artifacts/`. Use **Reload models** on the Models page, or restart the server, to pick them up. Decision thresholds are chosen on the validation split so that the false-positive rate stays at or below the chosen cap (5% by default).

## API (`/api/v1`, full schema at `/docs`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Engine status, parsers, counts, limits |
| POST | `/analyze` | Synchronous analysis `{files:[{name,code,language?}], options, title?}` |
| POST | `/jobs` · `/jobs/upload` | Asynchronous analysis (JSON or multipart); poll `GET /jobs/{id}` |
| GET | `/analyses?q=&status=&limit=&offset=` | History |
| GET | `/analyses/{id}/export` | Download the report as JSON |
| DELETE | `/analyses/{id}` · `/analyses?include_corpus=` | Delete one report or clear the history |
| GET | `/stats?days=14` | Dashboard aggregates |
| GET | `/rules?language=` | Rule catalogue |
| GET / DELETE | `/corpus` · `/corpus/{id}` | Saved reference corpus |
| GET | `/metrics` | Training and evaluation artifacts |
| POST | `/train/xgboost` · `/benchmark/plagiarism` · `/models/reload` | Background training, benchmark and hot reload; poll `GET /tasks/{id}` |

## Security and privacy

- Submitted code is **only parsed, never executed**.
- Source code is stored only when **Save to corpus** is on. Reports keep scores plus short snippets of flagged lines; delete them from Reports at any time.
- The server enforces per-file (500 KB), per-batch (100 files) and per-request (25 MB) limits, rejects binary uploads, and rate-limits analysis and training calls (120/min per IP).
- Responses carry security headers (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`). The UI ships with a strict Content-Security-Policy, and Monaco is bundled locally, so no CDN is needed and the editor works offline.
- File names are stripped of paths. Windows line endings are normalized, so line numbers match. Unhandled errors return a generic message; details are logged server-side.

Every limit is configurable through `CODEGUARD_*` variables (see `.env.example`). The `.env` file can live in the repository root or in `backend/`.

## Verification status

- **67 backend tests pass.** They cover:
  - parsing in 5 languages and the stylometric features;
  - plagiarism under each obfuscation;
  - vulnerability rules, including regression tests for earlier false positives (`model.eval()`, `regex.exec()`, docstrings, block comments, `shell=True` in unrelated calls);
  - the heuristic AI engine;
  - XGBoost train → save → hot-load → serve, both from the CLI and the API;
  - jobs, uploads, limits, rate limiting, security headers, stats, export, history clearing, DB migration and UTC timestamps.
- **End-to-end browser test (headless Chromium):** every page; the demo analyses; the AI, Similarity and Security tabs; Compare; the report page; the benchmark; the light theme; and a 390 px phone layout. There were zero console errors under the production CSP. Dev mode (Vite proxy), file upload, rename and Ctrl+Enter were also exercised.
- **Plagiarism benchmark (100 real stdlib functions):** recall of 1.00 for rename, reorder and comment edits, 0.97 for dead code and 0.95 for all combined; 0.3% false positives on unrelated pairs. This is a mechanics check, not a thesis result; rerun it on your own dataset.
- **Not verified here:** dataset downloads and LLM generation (network and API keys), CodeBERT training and inference (needs torch/GPU), and a real Windows machine. The `.bat` scripts use only standard `cmd` features, but they were written on Linux.
- **The XGBoost tests use synthetic data** to prove the pipeline works; they say nothing about real-world accuracy. AI-code detection is probabilistic and weak on short or edited code. **Treat results as decision support, never as proof of misconduct.**
