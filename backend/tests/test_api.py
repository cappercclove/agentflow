import asyncio
from datetime import datetime, timezone

from models import SessionLocal, Execution


async def test_create_workflow(client):
    res = await client.post("/api/workflows", json={
        "name": "Test Workflow",
        "description": "A test",
        "nodes": [],
        "edges": [],
    })
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Test Workflow"
    assert "id" in data


async def test_list_workflows(client):
    await client.post("/api/workflows", json={"name": "WF1"})
    await client.post("/api/workflows", json={"name": "WF2"})

    res = await client.get("/api/workflows")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2


async def test_get_workflow(client):
    create_res = await client.post("/api/workflows", json={"name": "Detail"})
    wf_id = create_res.json()["id"]

    res = await client.get(f"/api/workflows/{wf_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Detail"


async def test_get_workflow_not_found(client):
    res = await client.get("/api/workflows/9999")
    assert res.status_code == 404


async def test_update_workflow(client):
    create_res = await client.post("/api/workflows", json={"name": "Old"})
    wf_id = create_res.json()["id"]

    res = await client.put(f"/api/workflows/{wf_id}", json={"name": "New"})
    assert res.status_code == 200

    get_res = await client.get(f"/api/workflows/{wf_id}")
    assert get_res.json()["name"] == "New"


async def test_delete_workflow(client):
    create_res = await client.post("/api/workflows", json={"name": "ToDelete"})
    wf_id = create_res.json()["id"]

    res = await client.delete(f"/api/workflows/{wf_id}")
    assert res.status_code == 200

    get_res = await client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 404


async def test_stats(client):
    await client.post("/api/workflows", json={"name": "S1"})
    await client.post("/api/workflows", json={"name": "S2"})

    res = await client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["workflows"] == 2


async def test_node_types(client):
    res = await client.get("/api/node-types")
    assert res.status_code == 200
    data = res.json()
    assert "start" in data
    assert "end" in data
    assert "llm" in data
    assert data["condition"]["outputs"] == ["true", "false"]
    assert "loop" in data


async def test_validate_endpoint(client):
    res = await client.post("/api/workflows/validate", json={"nodes": [], "edges": []})
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert body["problems"]


async def test_execute_rejects_invalid_graph(client):
    created = await client.post("/api/workflows", json={"name": "Broken", "nodes": [
        {"id": "start", "type": "start", "config": {}},
    ], "edges": []})
    wf_id = created.json()["id"]

    res = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
    assert res.status_code == 400
    assert "结束" in res.json()["detail"]


async def test_execution_routes_only_the_taken_branch(client):
    nodes = [
        {"id": "start", "type": "start", "title": "开始", "config": {}},
        {"id": "cond", "type": "condition", "title": "判断", "config": {"condition": 'input contains "投诉"'}},
        {"id": "t", "type": "text", "title": "投诉", "config": {"operation": "concat", "texts": ["TRUE"]}},
        {"id": "f", "type": "text", "title": "咨询", "config": {"operation": "concat", "texts": ["FALSE"]}},
        {"id": "end", "type": "end", "title": "结束", "config": {}},
    ]
    edges = [
        {"source": "start", "target": "cond"},
        {"source": "cond", "target": "t", "sourcePort": "true"},
        {"source": "cond", "target": "f", "sourcePort": "false"},
        {"source": "t", "target": "end"},
        {"source": "f", "target": "end"},
    ]
    created = await client.post("/api/workflows", json={"name": "Branching", "nodes": nodes, "edges": edges})
    wf_id = created.json()["id"]

    started = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "我要投诉"}})
    exec_id = started.json()["execution_id"]

    for _ in range(20):
        await asyncio.sleep(0.05)
        finished = await client.get(f"/api/executions/{exec_id}")
        if finished.json()["status"] != "running":
            break

    execution = finished.json()
    assert execution["status"] == "completed"
    assert execution["output_data"]["output"] == "TRUE"
    assert set(execution["output_data"]["nodes"]) == {"start", "cond", "t", "end"}
    assert any("跳过分支" in log["message"] for log in execution["logs"])

    stats = (await client.get("/api/stats")).json()
    recent = stats["recent_executions"][0]
    assert recent["workflow_name"] == "Branching"
    assert recent["finished_at"]


