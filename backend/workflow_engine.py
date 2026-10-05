import json
import asyncio
import re
import operator
import logging
import httpx
from datetime import datetime, timezone
from llm_client import call_llm

logger = logging.getLogger(__name__)


SAFE_OPS = {
    "==": operator.eq, "!=": operator.ne,
    ">": operator.gt, ">=": operator.ge,
    "<": operator.lt, "<=": operator.le,
    "and": lambda a, b: bool(a) and bool(b),
    "or": lambda a, b: bool(a) or bool(b),
}

TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?|\"[^\"]*\"|'[^']*'|==|!=|>=|<=|>|<|and|or|[a-zA-Z_]\w*)")


def _safe_eval_condition(expr: str, context: dict):
    tokens = [t for t in TOKEN_RE.findall(expr) if t.strip()]
    if not tokens:
        return False

    def resolve(token):
        if token in ("and", "or"):
            return token
        if token in SAFE_OPS:
            return token
        if token.startswith(("\"", "'")):
            return token[1:-1]
        try:
            return float(token) if "." in token else int(token)
        except ValueError:
            return context.get(token, "")

    def parse_or(pos):
        left, pos = parse_and(pos)
        while pos < len(tokens) and tokens[pos] == "or":
            right, pos = parse_and(pos + 1)
            left = SAFE_OPS["or"](left, right)
        return left, pos

    def parse_and(pos):
        left, pos = parse_comparison(pos)
        while pos < len(tokens) and tokens[pos] == "and":
            right, pos = parse_comparison(pos + 1)
            left = SAFE_OPS["and"](left, right)
        return left, pos

    def parse_comparison(pos):
        left = resolve(tokens[pos])
        pos += 1
        if pos < len(tokens) and tokens[pos] in SAFE_OPS:
            op = SAFE_OPS[tokens[pos]]
            right = resolve(tokens[pos + 1])
            return op(left, right), pos + 2
        return bool(left), pos

    result, _ = parse_or(0)
    return bool(result)


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

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, call_llm, prompt, model, temperature)
    logger.info("LLM node executed: node_id=%s model=%s", node.get("id"), model)
    return {"output": result}


async def _exec_condition(node: dict, context: dict) -> dict:
    condition = node.get("config", {}).get("condition", "")
    condition = _replace_vars(condition, context)

    try:
        result = _safe_eval_condition(condition, context)
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
