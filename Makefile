.PHONY: setup backend frontend start test build eval-plag
setup:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
	cd frontend && npm install && npm run build
backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000
frontend:
	cd frontend && npm run dev
start: build
	cd backend && . .venv/bin/activate && uvicorn app.main:app --port 8000
test:
	cd backend && . .venv/bin/activate && python -m pytest
build:
	cd frontend && npm run build
eval-plag:
	cd backend && . .venv/bin/activate && python -m ml.eval_plagiarism --stdlib