async def test_loop_node_aggregates_items(client):
    nodes = [
        {"id": "start", "type": "start", "title": "开始", "config": {}},
        {"id": "sp", "type": "text", "title": "拆分", "config": {"operation": "split", "texts": ["{{input}}"], "separator": "\\n"}},
        {"id": "lp", "type": "loop", "title": "逐项", "config": {"source": "{{sp}}", "action": "collect", "join": " | "}},
        {"id": "end", "type": "end", "title": "结束", "config": {}},
    ]
    edges = [
        {"source": "start", "target": "sp"},
        {"source": "sp", "target": "lp"},
        {"source": "lp", "target": "end"},
    ]
    created = await client.post("/api/workflows", json={"name": "Loop", "nodes": nodes, "edges": edges})
    wf_id = created.json()["id"]

    started = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "苹果\n香蕉\n橙子"}})
    exec_id = started.json()["execution_id"]

    for _ in range(20):
        await asyncio.sleep(0.05)
        finished = await client.get(f"/api/executions/{exec_id}")
        if finished.json()["status"] != "running":
            break

    assert finished.json()["output_data"]["output"] == "苹果 | 香蕉 | 橙子"


async def test_cancel_stops_a_running_execution(client, monkeypatch):
    import main

    async def slow_node(node, context, send_log=None):
        await asyncio.sleep(30)
        return {"status": "success", "output": "never"}

    monkeypatch.setattr(main, "execute_node", slow_node)

    created = await client.post("/api/workflows", json={"name": "Slow", "nodes": [
        {"id": "start", "type": "start", "title": "开始", "config": {}},
        {"id": "end", "type": "end", "title": "结束", "config": {}},
    ], "edges": [{"source": "start", "target": "end"}]})
    wf_id = created.json()["id"]

    started = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
    exec_id = started.json()["execution_id"]
    await asyncio.sleep(0.05)

    res = await client.post(f"/api/executions/{exec_id}/cancel")
    assert res.status_code == 200

    for _ in range(20):
        await asyncio.sleep(0.05)
        finished = await client.get(f"/api/executions/{exec_id}")
        if finished.json()["status"] == "cancelled":
            break

    execution = finished.json()
    assert execution["status"] == "cancelled"
    assert execution["finished_at"]
    assert any(log["status"] == "cancelled" for log in execution["logs"])


