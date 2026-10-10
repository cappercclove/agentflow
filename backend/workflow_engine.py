import json
import asyncio
import re
import time
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
    "contains": lambda a, b: str(b) in str(a),
}

LOGIC_TOKENS = ("and", "or", "contains")

TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?|\"[^\"]*\"|'[^']*'|==|!=|>=|<=|>|<|and|or|contains|[a-zA-Z_]\w*)")


def _safe_eval_condition(expr: str, context: dict):
    tokens = [t for t in TOKEN_RE.findall(expr) if t.strip()]
    if not tokens:
        return False

    def resolve(token):
        if token in LOGIC_TOKENS:
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

    started = time.perf_counter()
    try:
        if node_type == "llm":
            result = await _exec_llm(node, context)
        elif node_type == "condition":
            result = await _exec_condition(node, context)
        elif node_type == "http":
            result = await _exec_http(node, context)
        elif node_type == "text":
            result = await _exec_text(node, context)
        elif node_type == "loop":
            result = await _exec_loop(node, context)
        elif node_type == "start":
            result = {"output": context.get("input", "")}
        elif node_type == "end":
            result = {"output": context.get("final_output", "工作流执行完成")}
        else:
            result = {"output": f"未知节点类型: {node_type}"}

        duration_ms = int((time.perf_counter() - started) * 1000)
        note = result.get("note") or ""
        if send_log:
            suffix = f"（{duration_ms}ms）" + (f" · {note}" if note else "")
            await send_log(node_id, "completed", f"完成: {node_title}{suffix}")

        out = {"status": "success", "output": result.get("output", ""), "duration_ms": duration_ms}
        if result.get("branch"):
            out["branch"] = result["branch"]
        return out

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
    except Exception as e:
        logger.warning("Condition node failed to evaluate: node_id=%s expr=%r error=%s", node.get("id"), condition, e)
        return {"output": "false", "branch": "false", "note": "表达式解析失败，走 false 分支"}

    branch = "true" if result else "false"
    return {"output": branch, "branch": branch, "note": f"分支 → {branch}"}


async def _exec_http(node: dict, context: dict) -> dict:
    cfg = node.get("config", {})
    url = _replace_vars(cfg.get("url", ""), context)
    method = str(cfg.get("method", "GET")).upper()
    headers = _as_headers(cfg.get("headers", {}))
    body = _replace_vars(cfg.get("body", ""), context)

    if not url:
        raise ValueError("HTTP 节点未配置请求地址")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.request(
            method,
            url,
            headers=headers,
            content=body.encode("utf-8") if body else None,
        )

    if resp.is_error and cfg.get("fail_on_error", True):
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    return {"output": resp.text, "status_code": resp.status_code, "note": f"{method} {resp.status_code}"}


async def _exec_loop(node: dict, context: dict) -> dict:
    cfg = node.get("config", {})
    items = _as_list(_replace_vars(cfg.get("source", "{{input}}"), context), _unescape(cfg.get("separator", "\n")))

    try:
        max_items = max(1, min(int(cfg.get("max_items", 20) or 20), 100))
    except (TypeError, ValueError):
        max_items = 20
    items = items[:max_items]

    if not items:
        return {"output": "", "note": "0 项"}

    join = _unescape(cfg.get("join", "\n\n"))

    if cfg.get("action", "llm") != "llm":
        return {"output": join.join(items), "note": f"{len(items)} 项"}

    template = cfg.get("prompt", "{{item}}")
    model = cfg.get("model", "qwen-plus")
    temperature = float(cfg.get("temperature", 0.5))
    semaphore = asyncio.Semaphore(3)
    loop = asyncio.get_running_loop()

    async def run_one(index: int, item: str) -> str:
        item_context = dict(context)
        item_context["item"] = item
        item_context["index"] = index + 1
        prompt = _replace_vars(template, item_context)
        async with semaphore:
            try:
                return await loop.run_in_executor(None, call_llm, prompt, model, temperature)
            except Exception as e:
                logger.warning("Loop item failed: node_id=%s index=%s error=%s", node.get("id"), index, e)
                return f"[第 {index + 1} 项执行失败: {e}]"

    results = await asyncio.gather(*(run_one(i, it) for i, it in enumerate(items)))
    failures = [r for r in results if r.startswith("[第")]
    if len(failures) == len(items):
        raise RuntimeError(f"循环 {len(items)} 项全部失败：{failures[0]}")
    return {"output": join.join(results), "note": f"{len(items)} 项" + (f"，{len(failures)} 项失败" if failures else "")}


