import os
from openai import APIConnectionError, APIStatusError, OpenAI

_client_cache = {}


def get_client(model: str = None):
    if model not in _client_cache:
        _client_cache[model] = OpenAI(
            api_key=os.getenv("BAILIAN_API_KEY"),
            base_url=os.getenv("BAILIAN_BASE_URL"),
        )
    return _client_cache[model]


def _get_model_map():
    # A dedicated Bailian endpoint does not necessarily serve every public model
    # name, so each tier can be pointed at a concrete id on that endpoint.
    return {
        "qwen-plus": os.getenv("BAILIAN_MODEL", "qwen-plus"),
        "qwen-turbo": os.getenv("BAILIAN_MODEL_TURBO", "qwen-turbo"),
        "qwen-max": os.getenv("BAILIAN_MODEL_MAX", "qwen-max"),
    }


def call_llm(prompt: str, model: str = "qwen-plus", temperature: float = 0.7) -> str:
    # The panel writes a string here; an imported graph can put a number or null, and
    # the SDK rejects anything that is not a str with an error nobody can trace back
    # to the model field.
    model_id = model if isinstance(model, str) and model.strip() else "qwen-plus"
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("提示词为空，无法调用模型")
    model_name = _get_model_map().get(model_id, model_id)
    client = get_client(model_id)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=2048,
        )
    except APIConnectionError as e:
        # What the SDK says ("Connection error.") is true but useless next to a
        # canvas: the user needs to know the model service is unreachable, not that
        # a Python class raised.
        raise RuntimeError(f"无法连接大模型服务，请检查网络或接口地址：{e}") from e
    except APIStatusError as e:
        raise RuntimeError(f"大模型服务返回 {e.status_code}：{str(e)[:200]}") from e
    choices = response.choices or []
    # A content-filtered or truncated completion can come back with no choices at
    # all, or with message.content = None. Both used to raise AttributeError here
    # and surface as an unexplained 500; an empty string would be worse, because
    # the workflow would keep going on nothing.
    content = choices[0].message.content if choices else None
    if not content or not content.strip():
        raise RuntimeError("模型没有返回内容，请重试或更换模型")
    return content.strip()


def decompose_task(task: str) -> list[dict]:
    prompt = f"""你是一个任务规划专家。请将以下复杂任务分解为多个可执行的子任务步骤。

任务：{task}

请以 JSON 数组格式返回，每个子任务包含：
- step: 步骤序号（从1开始）
- title: 步骤标题（简短）
- description: 步骤描述（具体要做什么）
- type: 任务类型（llm / http / text / condition）
- input: 该步骤的输入描述
- output: 该步骤期望的输出描述

只返回 JSON 数组，不要其他内容。"""

    result = call_llm(prompt, model="qwen-plus", temperature=0.3)
    import json
    try:
        start = result.index("[")
        end = result.rindex("]") + 1
        return json.loads(result[start:end])
    except (ValueError, json.JSONDecodeError):
        return [{"step": 1, "title": "执行任务", "description": task, "type": "llm", "input": task, "output": "任务结果"}]