async def test_cancel_on_a_finished_execution_is_a_no_op(client):
    db = SessionLocal()
    execution = Execution(
        workflow_id=1,
        status="completed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    exec_id = execution.id
    db.close()

    res = await client.post(f"/api/executions/{exec_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    missing = await client.post("/api/executions/999999/cancel")
    assert missing.status_code == 404


async def test_executions_still_running_after_a_restart_get_reaped(client):
    """No task owns the row, so cancelling has to write the status itself."""
    import main

    db = SessionLocal()
    execution = Execution(workflow_id=1, status="running", started_at=datetime.now(timezone.utc))
    db.add(execution)
    db.commit()
    exec_id = execution.id
    db.close()

    assert exec_id not in main.running_tasks

    res = await client.post(f"/api/executions/{exec_id}/cancel")
    assert res.json()["status"] == "cancelled"

    after = (await client.get(f"/api/executions/{exec_id}")).json()
    assert after["status"] == "cancelled"
    assert after["logs"][-1]["message"] == "执行已被手动停止"


async def test_deleting_executions_respects_running_ones(client):
    created = await client.post("/api/workflows", json={"name": "Del"})
    wf_id = created.json()["id"]

    db = SessionLocal()
    running = Execution(workflow_id=wf_id, status="running", started_at=datetime.now(timezone.utc))
    done = Execution(
        workflow_id=wf_id,
        status="completed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add_all([running, done])
    db.commit()
    running_id, done_id = running.id, done.id
    db.close()

    blocked = await client.delete(f"/api/executions/{running_id}")
    assert blocked.status_code == 409
    assert "停止" in blocked.json()["detail"]

    assert (await client.delete(f"/api/executions/{done_id}")).status_code == 200
    assert (await client.delete(f"/api/executions/{done_id}")).status_code == 404

    cleared = await client.delete("/api/executions")
    assert cleared.json()["deleted"] == 0

    remaining = (await client.get("/api/executions")).json()
    assert [e["id"] for e in remaining] == [running_id]


async def test_deleting_a_workflow_stops_its_live_runs(client):
    created = await client.post("/api/workflows", json={"name": "Cascade"})
    wf_id = created.json()["id"]

    db = SessionLocal()
    stale = Execution(workflow_id=wf_id, status="running", started_at=datetime.now(timezone.utc))
    db.add(stale)
    db.commit()
    exec_id = stale.id
    db.close()

    res = await client.delete(f"/api/workflows/{wf_id}")
    assert res.status_code == 200

    db = SessionLocal()
    assert db.query(Execution).filter(Execution.id == exec_id).first() is None
    db.close()


async def test_import_workflow(client):
    res = await client.post("/api/workflows/import", json={
        "name": "Imported",
        "description": "来自文件",
        "nodes": [
            {"id": "start", "type": "start", "x": 0, "y": 0},
            {"id": "end", "type": "end", "x": 200, "y": 0},
        ],
        "edges": [{"source": "start", "target": "end"}],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["node_count"] == 2

    stored = await client.get(f"/api/workflows/{body['id']}")
    assert stored.json()["name"] == "Imported"


async def test_import_rejects_broken_shape(client):
    res = await client.post("/api/workflows/import", json={
        "name": "Bad",
        "nodes": [{"id": "start", "type": "start"}, {"type": "end"}],
        "edges": [{"source": "start", "target": "ghost"}],
    })
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "缺少 id" in detail
    assert "不存在的节点" in detail


async def test_import_accepts_an_unfinished_draft(client):
    res = await client.post("/api/workflows/import", json={
        "name": "Draft",
        "nodes": [{"id": "a", "type": "llm", "config": {"prompt": "x"}}],
        "edges": [],
    })
    assert res.status_code == 200


async def test_validate_flags_nodes_without_id(client):
    res = await client.post("/api/workflows/validate", json={
        "nodes": [{"type": "start"}, {"type": "end"}],
        "edges": [],
    })
    body = res.json()
    assert body["valid"] is False
    assert "缺少 id" in "；".join(body["problems"])


async def test_validate_survives_junk_nodes(client):
    # Junk can already be sitting in the database, and validate runs before every
    # execute — this used to raise AttributeError and answer with a 500.
    res = await client.post("/api/workflows/validate", json={"nodes": ["start"], "edges": []})
    body = res.json()
    assert body["valid"] is False
    assert "不是对象" in body["problems"][0]


async def test_decompose_reports_model_failure(client, monkeypatch):
    import main

    def boom(_task):
        raise RuntimeError("连接超时")

    monkeypatch.setattr(main, "decompose_task", boom)
    res = await client.post("/api/decompose", json={"task": "写一份周报"})
    assert res.status_code == 502
    assert "连接超时" in res.json()["detail"]


async def test_unexpected_crash_still_tells_the_client_it_ended(client, monkeypatch):
    import main

    sent = []

    async def fake_complete(exec_id, status, output):
        sent.append(status)

    def boom(_value):
        raise RuntimeError("数据库写入失败")

    monkeypatch.setattr(main, "_send_complete", fake_complete)
    monkeypatch.setattr(main, "_truncate", boom)

    nodes = [
        {"id": "start", "type": "start", "config": {}},
        {"id": "t", "type": "text", "config": {"operation": "concat", "texts": ["{{input}}"]}},
        {"id": "end", "type": "end", "config": {}},
    ]
    edges = [{"source": "start", "target": "t"}, {"source": "t", "target": "end"}]
    created = await client.post("/api/workflows", json={"name": "Crash", "nodes": nodes, "edges": edges})
    started = await client.post(f"/api/workflows/{created.json()['id']}/execute", json={"input": {"input": "x"}})
    exec_id = started.json()["execution_id"]

    for _ in range(20):
        await asyncio.sleep(0.05)
        finished = await client.get(f"/api/executions/{exec_id}")
        if finished.json()["status"] != "running":
            break

    assert finished.json()["status"] == "error"
    assert "数据库写入失败" in finished.json()["output_data"]["error"]
    # Without the frame the detail page would sit at 运行中 forever.
    assert sent == ["error"]


async def test_service_worker_script_must_be_revalidated(client):
    # An HTTP-cached worker means a bumped CACHE_NAME never reaches the browser, so
    # every later frontend fix silently fails to ship.
    res = await client.get("/sw.js")
    assert res.status_code == 200
    assert "no-cache" in res.headers["cache-control"]
    assert "CACHE_NAME" in res.text
