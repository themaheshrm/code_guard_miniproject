import time

CODE_A = "import os\ndef f(u):\n    os.system('ls ' + u)\n    return len(u)\n"
CODE_B = "import os\ndef g(v):\n    os.system('ls ' + v)\n    return len(v)\n"


def body(**opts):
    return {"files": [{"name": "a.py", "code": CODE_A}, {"name": "b.py", "code": CODE_B}], "options": opts}


def test_health(client):
    j = client.get("/api/v1/health").json()
    assert j["status"] == "ok" and j["models"]["xgboost"]["available"] is False
    assert j["models"]["heuristic"]["available"] is True and j["rules"] >= 40


def test_sync_analysis_report_shape(client):
    r = client.post("/api/v1/analyze", json=body())
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["plagiarism"]["pairs"][0]["score"] > 0.8 and res["plagiarism"]["clusters"] == [["a.py", "b.py"]]
    f = res["files"][0]
    # no trained model in the temp artefacts dir -> the always-available heuristic engine answers, and says so
    assert f["ai"]["status"] == "ok" and f["ai"]["engine"] == "heuristic" and 0 <= f["ai"]["probability"] <= 1
    assert f["vulnerability"]["findings"] and f["verdict"]["disclaimer"]
    assert res["summary"]["n_files"] == 2 and res["summary"]["similar_pairs"] == 1
    assert f["warnings"]  # short snippet warning


