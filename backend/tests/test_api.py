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
