import asyncio


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
