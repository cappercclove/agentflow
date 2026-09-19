import json
import asyncio
import httpx
from datetime import datetime
from llm_client import call_llm


async def execute_node(node: dict, context: dict, send_log=None) -> dict:
    node_type = node.get("type", "llm")
    node_id = node.get("id", "unknown")
    node_title = node.get("title", node_type)

    if send_log:
        await send_log(node_id, "running", f"开始执行: {node_title}")

    try:
        if node_type == "llm":
            result = await _exec_llm(node, context)
        elif node_type == "condition":
            result = await _exec_condition(node, context)
        elif node_type == "http":
            result = await _exec_http(node, context)
        elif node_type == "text":
            result = await _exec_text(node, context)
        elif node_type == "start":
            result = {"output": context.get("input", "")}
        elif node_type == "end":
            result = {"output": context.get("final_output", "工作流执行完成")}
        else:
            result = {"output": f"未知节点类型: {node_type}"}

        if send_log:
            await send_log(node_id, "completed", f"完成: {node_title}")

        return {"status": "success", "output": result.get("output", "")}

    except Exception as e:
        if send_log:
            await send_log(node_id, "error", f"错误: {str(e)}")
        return {"status": "error", "output": str(e)}


async def _exec_llm(node: dict, context: dict) -> dict:
    prompt = node.get("config", {}).get("prompt", "")
    model = node.get("config", {}).get("model", "qwen-plus")
    temperature = node.get("config", {}).get("temperature", 0.7)

    prompt = _replace_vars(prompt, context)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, call_llm, prompt, model, temperature)
    return {"output": result}


async def _exec_condition(node: dict, context: dict) -> dict:
    condition = node.get("config", {}).get("condition", "")
    condition = _replace_vars(condition, context)

    try:
        result = eval(condition, {"__builtins__": {}}, context)
        branch = "true" if result else "false"
        return {"output": branch, "branch": branch}
    except Exception:
        return {"output": "false", "branch": "false"}


async def _exec_http(node: dict, context: dict) -> dict:
    url = node.get("config", {}).get("url", "")
    method = node.get("config", {}).get("method", "GET")
    headers = node.get("config", {}).get("headers", {})
    body = node.get("config", {}).get("body", "")

    url = _replace_vars(url, context)
    body = _replace_vars(body, context)

    async with httpx.AsyncClient(timeout=30) as client:
        if method.upper() == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, headers=headers, content=body)

    return {"output": resp.text, "status_code": resp.status_code}


async def _exec_text(node: dict, context: dict) -> dict:
    operation = node.get("config", {}).get("operation", "concat")
    texts = node.get("config", {}).get("texts", [])

    processed = [_replace_vars(t, context) for t in texts]

    if operation == "concat":
        return {"output": "".join(processed)}
    elif operation == "split":
        separator = node.get("config", {}).get("separator", "\n")
        return {"output": processed[0].split(separator) if processed else []}
    elif operation == "replace":
        text = processed[0] if processed else ""
        old = node.get("config", {}).get("old", "")
        new = node.get("config", {}).get("new", "")
        return {"output": text.replace(old, new)}
    else:
        return {"output": processed[0] if processed else ""}


def _replace_vars(text: str, context: dict) -> str:
    if not isinstance(text, str):
        return text
    for key, value in context.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)
        text = text.replace(placeholder, value)
    return text
