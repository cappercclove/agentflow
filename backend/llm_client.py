import os
from openai import OpenAI

_client_cache = {}


def get_client(model: str = None):
    if model not in _client_cache:
        _client_cache[model] = OpenAI(
            api_key=os.getenv("BAILIAN_API_KEY"),
            base_url=os.getenv("BAILIAN_BASE_URL"),
        )
    return _client_cache[model]


def _get_model_map():
    return {
        "qwen-plus": os.getenv("BAILIAN_MODEL", "qwen-plus"),
        "qwen-turbo": "qwen-turbo",
        "qwen-max": "qwen-max",
    }


def call_llm(prompt: str, model: str = "qwen-plus", temperature: float = 0.7) -> str:
    model_name = _get_model_map().get(model, model)
    client = get_client(model)
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=2048,
    )
    return response.choices[0].message.content.strip()


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
