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

COMPARISON_OPS = ("==", "!=", ">", ">=", "<", "<=")

# What parse_comparison is allowed to consume as a binary operator. "and" / "or"
# are deliberately absent: treating them as operators makes the parser fold
# "x or y and z" left-to-right, so a rule that already matched on x still takes
# the false branch. They belong to the level above.
BINARY_OPS = COMPARISON_OPS + ("contains",)


def _as_number(value):
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _align_numeric(op_name: str, left, right):
    """Compare '10' against 5 as numbers, not as a string against an int.

    Node outputs are always text, so a literal in the expression is the only side
    that arrives typed. Without this, x > 5 raises TypeError and the node silently
    takes the false branch.
    """
    if op_name not in COMPARISON_OPS or isinstance(left, type(right)):
        return left, right
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        converted = _as_number(right)
        return (left, converted) if converted is not None else (left, right)
    if isinstance(right, (int, float)) and not isinstance(right, bool):
        converted = _as_number(left)
        return (converted, right) if converted is not None else (left, right)
    return left, right


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
        if pos < len(tokens) and tokens[pos] in BINARY_OPS:
            op_name = tokens[pos]
            right = resolve(tokens[pos + 1])
            left, right = _align_numeric(op_name, left, right)
            return SAFE_OPS[op_name](left, right), pos + 2
        return bool(left), pos

    result, _ = parse_or(0)
    return bool(result)


def _cfg(node: dict) -> dict:
    """A config that is not an object would make every executor raise AttributeError.

    The API refuses such a graph now, but a row written before that check exists can
    still come back from the database, and a crash there reads as a server bug.
    """
    cfg = node.get("config")
    return cfg if isinstance(cfg, dict) else {}


def _as_prompt(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _as_temperature(value, default: float = 0.7) -> float:
    """Never let a stray value reach the provider: an unparseable temperature becomes
    the default, an out-of-range one is clamped, and both say so in the log."""
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        logger.warning("Temperature is not a number (%r), using %s", value, default)
        return default
    clamped = max(0.0, min(temperature, 2.0))
    if clamped != temperature:
        logger.warning("Temperature %s clamped to %s", temperature, clamped)
    return clamped


async def execute_node(node: dict, context: dict, send_log=None) -> dict:
    if not isinstance(node, dict):
        return {"status": "error", "output": f"节点不是对象: {type(node).__name__}"}
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
            raise ValueError(f"未知节点类型: {node_type}")

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
    cfg = _cfg(node)
    prompt = _as_prompt(cfg.get("prompt", ""))
    model = cfg.get("model", "qwen-plus")
    temperature = _as_temperature(cfg.get("temperature", 0.7))

    prompt = _replace_vars(prompt, context)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, call_llm, prompt, model, temperature)
    logger.info("LLM node executed: node_id=%s model=%s", node.get("id"), model)
    return {"output": result}


async def _exec_condition(node: dict, context: dict) -> dict:
    condition = _as_prompt(_cfg(node).get("condition", ""))
    condition = _replace_vars(condition, context)

    try:
        result = _safe_eval_condition(condition, context)
    except Exception as e:
        logger.warning("Condition node failed to evaluate: node_id=%s expr=%r error=%s", node.get("id"), condition, e)
        return {"output": "false", "branch": "false", "note": f"表达式无法求值（{e}），走 false 分支"}

    branch = "true" if result else "false"
    return {"output": branch, "branch": branch, "note": f"分支 → {branch}"}


# A response is kept as one string in the execution row, so an uncapped body becomes
# both the process memory and the database.
MAX_HTTP_OUTPUT_CHARS = 200_000

# Not a general SSRF filter — the demo's own self-check node calls 127.0.0.1, and any
# node here is written by the person who owns the instance. These few addresses are
# separate: they hand out the machine's cloud credentials to whoever asks.
BLOCKED_HTTP_HOSTS = {
    "169.254.169.254", "metadata.google.internal", "metadata.goog", "100.100.100.200",
}


