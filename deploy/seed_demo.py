#!/usr/bin/env python3
"""Seed a running AgentFlow with demo content: three workflows and real, completed runs.

An empty deployment tells a visitor nothing, and the templates in the front end
only exist once someone clicks one. This script writes the graphs through the
public API and then actually executes them, so the history tab shows real model
output (branch taken, items looped, HTTP response) rather than a screenshot.

It is idempotent: a workflow is created only when its name is absent, and runs
are started only for a workflow that has no executions yet. Re-running is free.

    cd /opt/agentflow
    set -a; . backend/.env; set +a          # keeps the access code out of history
    python3 deploy/seed_demo.py

Against a local, ungated instance:
    AF_BASE_URL=http://127.0.0.1:8000 python3 deploy/seed_demo.py --no-login
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("AF_BASE_URL", "http://127.0.0.1:8001")
CODE = os.environ.get("AGENTFLOW_ACCESS_CODE", "")
POLL_TIMEOUT = int(os.environ.get("AF_SEED_POLL_TIMEOUT", "240"))


def node(nid, title, ntype, x, y, config):
    return {"id": nid, "type": ntype, "title": title, "x": x, "y": y, "config": config}


def edge(source, target, port="output"):
    return {"source": source, "target": target, "sourcePort": port}


DEMO_WORKFLOWS = [
    {
        "name": "示例 1 · 条件分支：客服分诊",
        "description": "先用小模型判定意图，再由条件节点决定走投诉处理还是标准答复。未选中的分支在执行日志里记为「跳过」。",
        "nodes": [
            node("start", "用户输入", "start", 60, 220, {}),
            node("llm_1", "意图分类", "llm", 270, 220, {
                "prompt": "下面是一句客户留言。只回复「投诉」或「咨询」两个词之一，不要解释。\n\n{{input}}",
                "model": "qwen-turbo", "temperature": 0.1}),
            node("cond_1", "是否投诉", "condition", 490, 220, {
                "condition": "'{{llm_1}}' contains \"投诉\""}),
            node("llm_2", "致歉并给出处置步骤", "llm", 730, 130, {
                "prompt": "客户提出了投诉。请先致歉，再给出 3 条可执行的处置步骤（每条不超过 25 字）：\n{{input}}",
                "model": "qwen-plus", "temperature": 0.6}),
            node("llm_3", "直接答复", "llm", 730, 310, {
                "prompt": "这是客户的咨询。请用两三句话直接回答：\n{{input}}",
                "model": "qwen-plus", "temperature": 0.5}),
            node("end", "结束", "end", 980, 220, {}),
        ],
        "edges": [
            edge("start", "llm_1"), edge("llm_1", "cond_1"),
            edge("cond_1", "llm_2", "true"), edge("cond_1", "llm_3", "false"),
            edge("llm_2", "end"), edge("llm_3", "end"),
        ],
        "runs": [
            {"input": "上周买的书收到时封面裂了一道口子，希望你们给个说法。"},
            {"input": "请问这本书下单之后大概几天发货？"},
        ],
    },
    {
        "name": "示例 2 · 批量循环：周报逐条提炼",
        "description": "文本节点把输入按行拆成列表，循环节点逐项调用模型（3 路并发）后聚合，最后再由一个模型把逐条结果写成一段。",
        "nodes": [
            node("start", "一周流水账", "start", 60, 220, {}),
            node("split_1", "按行拆分", "text", 270, 220, {
                "operation": "split", "texts": ["{{input}}"], "separator": "\\n"}),
            node("loop_1", "逐项提炼", "loop", 490, 220, {
                "source": "{{split_1}}", "separator": "\\n", "action": "llm",
                "prompt": "把下面这条工作记录压缩成一句 20 字以内的要点，只输出那句话：\n{{item}}",
                "model": "qwen-turbo", "temperature": 0.3, "max_items": 20, "join": "\\n"}),
            node("llm_1", "汇成一段", "llm", 730, 220, {
                "prompt": "把下列要点整合为一段连贯的周总结（不超过 120 字）：\n{{loop_1}}",
                "model": "qwen-plus", "temperature": 0.6}),
            node("end", "结束", "end", 960, 220, {}),
        ],
        "edges": [edge("start", "split_1"), edge("split_1", "loop_1"),
                  edge("loop_1", "llm_1"), edge("llm_1", "end")],
        "runs": [{"input": "\n".join([
            "周一：把条件节点的路由改成真正按分支选路，未选中的分支只记日志不执行",
            "周二：给运行加了取消按钮，长任务不再只能等它跑完",
            "周三：工作流支持导入导出 JSON，导入时逐条校验节点结构",
            "周四：修了 WebSocket 首包时序，页面打开慢也不会一直显示运行中",
            "周五：部署到公网服务器，配上访问口令和按 IP 的额度限制",
        ])}],
    },
    {
        "name": "示例 3 · HTTP 请求：服务自检",
        "description": "HTTP 节点请求本机健康检查接口，文本节点把返回值拼成一段可读的状态说明。换成任意外部地址即可用于真实探活。",
        "nodes": [
            node("start", "开始", "start", 60, 220, {}),
            node("http_1", "请求 /health", "http", 270, 220, {
                "url": "http://127.0.0.1:8000/health", "method": "GET",
                "headers": {}, "body": "", "fail_on_error": True}),
            node("text_1", "拼成状态说明", "text", 490, 220, {
                "operation": "concat",
                "texts": ["健康检查返回：", "{{http_1}}",
                          "\n以上由 AgentFlow 的 HTTP 节点直接请求本机接口得到。"]}),
            node("end", "结束", "end", 730, 220, {}),
        ],
        "edges": [edge("start", "http_1"), edge("http_1", "text_1"), edge("text_1", "end")],
        "runs": [{"input": "自检"}],
    },
]

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def api(method, path, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise SystemExit("seed: %s %s -> HTTP %d %s" % (method, path, e.code, detail))


def wait_for(execution_id):
    deadline = time.time() + POLL_TIMEOUT
    run = None
    while time.time() < deadline:
        run = api("GET", "/api/executions/%s" % execution_id)
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(2)
    raise SystemExit("seed: execution %s still %s after %ds"
                     % (execution_id, run and run["status"], POLL_TIMEOUT))


def main():
    if "--no-login" not in sys.argv:
        if not CODE:
            raise SystemExit("seed: AGENTFLOW_ACCESS_CODE is empty; export it or pass --no-login")
        api("POST", "/api/login", {"code": CODE})
    print("seed: working against %s" % BASE)

    known = {w["name"]: w["id"] for w in api("GET", "/api/workflows")}
    for spec in DEMO_WORKFLOWS:
        name = spec["name"]
        if name in known:
            wf_id = known[name]
            print("seed: exists  %s (#%d)" % (name, wf_id))
        else:
            wf_id = api("POST", "/api/workflows",
                        {k: spec[k] for k in ("name", "description", "nodes", "edges")})["id"]
            print("seed: created %s (#%d)" % (name, wf_id))

        if api("GET", "/api/executions?workflow_id=%d" % wf_id):
            print("seed: %s already has runs, not spending more model calls" % name)
            continue
        for payload in spec["runs"]:
            started = api("POST", "/api/workflows/%d/execute" % wf_id, payload, timeout=90)
            run = wait_for(started["execution_id"])
            out = (run["output_data"] or {}).get("output", "")
            print("seed:   run #%s %s, %d log lines, %d nodes, output=%s" % (
                run["id"], run["status"], len(run["logs"] or []),
                len((run["output_data"] or {}).get("nodes", {})), out[:60].replace("\n", " ")))
            if run["status"] != "completed":
                raise SystemExit("seed: run #%s ended as %s: %s"
                                 % (run["id"], run["status"], out[:200]))
    print("seed: done")


if __name__ == "__main__":
    main()