async def _exec_text(node: dict, context: dict) -> dict:
    operation = node.get("config", {}).get("operation", "concat")
    texts = node.get("config", {}).get("texts", [])

    processed = [_replace_vars(t, context) for t in texts]

    if operation == "concat":
        return {"output": "".join(processed)}
    elif operation == "split":
        separator = _unescape(node.get("config", {}).get("separator", "\n"))
        return {"output": processed[0].split(separator) if processed else []}
    elif operation == "replace":
        text = processed[0] if processed else ""
        old = node.get("config", {}).get("old", "")
        new = node.get("config", {}).get("new", "")
        return {"output": text.replace(old, new)}
    else:
        return {"output": processed[0] if processed else ""}


def _unescape(text: str) -> str:
    if not isinstance(text, str):
        return text
    return text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "")


def _as_list(value, separator: str) -> list:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(i).strip() for i in parsed if str(i).strip()]
            if isinstance(parsed, dict):
                return [f"{k}: {v}" for k, v in parsed.items()]
        return [i.strip() for i in stripped.split(separator) if i.strip()]
    if isinstance(value, (list, tuple)):
        return [str(i).strip() for i in value if str(i).strip()]
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    if value is None:
        return []
    return [str(value)]


def _as_headers(headers) -> dict:
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    if isinstance(headers, str) and headers.strip():
        try:
            parsed = json.loads(headers)
        except json.JSONDecodeError:
            raise ValueError("请求头需为 JSON 对象，例如 {\"Authorization\": \"Bearer xxx\"}")
        if not isinstance(parsed, dict):
            raise ValueError("请求头需为 JSON 对象")
        return {str(k): str(v) for k, v in parsed.items()}
    return {}


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


REQUIRED_CONFIG = {
    "llm": ("prompt", "提示词"),
    "condition": ("condition", "条件表达式"),
    "http": ("url", "请求地址"),
}


def validate_workflow(nodes: list, edges: list) -> list[str]:
    """Return a list of human-readable problems that would break execution."""
    from node_types import NODE_TYPES

    if not nodes:
        return ["工作流为空，请先从左侧拖入节点"]

    problems = []
    ids = [n.get("id") for n in nodes]
    id_set = {i for i in ids if i}

    duplicated = sorted({i for i in id_set if ids.count(i) > 1})
    if duplicated:
        problems.append(f"节点 ID 重复: {', '.join(duplicated)}")

    starts = [n for n in nodes if n.get("type") == "start"]
    if not starts:
        problems.append("缺少「开始」节点")
    elif len(starts) > 1:
        problems.append(f"有 {len(starts)} 个「开始」节点，只应保留 1 个")

    if not any(n.get("type") == "end" for n in nodes):
        problems.append("缺少「结束」节点")

    for node in nodes:
        node_id = node.get("id") or "?"
        node_type = node.get("type")
        label = node.get("title") or node_type
        if node_type not in NODE_TYPES:
            problems.append(f"节点「{label}」类型未知: {node_type}")
            continue
        key, field = REQUIRED_CONFIG.get(node_type, (None, None))
        if key and not str(node.get("config", {}).get(key, "")).strip():
            problems.append(f"节点「{label}」未填写{field}")

    for edge in edges:
        for endpoint in ("source", "target"):
            if edge.get(endpoint) not in id_set:
                problems.append(f"连线引用了不存在的节点: {edge.get(endpoint)}")

    reachable = set()
    out_map = {}
    for edge in edges:
        out_map.setdefault(edge.get("source"), []).append(edge.get("target"))
    queue = [n.get("id") for n in starts]
    while queue:
        current = queue.pop()
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(out_map.get(current, []))

    orphans = [n.get("title") or n.get("id") for n in nodes if n.get("id") not in reachable]
    if orphans:
        problems.append(f"以下节点没有从「开始」连通的线路: {', '.join(orphans)}")

    return problems
