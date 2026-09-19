import os
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import engine, SessionLocal, Workflow, Execution
from workflow_engine import execute_node
from llm_client import decompose_task, call_llm
from node_types import NODE_TYPES

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

active_connections: dict[int, WebSocket] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="AI Agent Workflow Platform", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
async def create_workflow(data: WorkflowCreate):
    db = SessionLocal()
    try:
        workflow = Workflow(
            name=data.name,
            description=data.description,
            nodes=data.nodes,
            edges=data.edges,
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
        return {"id": workflow.id, "name": workflow.name, "created_at": workflow.created_at.isoformat()}
    finally:
        db.close()


@app.get("/api/workflows")
async def list_workflows():
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: int):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: int, data: WorkflowUpdate):
    db = SessionLocal()
    try:
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
        workflow.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Workflow updated"}
    finally:
        db.close()


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int):
    db = SessionLocal()
    try:
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        db.delete(workflow)
        db.commit()
        return {"message": "Workflow deleted"}
    finally:
        db.close()


@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: int, data: ExecuteRequest):
    db = SessionLocal()
    try:
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        execution = Execution(
            workflow_id=workflow_id,
            status="running",
            input_data=data.input,
            started_at=datetime.utcnow(),
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        exec_id = execution.id
    finally:
        db.close()

    asyncio.create_task(_run_workflow(exec_id, workflow_id, workflow.nodes, workflow.edges, data.input))

    return {"execution_id": exec_id, "status": "running"}


@app.get("/api/executions/{execution_id}")
async def get_execution(execution_id: int):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.get("/api/executions")
async def list_executions(workflow_id: int = None):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.post("/api/decompose")
async def decompose(data: DecomposeRequest):
    steps = decompose_task(data.task)
    return {"steps": steps}


@app.post("/api/nodes/execute")
async def execute_single_node(data: NodeExecuteRequest):
    result = await execute_node(data.node, data.context)
    return result


@app.get("/api/stats")
async def get_stats():
    db = SessionLocal()
    try:
        workflow_count = db.query(Workflow).count()
        execution_count = db.query(Execution).count()
        success_count = db.query(Execution).filter(Execution.status == "completed").count()
        return {
            "workflows": workflow_count,
            "executions": execution_count,
            "success_rate": round(success_count / execution_count * 100, 1) if execution_count > 0 else 0,
        }
    finally:
        db.close()


@app.websocket("/ws/execute/{execution_id}")
async def websocket_execute(websocket: WebSocket, execution_id: int):
    await websocket.accept()
    active_connections[execution_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        active_connections.pop(execution_id, None)


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
        node_map = {n["id"]: n for n in nodes}
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
            log_entry = {"node_id": node_id, "status": status, "message": message, "timestamp": datetime.utcnow().isoformat()}
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

        while current_nodes:
            next_nodes = []
            for node in current_nodes:
                node_id = node["id"]
                if node_id in visited:
                    continue
                visited.add(node_id)

                result = await execute_node(node, context, send_log)

                if result["status"] == "error":
                    execution.status = "error"
                    execution.output_data = {"error": result["output"]}
                    execution.finished_at = datetime.utcnow()
                    db.commit()
                    ws = active_connections.get(exec_id)
                    if ws:
                        try:
                            await ws.send_json({"type": "complete", "status": "error", "output": result["output"]})
                        except Exception:
                            pass
                    return

                context[node_id] = result["output"]
                final_output = result["output"]

                for edge in edge_map.get(node_id, []):
                    target_id = edge.get("target")
                    if target_id and target_id in node_map and target_id not in visited:
                        next_nodes.append(node_map[target_id])

            current_nodes = next_nodes

        execution.status = "completed"
        execution.output_data = {"output": final_output}
        execution.finished_at = datetime.utcnow()
        db.commit()

        ws = active_connections.get(exec_id)
        if ws:
            try:
                await ws.send_json({"type": "complete", "status": "completed", "output": final_output})
            except Exception:
                pass

    except Exception as e:
        execution = db.query(Execution).filter(Execution.id == exec_id).first()
        if execution:
            execution.status = "error"
            execution.output_data = {"error": str(e)}
            execution.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