def test_async_job_polling_and_listing(client):
    jid = client.post("/api/v1/jobs", json=body()).json()["id"]
    for _ in range(100):
        j = client.get(f"/api/v1/jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["status"] == "done" and j["result"]["files"]
    assert any(a["id"] == jid for a in client.get("/api/v1/analyses").json())


def test_upload_endpoint(client):
    r = client.post("/api/v1/jobs/upload", files=[("files", ("a.py", CODE_A)), ("files", ("b.py", CODE_B))], data={"options": '{"run_ai": false}'})
    assert r.status_code == 202
    for _ in range(50):
        j = client.get(f"/api/v1/jobs/{r.json()['id']}").json()
        if j["status"] != "queued" and j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "done" and j["result"]["files"][0]["ai"] is None


def test_upload_duplicate_filenames_disambiguated(client):
    r = client.post(
        "/api/v1/jobs/upload",
        files=[("files", ("file.py", CODE_A)), ("files", ("file.py", CODE_B))],
        data={"options": '{"run_ai": false}'},
    )
    assert r.status_code == 202
    for _ in range(50):
        j = client.get(f"/api/v1/jobs/{r.json()['id']}").json()
        if j["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert j["status"] == "done"
    names = [f["name"] for f in j["result"]["files"]]
    assert len(names) == 2 and "file.py" in names and "file_1.py" in names


def test_not_persisted_by_default_and_opt_in_corpus_comparison(client):
    client.post("/api/v1/analyze", json=body())
    assert client.get("/api/v1/corpus").json() == []  # privacy: nothing stored unless asked
    aid = client.post("/api/v1/analyze", json=body(persist=True)).json()["id"]
    assert len(client.get("/api/v1/corpus").json()) == 2
    new = {"files": [{"name": "new.py", "code": CODE_A.replace("f(", "h(")}], "options": {"compare_corpus": True}}
    res = client.post("/api/v1/analyze", json=new).json()["result"]
    assert res["plagiarism"]["corpus_matches"] and res["files"][0]["max_similarity"] > 0.5
    assert client.delete(f"/api/v1/analyses/{aid}").status_code == 204
    assert client.get("/api/v1/corpus").json() == []
    assert client.get(f"/api/v1/jobs/{aid}").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/v1/analyze", json={"files": []}).status_code == 422
    assert client.post("/api/v1/analyze", json={"files": [{"name": "a.py", "code": "   "}]}).status_code == 422
    dup = {"files": [{"name": "a.py", "code": "x=1"}, {"name": "a.py", "code": "y=2"}]}
    assert client.post("/api/v1/analyze", json=dup).status_code == 422
    big = {"files": [{"name": "a.py", "code": "x=1\n" * 200_000}]}
    assert client.post("/api/v1/analyze", json=big).status_code == 413
    assert client.get("/api/v1/jobs/nope").status_code == 404


def test_unparseable_code_still_returns_a_report(client):
    r = client.post("/api/v1/analyze", json={"files": [{"name": "bad.py", "code": "def f(:\n  eval(x)\n"}]})
    assert r.status_code == 200 and r.json()["result"]["files"][0]["vulnerability"]["findings"]


def test_metrics_endpoint_empty_without_training(client):
    assert client.get("/api/v1/metrics").json()["xgboost"] is None


def test_health_includes_parser_diagnostics(client):
    j = client.get("/api/v1/health").json()
    assert "parsers" in j
    for lang in ("python", "java", "c", "cpp", "javascript"):
        assert lang in j["parsers"]
        assert "available" in j["parsers"][lang]
        assert "module" in j["parsers"][lang]


def test_orphaned_jobs_recovered_on_startup(tmp_path):
    from app.db import Analysis, init_db, session
    from app.main import create_app
    from fastapi.testclient import TestClient

    db_path = tmp_path / "test_orphan.db"
    db_url = f"sqlite:///{db_path}"
    init_db(db_url)

    with session() as s:
        s.add(Analysis(id="job_running", mode="single", status="running", n_files=1))
        s.add(Analysis(id="job_queued", mode="single", status="queued", n_files=1))
        s.add(Analysis(id="job_done", mode="single", status="done", n_files=1, result={"ok": True}))
        s.add(Analysis(id="job_failed", mode="single", status="failed", error="Prior failure"))
        s.commit()

    with TestClient(create_app(db_url)) as new_client:
        r_run = new_client.get("/api/v1/jobs/job_running").json()
        assert r_run["status"] == "failed"
        assert "restarted" in r_run["error"].lower()

        r_que = new_client.get("/api/v1/jobs/job_queued").json()
        assert r_que["status"] == "failed"
        assert "restarted" in r_que["error"].lower()

        r_done = new_client.get("/api/v1/jobs/job_done").json()
        assert r_done["status"] == "done"
        assert r_done["result"] == {"ok": True}

        r_fail = new_client.get("/api/v1/jobs/job_failed").json()
        assert r_fail["status"] == "failed"
        assert r_fail["error"] == "Prior failure"



def _wait(client, url, key="status"):
    for _ in range(200):
        j = client.get(url).json()
        if j[key] not in ("queued", "running"):
            return j
        time.sleep(0.05)
    return j


def test_timestamps_are_utc_and_titles_default(client):
    j = client.post("/api/v1/analyze", json={**body(), "title": "  Lab 3  "}).json()
    assert j["created_at"].endswith("+00:00") and j["finished_at"] and j["title"] == "Lab 3"
    single = client.post("/api/v1/analyze", json={"files": [{"name": "x.py", "code": CODE_A}]}).json()
    assert single["title"] == "x.py" and single["summary"]["n_files"] == 1


def test_stats_rules_export_and_clear_history(client):
    client.post("/api/v1/analyze", json=body())
    st = client.get("/api/v1/stats").json()
    assert st["totals"]["analyses"] == 1 and st["totals"]["files"] == 2 and st["severity"]["high"] >= 2
    assert st["top_cwes"][0]["cwe"] == "CWE-78" and len(st["timeline"]) == 14 and st["timeline"][-1]["analyses"] == 1
    rules = client.get("/api/v1/rules?language=java").json()
    assert rules["count"] > 5 and all("java" in r["languages"] for r in rules["rules"])
    aid = st["recent"][0]["id"]
    ex = client.get(f"/api/v1/analyses/{aid}/export")
    assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"] and ex.json()["id"] == aid
    assert [a["id"] for a in client.get("/api/v1/analyses?q=Batch").json()] == [aid]
    assert client.delete("/api/v1/analyses").status_code == 204 and client.get("/api/v1/analyses").json() == []


def test_corpus_item_and_clear_keeps_corpus(client):
    client.post("/api/v1/analyze", json=body(persist=True))
    items = client.get("/api/v1/corpus").json()
    one = client.get(f"/api/v1/corpus/{items[0]['id']}").json()
    assert one["code"] in (CODE_A, CODE_B) and items[0]["lines"] >= 4
    client.delete("/api/v1/analyses")  # corpus-backed analyses survive unless include_corpus=true
    assert len(client.get("/api/v1/corpus").json()) == 2
    client.delete("/api/v1/analyses?include_corpus=true")
    assert client.get("/api/v1/corpus").json() == []


def test_cross_language_files_are_not_compared_and_crlf_normalised(client):
    files = [{"name": "a.py", "code": CODE_A.replace("\n", "\r\n")}, {"name": "a.js", "code": "function f(u){ return u.length }\n"}]
    res = client.post("/api/v1/analyze", json={"files": files}).json()["result"]
    assert res["plagiarism"]["pairs"] == [] and res["files"][0]["vulnerability"]["findings"][0]["line"] == 3
    assert client.post("/api/v1/analyze", json={"files": [{"name": "a.py", "code": "x=1", "language": "cobol"}]}).status_code == 422


def test_security_headers_and_upload_limits(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    big = "x = 1\n" * 100_000
    r = client.post("/api/v1/jobs/upload", files=[("files", ("big.py", big))])
    assert r.status_code == 413
    r = client.post("/api/v1/jobs/upload", files=[("files", ("bin.py", b"\x00\x01\x02abc"))])
    assert r.status_code == 422


def test_rate_limit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("CODEGUARD_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setenv("CODEGUARD_ARTIFACTS_DIR", str(tmp_path))
    get_settings.cache_clear()
    with TestClient(create_app("sqlite:///:memory:")) as c:
        codes = [c.post("/api/v1/analyze", json={"files": [{"name": "a.py", "code": "x = 1"}]}).status_code for _ in range(3)]
    get_settings.cache_clear()
    assert codes == [200, 200, 429]


def test_train_xgboost_from_ui_and_hot_reload(client, pair_rows):
    import json as _json

    data = "\n".join(_json.dumps(r) for r in pair_rows)
    assert client.post("/api/v1/train/xgboost", files={"dataset": ("d.jsonl", "not json")}).status_code == 422
    t = client.post("/api/v1/train/xgboost", files={"dataset": ("d.jsonl", data)}).json()
    t = _wait(client, f"/api/v1/tasks/{t['id']}")
    assert t["status"] == "done", t
    assert client.get("/api/v1/health").json()["models"]["xgboost"]["available"] is True
    assert client.get("/api/v1/metrics").json()["xgboost"]["test"]
    f = client.post("/api/v1/analyze", json=body()).json()["result"]["files"][0]
    assert f["ai"]["engine"] == "ensemble" and set(f["ai"]["models"]) == {"xgboost", "heuristic"}


def test_plagiarism_benchmark_task(client):
    t = client.post("/api/v1/benchmark/plagiarism?n=20").json()
    t = _wait(client, f"/api/v1/tasks/{t['id']}")
    assert t["status"] == "done" and t["result"]["n_programs"] >= 10
    assert client.get("/api/v1/metrics").json()["plagiarism"]["sweep"]


def test_old_database_is_migrated(tmp_path):
    import sqlite3

    from app.db import init_db

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE analyses (id VARCHAR(32) PRIMARY KEY, created_at DATETIME, mode VARCHAR(16), status VARCHAR(16), "
                "n_files INTEGER, persist BOOLEAN, result JSON, error TEXT)")
    con.commit(); con.close()
    init_db(f"sqlite:///{db}")
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(analyses)")}
    assert {"title", "summary", "finished_at"} <= cols
