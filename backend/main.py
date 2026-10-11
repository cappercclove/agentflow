import os
import json
import time
import asyncio
import logging
import signal
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import engine, SessionLocal, Workflow, Execution
from workflow_engine import execute_node, validate_workflow, validate_graph_shape
from llm_client import decompose_task, call_llm
from node_types import NODE_TYPES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

active_connections: dict[int, WebSocket] = {}
pending_tasks: set = set()
running_tasks: dict[int, asyncio.Task] = {}
shutdown_event = asyncio.Event()

FINISHED_STATUSES = ("completed", "error", "cancelled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    if os.name == "posix":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: shutdown_event.set())
            except (ValueError, NotImplementedError):
                # Only the main thread may own signal handlers, so an app started
                # inside another thread (or a test portal) simply loses that hook.
                logger.info("Signal handlers unavailable on this loop")
                break
    logger.info("Server started")
    yield
    shutdown_event.set()
    for task in list(pending_tasks):
        task.cancel()
    for ws in list(active_connections.values()):
        try:
            await ws.close()
        except Exception:
            pass
    logger.info("Server shut down gracefully")

app = FastAPI(title="AI Agent Workflow Platform", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info("%s %s %d %.3fs", request.method, request.url.path, response.status_code, duration)
    return response


@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/sw.js")
async def serve_service_worker():
    sw_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "sw.js")
    with open(sw_path, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(
        content=content,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend")), name="static")


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    nodes: list = []
    edges: list = []


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list | None = None
    edges: list | None = None


class ExecuteRequest(BaseModel):
    input: dict = {}


class DecomposeRequest(BaseModel):
    task: str


class NodeExecuteRequest(BaseModel):
    node: dict
    context: dict = {}


class ValidateRequest(BaseModel):
    nodes: list = []
    edges: list = []


class WorkflowImport(BaseModel):
    name: str = "导入的工作流"
    description: str = ""
    nodes: list = []
    edges: list = []


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))


@app.get("/api/node-types")
async def get_node_types():
    return NODE_TYPES


@app.post("/api/workflows")
async def create_workflow(data: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = Workflow(
        name=data.name,
        description=data.description,
        nodes=data.nodes,
        edges=data.edges,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    logger.info("Workflow created: id=%s name=%s", workflow.id, workflow.name)
    return {"id": workflow.id, "name": workflow.name, "created_at": workflow.created_at.isoformat()}


@app.get("/api/workflows")
async def list_workflows(db: Session = Depends(get_db)):
    workflows = db.query(Workflow).order_by(Workflow.updated_at.desc()).all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "nodes": w.nodes,
            "edges": w.edges,
            "created_at": w.created_at.isoformat(),
            "updated_at": w.updated_at.isoformat(),
        }
        for w in workflows
    ]


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: int, data: WorkflowUpdate, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.nodes is not None:
        workflow.nodes = data.nodes
    if data.edges is not None:
        workflow.edges = data.edges
    workflow.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Workflow updated: id=%s", workflow_id)
    return {"message": "Workflow updated"}


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # The cascade below deletes the Execution rows; a run still writing to them would
    # otherwise keep committing into rows that no longer exist.
    _cancel_executions(db, workflow_id=workflow_id)
    db.delete(workflow)
    db.commit()
    logger.info("Workflow deleted: id=%s", workflow_id)
    return {"message": "Workflow deleted"}


@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: int, data: ExecuteRequest, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    problems = validate_workflow(workflow.nodes or [], workflow.edges or [])
    if problems:
        logger.warning("Workflow rejected before execution: workflow_id=%s problems=%s", workflow_id, problems)
        raise HTTPException(status_code=400, detail="；".join(problems))

    execution = Execution(
        workflow_id=workflow_id,
        status="running",
        input_data=data.input,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    exec_id = execution.id

    nodes_snapshot = workflow.nodes
    edges_snapshot = workflow.edges

    logger.info("Workflow execution started: workflow_id=%s execution_id=%s", workflow_id, exec_id)
    task = asyncio.create_task(_run_workflow(exec_id, workflow_id, nodes_snapshot, edges_snapshot, data.input))
    pending_tasks.add(task)
    running_tasks[exec_id] = task
    task.add_done_callback(pending_tasks.discard)
    task.add_done_callback(lambda _t: running_tasks.pop(exec_id, None))

    return {"execution_id": exec_id, "status": "running"}


@app.get("/api/executions/{execution_id}")
async def get_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {
        "id": execution.id,
        "workflow_id": execution.workflow_id,
        "status": execution.status,
        "input_data": execution.input_data,
        "output_data": execution.output_data,
        "logs": execution.logs,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
    }


@app.get("/api/executions")
async def list_executions(workflow_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Execution)
    if workflow_id:
        query = query.filter(Execution.workflow_id == workflow_id)
    executions = query.order_by(Execution.created_at.desc()).limit(50).all()
    return [
        {
            "id": e.id,
            "workflow_id": e.workflow_id,
            "status": e.status,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "finished_at": e.finished_at.isoformat() if e.finished_at else None,
        }
        for e in executions
    ]


@app.post("/api/workflows/import")
async def import_workflow(data: WorkflowImport, db: Session = Depends(get_db)):
    problems = validate_graph_shape(data.nodes, data.edges)
    if problems:
        raise HTTPException(status_code=400, detail="；".join(problems))

    workflow = Workflow(
        name=data.name or "导入的工作流",
        description=data.description,
        nodes=data.nodes,
        edges=data.edges,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    logger.info("Workflow imported: id=%s name=%s nodes=%s", workflow.id, workflow.name, len(workflow.nodes))
    return {"id": workflow.id, "name": workflow.name, "node_count": len(workflow.nodes)}


def _append_log(execution: Execution, status: str, message: str):
    logs = list(execution.logs or [])
    logs.append({
        "node_id": "-",
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    execution.logs = logs


def _mark_cancelled(execution: Execution):
    _append_log(execution, "cancelled", "执行已被手动停止")
    execution.status = "cancelled"
    execution.finished_at = datetime.now(timezone.utc)


def _cancel_executions(db: Session, execution_id: int = None, workflow_id: int = None) -> int:
    """Stop unfinished runs; returns how many are still executing in this process."""
    query = db.query(Execution).filter(Execution.status.notin_(FINISHED_STATUSES))
    if execution_id is not None:
        query = query.filter(Execution.id == execution_id)
    if workflow_id is not None:
        query = query.filter(Execution.workflow_id == workflow_id)

    live = 0
    touched = 0
    for execution in query.all():
        touched += 1
        task = running_tasks.get(execution.id)
        if task:
            live += 1
            task.cancel()
        else:
            # Nothing is running in this process: the row is a leftover from a restart.
            _mark_cancelled(execution)
            active_connections.pop(execution.id, None)
    if touched:
        db.commit()
    return live


@app.post("/api/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.status in FINISHED_STATUSES:
        return {"message": "already_finished", "status": execution.status}

    live = _cancel_executions(db, execution_id=execution_id)
    logger.info("Execution cancellation requested: execution_id=%s live=%s", execution_id, live)
    return {"message": "cancelled", "status": "stopping" if live else "cancelled"}


@app.delete("/api/executions/{execution_id}")
async def delete_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if execution.status not in FINISHED_STATUSES:
        raise HTTPException(status_code=409, detail="运行中的执行不能删除，请先停止")

    db.delete(execution)
    db.commit()
    active_connections.pop(execution_id, None)
    logger.info("Execution deleted: id=%s", execution_id)
    return {"message": "Execution deleted"}


@app.delete("/api/executions")
async def clear_executions(db: Session = Depends(get_db)):
    """Drop finished runs only — a live run's logs still belong to somebody's screen."""
    deleted = (
        db.query(Execution)
        .filter(Execution.status.in_(FINISHED_STATUSES))
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("Executions cleared: deleted=%s", deleted)
    return {"deleted": deleted}


@app.post("/api/decompose")
async def decompose(data: DecomposeRequest):
    logger.info("Task decomposition requested: task=%s", data.task[:100])
    loop = asyncio.get_running_loop()
    try:
        # decompose_task blocks on an HTTP call to the model; on the event loop it
        # would freeze every other request, including the WebSocket log streams.
        steps = await loop.run_in_executor(None, decompose_task, data.task)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"任务分解失败：{e}")
    return {"steps": steps}


@app.post("/api/nodes/execute")
async def execute_single_node(data: NodeExecuteRequest):
    result = await execute_node(data.node, data.context)
    return result


@app.post("/api/workflows/validate")
async def validate_workflow_graph(data: ValidateRequest):
    problems = validate_workflow(data.nodes, data.edges)
    return {"valid": not problems, "problems": problems}


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    workflow_count = db.query(Workflow).count()
    execution_count = db.query(Execution).count()
    success_count = db.query(Execution).filter(Execution.status == "completed").count()
    error_count = db.query(Execution).filter(Execution.status == "error").count()
    running_count = db.query(Execution).filter(Execution.status == "running").count()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(Execution).filter(Execution.created_at >= today_start).count()

    recent_workflows = (
        db.query(Workflow)
        .order_by(Workflow.updated_at.desc())
        .limit(5)
        .all()
    )

    recent_executions = (
        db.query(Execution)
        .order_by(Execution.created_at.desc())
        .limit(5)
        .all()
    )

    wf_names = {
        w.id: w.name
        for w in db.query(Workflow)
        .filter(Workflow.id.in_({e.workflow_id for e in recent_executions}))
        .all()
    }

    return {
        "workflows": workflow_count,
        "executions": execution_count,
        "today_executions": today_count,
        "success_rate": round(success_count / execution_count * 100, 1) if execution_count > 0 else 0,
        "success_count": success_count,
        "error_count": error_count,
        "running_count": running_count,
        "recent_workflows": [
            {
                "id": w.id,
                "name": w.name,
                "node_count": len(w.nodes) if w.nodes else 0,
                "updated_at": w.updated_at.isoformat(),
            }
            for w in recent_workflows
        ],
        "recent_executions": [
            {
                "id": e.id,
                "workflow_id": e.workflow_id,
                "workflow_name": wf_names.get(e.workflow_id),
                "status": e.status,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
            }
            for e in recent_executions
        ],
    }


@app.websocket("/ws/execute/{execution_id}")
async def websocket_execute(websocket: WebSocket, execution_id: int):
    await websocket.accept()
    active_connections[execution_id] = websocket
    try:
        await _send_state_snapshot(websocket, execution_id)
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        # Anything that breaks this loop other than a clean disconnect used to leave
        # a dead socket registered, and every later send to it failed silently — the
        # run then looked as if it had produced no logs at all.
        if active_connections.get(execution_id) is websocket:
            active_connections.pop(execution_id, None)


async def _send_state_snapshot(websocket: WebSocket, execution_id: int):
    """Hand the client what already happened, before listening for what comes next.

    The page fetches the run, sees it still going, then opens this socket. A short
    graph finishes inside that gap, so every log and the closing frame were already
    sent to nobody: the client would sit at 运行中 with an open socket that never
    closes and therefore never falls back to polling.
    """
    db = SessionLocal()
    try:
        execution = db.query(Execution).filter(Execution.id == execution_id).first()
        if not execution:
            return
        await websocket.send_json({
            "type": "snapshot",
            "status": execution.status,
            "logs": execution.logs or [],
        })
        if execution.status not in ("running", "pending"):
            await websocket.send_json({
                "type": "complete",
                "status": execution.status,
                "output": _truncate(str((execution.output_data or {}).get("error", ""))),
            })
    except Exception:
        # A snapshot is only a head start; the live stream still has the run.
        logger.exception("Could not snapshot execution %s", execution_id)
    finally:
        db.close()


def _outgoing_edges(edges: list, branch: str | None) -> list:
    """Pick the edges that should actually run.

    A condition node routes by port: edges tagged sourcePort == branch win.
    Untagged edges (drawn before ports existed) keep the legacy behaviour of
    taking the first one, so a saved workflow never runs both branches.
    """
    if branch is None:
        return edges
    tagged = [e for e in edges if e.get("sourcePort") == branch]
    if tagged:
        return tagged
    return [e for e in edges if not e.get("sourcePort")][:1]


def _skipped_edges(edges: list, branch: str | None) -> list:
    taken = {id(e) for e in _outgoing_edges(edges, branch)}
    return [e for e in edges if id(e) not in taken]


def _truncate(value, limit: int = 4000):
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"…（已截断，共 {len(value)} 字）"
    return value


async def _send_complete(exec_id: int, status: str, output: str):
    ws = active_connections.get(exec_id)
    if not ws:
        return
    try:
        await ws.send_json({"type": "complete", "status": status, "output": output})
    except Exception:
        pass


async def _run_workflow(exec_id: int, workflow_id: int, nodes: list, edges: list, input_data: dict):
    db = SessionLocal()
    try:
        execution = db.query(Execution).filter(Execution.id == exec_id).first()
        if not execution:
            return

        execution.status = "running"
        db.commit()

        context = dict(input_data)
        logs = []
        node_map = {n.get("id"): n for n in nodes if n.get("id")}
        edge_map = {}
        for edge in edges:
            source = edge.get("source")
            if source not in edge_map:
                edge_map[source] = []
            edge_map[source].append(edge)

        start_nodes = [n for n in nodes if n.get("type") == "start"]
        if not start_nodes:
            start_nodes = nodes[:1]

        async def send_log(node_id, status, message):
            log_entry = {"node_id": node_id, "status": status, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()}
            logs.append(log_entry)
            execution.logs = logs
            db.commit()

            ws = active_connections.get(exec_id)
            if ws:
                try:
                    await ws.send_json({"type": "log", "data": log_entry})
                except Exception:
                    pass

        current_nodes = start_nodes
        visited = set()
        final_output = ""
        node_outputs = {}

        while current_nodes:
            next_nodes = []
            for node in current_nodes:
                node_id = node.get("id")
                if node_id in visited:
                    continue
                visited.add(node_id)

                result = await execute_node(node, context, send_log)

                if result["status"] == "error":
                    execution.status = "error"
                    execution.output_data = {"error": result["output"], "nodes": node_outputs}
                    execution.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    await _send_complete(exec_id, "error", result["output"])
                    return

                context[node_id] = result["output"]
                node_outputs[node_id] = _truncate(result["output"])
                if node.get("type") != "end":
                    final_output = result["output"]
                    context["final_output"] = final_output

                outgoing = edge_map.get(node_id, [])
                for edge in _outgoing_edges(outgoing, result.get("branch")):
                    target_id = edge.get("target")
                    if target_id and target_id in node_map and target_id not in visited:
                        next_nodes.append(node_map[target_id])

                for edge in _skipped_edges(outgoing, result.get("branch")):
                    skipped = node_map.get(edge.get("target"))
                    if skipped:
                        await send_log(node_id, "skipped", f"跳过分支: {skipped.get('title') or skipped['id']}")

            current_nodes = next_nodes

        execution.status = "completed"
        execution.output_data = {"output": _truncate(final_output), "nodes": node_outputs}
        execution.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _send_complete(exec_id, "completed", final_output)

    except asyncio.CancelledError:
        # Stopping mid-node is the only way to break a long LLM or HTTP await. The
        # executor thread still finishes its own call; its result is simply dropped.
        try:
            execution = db.query(Execution).filter(Execution.id == exec_id).first()
            if execution:
                _mark_cancelled(execution)
                db.commit()
        except Exception:
            # WAL makes this unlikely, but a locked write here would otherwise leave
            # the row at running and skip the frame below.
            logger.exception("Could not persist the cancellation of execution %s", exec_id)
            db.rollback()
        logger.info("Execution cancelled: id=%s", exec_id)
        try:
            # Another 停止 click lands while this handler is still working; shield so
            # the client is told the run ended instead of waiting on nothing.
            await asyncio.shield(_send_complete(exec_id, "cancelled", ""))
        except Exception:
            pass
        raise

    except Exception as e:
        logger.exception("Workflow execution failed")
        try:
            execution = db.query(Execution).filter(Execution.id == exec_id).first()
            if execution:
                _append_log(execution, "error", f"执行异常终止：{e}")
                execution.status = "error"
                execution.output_data = {"error": str(e)}
                execution.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            logger.exception("Could not persist the failure of execution %s", exec_id)
            db.rollback()
        # Every other exit sends this frame. Without it the socket stays open and
        # the detail page keeps showing 运行中 for a run the database called error.
        await _send_complete(exec_id, "error", str(e))
    finally:
        db.close()
