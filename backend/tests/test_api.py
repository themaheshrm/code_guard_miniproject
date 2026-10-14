import time

CODE_A = "import os\ndef f(u):\n    os.system('ls ' + u)\n    return len(u)\n"
CODE_B = "import os\ndef g(v):\n    os.system('ls ' + v)\n    return len(v)\n"


def body(**opts):
    return {"files": [{"name": "a.py", "code": CODE_A}, {"name": "b.py", "code": CODE_B}], "options": opts}


def test_health(client):
    j = client.get("/api/v1/health").json()
    assert j["status"] == "ok" and j["models"]["xgboost"]["available"] is False


def test_sync_analysis_report_shape(client):
    r = client.post("/api/v1/analyze", json=body())
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["plagiarism"]["pairs"][0]["score"] > 0.8 and res["plagiarism"]["clusters"] == [["a.py", "b.py"]]
    f = res["files"][0]
    assert f["ai"]["status"] == "model_unavailable" and f["vulnerability"]["findings"] and f["verdict"]["disclaimer"]
    assert f["warnings"]  # short snippet warning


def test_async_job_polling_and_listing(client):
    jid = client.post("/api/v1/jobs", json=body()).json()["id"]
    for _ in range(50):
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