def _check_http_target(url: str) -> None:
    try:
        host = httpx.URL(url).host
    except Exception:
        raise ValueError(f"请求地址无法解析: {url[:80]}")
    if host.lower() in BLOCKED_HTTP_HOSTS:
        raise ValueError(f"该地址是云厂商的元数据服务，不允许请求: {host}")


async def _exec_http(node: dict, context: dict) -> dict:
    cfg = _cfg(node)
    url = _as_prompt(cfg.get("url", ""))
    url = _replace_vars(url, context).strip()
    method = str(cfg.get("method", "GET")).upper()
    headers = _as_headers(cfg.get("headers", {}))
    body = _replace_vars(_as_prompt(cfg.get("body", "")), context)

    if not url:
        raise ValueError("HTTP 节点未配置请求地址")
    _check_http_target(url)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.request(
            method,
            url,
            headers=headers,
            content=body.encode("utf-8") if body else None,
        )

    if resp.is_error and cfg.get("fail_on_error", True):
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    text = resp.text
    note = f"{method} {resp.status_code}"
    if len(text) > MAX_HTTP_OUTPUT_CHARS:
        text = text[:MAX_HTTP_OUTPUT_CHARS]
        note += f"，响应已截断到 {MAX_HTTP_OUTPUT_CHARS // 1000}k 字符"

    return {"output": text, "status_code": resp.status_code, "note": note}


async def _exec_loop(node: dict, context: dict) -> dict:
    cfg = _cfg(node)
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
    temperature = _as_temperature(cfg.get("temperature", 0.5), 0.5)
    semaphore = asyncio.Semaphore(3)
    loop = asyncio.get_running_loop()

    async def run_one(index: int, item: str):
        item_context = dict(context)
        item_context["item"] = item
        item_context["index"] = index + 1
        prompt = _replace_vars(template, item_context)
        async with semaphore:
            try:
                return await loop.run_in_executor(None, call_llm, prompt, model, temperature), True
            except Exception as e:
                logger.warning("Loop item failed: node_id=%s index=%s error=%s", node.get("id"), index, e)
                return f"[第 {index + 1} 项执行失败: {e}]", False

    # Carried as a flag, not sniffed from the text: an answer that legitimately
    # starts with 「[第」 used to be counted as a failure, and if every item read
    # that way the whole node was reported as errored.
    outcomes = await asyncio.gather(*(run_one(i, it) for i, it in enumerate(items)))
    results = [text for text, _ in outcomes]
    failures = [text for text, ok in outcomes if not ok]
    if len(failures) == len(items):
        raise RuntimeError(f"循环 {len(items)} 项全部失败：{failures[0]}")
    return {"output": join.join(results), "note": f"{len(items)} 项" + (f"，{len(failures)} 项失败" if failures else "")}


def _as_text_list(texts) -> list:
    """The panel writes an array; a hand-written graph can put a bare string here, and
    iterating that silently turns 「hello」 into five one-character items."""
    if isinstance(texts, str):
        return [texts]
    if isinstance(texts, (list, tuple)):
        return list(texts)
    if texts is None:
        return []
    raise ValueError(f"文本处理的 texts 需要是数组或字符串，当前是 {type(texts).__name__}")


async def _exec_text(node: dict, context: dict) -> dict:
    cfg = _cfg(node)
    operation = cfg.get("operation", "concat")
    texts = _as_text_list(cfg.get("texts", []))

    processed = [_as_prompt(_replace_vars(t, context)) for t in texts]

    if operation == "concat":
        return {"output": "".join(processed)}
    elif operation == "split":
        separator = _unescape(_cfg(node).get("separator", "\n"))
        return {"output": processed[0].split(separator) if processed else []}
    elif operation == "replace":
        text = processed[0] if processed else ""
        old = _cfg(node).get("old", "")
        new = _cfg(node).get("new", "")
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


VAR_RE = re.compile(r"\{\{([^{}]+)\}\}")


