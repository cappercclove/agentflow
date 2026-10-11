from datetime import datetime, timezone

from fastapi.testclient import TestClient

from models import SessionLocal, Execution


def _make_execution(**kwargs):
    db = SessionLocal()
    execution = Execution(
        workflow_id=1,
        status=kwargs.get("status", "completed"),
        started_at=kwargs.get("started_at", datetime.now(timezone.utc)),
        finished_at=kwargs.get("finished_at"),
        logs=kwargs.get("logs", []),
        output_data=kwargs.get("output_data", {}),
    )
    db.add(execution)
    db.commit()
    exec_id = execution.id
    db.close()
    return exec_id


# Deliberately not used as a context manager: entering it runs the app's lifespan,
# which installs POSIX signal handlers from a thread that is not the main one.
_client = TestClient


def test_snapshot_covers_a_run_that_already_ended():
    """A short graph can finish in the gap between the page's fetch and its socket."""
    import main

    finished = datetime.now(timezone.utc)
    exec_id = _make_execution(
        status="completed",
        finished_at=finished,
        logs=[{"node_id": "start", "status": "completed", "message": "完成: 开始", "timestamp": finished.isoformat()}],
        output_data={"output": "done"},
    )

    with _client(main.app).websocket_connect(f"/ws/execute/{exec_id}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["status"] == "completed"
        assert snapshot["logs"][0]["message"] == "完成: 开始"

        complete = ws.receive_json()
        assert complete["type"] == "complete"
        assert complete["status"] == "completed"
        # The closing frame used to carry output_data["error"] only, so a replayed
        # snapshot of a finished run always reported an empty result.
        assert complete["output"] == "done"


def test_snapshot_of_an_errored_run_carries_the_reason():
    import main

    exec_id = _make_execution(status="error", output_data={"error": "模型没有返回内容"})

    with _client(main.app).websocket_connect(f"/ws/execute/{exec_id}") as ws:
        assert ws.receive_json()["status"] == "error"
        complete = ws.receive_json()
        assert complete["type"] == "complete"
        assert complete["output"] == "模型没有返回内容"


def test_snapshot_of_a_live_run_leaves_the_stream_open():
    import main

    exec_id = _make_execution(status="running")

    with _client(main.app).websocket_connect(f"/ws/execute/{exec_id}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["status"] == "running"
        assert snapshot["logs"] == []

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_closing_an_outdated_tab_keeps_the_current_one_registered():
    """Reopening a live run replaces the socket; the old teardown must not drop it."""
    import main

    exec_id = _make_execution(status="running")
    url = f"/ws/execute/{exec_id}"
    client = _client(main.app)

    old_tab, new_tab = client.websocket_connect(url), None
    old_ws = old_tab.__enter__()
    try:
        old_ws.receive_json()
        new_tab = client.websocket_connect(url)
        new_tab.__enter__().receive_json()

        old_tab.__exit__(None, None, None)
        assert exec_id in main.active_connections

        new_tab.__exit__(None, None, None)
        new_tab = None
        assert exec_id not in main.active_connections
    finally:
        if new_tab is not None:
            new_tab.__exit__(None, None, None)