def _replace_vars(text: str, context: dict) -> str:
    """Replace every placeholder in one pass over the original string.

    Looping over the context and calling str.replace each time lets a value that
    itself contains a placeholder be substituted again, so an upstream node whose
    output happens to be "{{input}}" — a model echoing a template, a JSON body —
    would inject another node's data, and the result would depend on dict order.
    """
    if not isinstance(text, str):
        return text

    def render(match):
        key = match.group(1)
        if key not in context:
            return match.group(0)
        value = context[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return str(value)

    return VAR_RE.sub(render, text)


REQUIRED_CONFIG = {
    "llm": ("prompt", "提示词"),
    "condition": ("condition", "条件表达式"),
    "http": ("url", "请求地址"),
}

# Node ids are interpolated into CSS selectors, DOM data attributes and inline
# handlers by the editor. Constraining them here — at the only boundary an imported
# or hand-written graph crosses — is what keeps those sites from needing to be
# clever about characters that can never legitimately appear.
NODE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


def _known_node_types() -> set:
    from node_types import NODE_TYPES

    return set(NODE_TYPES)


def validate_graph_shape(nodes: list, edges: list, allow_empty: bool = False) -> list[str]:
    """Structural checks only, so an imported draft is never rejected for being unfinished.

    allow_empty covers the editor's own empty canvas: a brand-new workflow is saved with
    no nodes, and refusing that would make the first autosave fail.
    """
    if not isinstance(nodes, list) or (not nodes and not allow_empty):
        return ["文件里没有节点"] if not allow_empty else []

    problems = []
    ids = []

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            problems.append(f"第 {index + 1} 个节点不是对象")
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            problems.append(f"第 {index + 1} 个节点缺少 id")
        elif not NODE_ID_RE.match(node_id):
            problems.append(
                f"节点 ID 只能用字母、数字、下划线和连字符，且以字母或下划线开头: {node_id[:24]}"
            )
        else:
            ids.append(node_id)
        if not node.get("type"):
            problems.append(f"节点「{node_id or index + 1}」缺少 type")
        elif node["type"] not in _known_node_types():
            # A type the palette does not offer cannot be drawn, configured or run, so
            # accepting it only produced a blank box on the canvas that no later save
            # could get rid of.
            problems.append(f"节点「{node_id or index + 1}」类型未知: {node['type']}")
        if "config" in node and not isinstance(node["config"], dict):
            # Every executor reads config.get(...); a string here turns 检查 and 运行
            # into a 500 instead of a message.
            problems.append(f"节点「{node_id or index + 1}」的 config 不是对象")
        for axis in ("x", "y"):
            value = node.get(axis, 0)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
                problems.append(f"节点「{node_id or index + 1}」的坐标 {axis} 不是数字")

    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        problems.append(f"节点 ID 重复: {', '.join(duplicated)}")

    if not isinstance(edges, list):
        problems.append("edges 必须是数组")
    else:
        id_set = set(ids)
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                problems.append(f"第 {index + 1} 条连线不是对象")
                continue
            for endpoint in ("source", "target"):
                if edge.get(endpoint) not in id_set:
                    problems.append(f"第 {index + 1} 条连线的 {endpoint} 指向不存在的节点: {edge.get(endpoint)}")

    return problems


def validate_workflow(nodes: list, edges: list) -> list[str]:
    """Return a list of human-readable problems that would break execution."""
    from node_types import NODE_TYPES

    if not nodes:
        return ["工作流为空，请先从左侧拖入节点"]

    problems = []
    # Shape first: everything below assumes a node is a dict with an id, and a junk
    # workflow can reach here straight from the database or /api/workflows/validate.
    shape_problems = validate_graph_shape(nodes, edges)
    if shape_problems:
        return shape_problems

    ids = [n.get("id") for n in nodes]
    id_set = {i for i in ids if i}

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
        if key and not str(_cfg(node).get(key, "")).strip():
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
