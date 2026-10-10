from workflow_engine import (
    _as_list,
    _replace_vars,
    _safe_eval_condition,
    execute_node,
    validate_workflow,
)


class TestSafeEval:
    def test_comparison_eq(self):
        assert _safe_eval_condition("x == 1", {"x": 1}) is True
        assert _safe_eval_condition("x == 1", {"x": 2}) is False

    def test_comparison_ne(self):
        assert _safe_eval_condition("x != 1", {"x": 2}) is True
        assert _safe_eval_condition("x != 1", {"x": 1}) is False

    def test_comparison_gt_lt(self):
        assert _safe_eval_condition("x > 5", {"x": 10}) is True
        assert _safe_eval_condition("x < 5", {"x": 3}) is True
        assert _safe_eval_condition("x >= 5", {"x": 5}) is True
        assert _safe_eval_condition("x <= 5", {"x": 4}) is True

    def test_string_comparison(self):
        assert _safe_eval_condition('status == "ok"', {"status": "ok"}) is True
        assert _safe_eval_condition("status == 'ok'", {"status": "ok"}) is True

    def test_logical_and(self):
        assert _safe_eval_condition("x > 1 and y < 10", {"x": 5, "y": 3}) is True
        assert _safe_eval_condition("x > 1 and y < 10", {"x": 5, "y": 15}) is False

    def test_logical_or(self):
        assert _safe_eval_condition("x > 10 or y < 5", {"x": 1, "y": 3}) is True
        assert _safe_eval_condition("x > 10 or y < 5", {"x": 1, "y": 8}) is False

    def test_empty_expr(self):
        assert _safe_eval_condition("", {}) is False

    def test_missing_var(self):
        assert _safe_eval_condition("x == 1", {}) is False

    def test_truthy_value(self):
        assert _safe_eval_condition("x", {"x": "hello"}) is True
        assert _safe_eval_condition("x", {"x": ""}) is False


class TestReplaceVars:
    def test_basic_replace(self):
        result = _replace_vars("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_multiple_replace(self):
        result = _replace_vars("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_no_match(self):
        result = _replace_vars("no vars here", {"x": 1})
        assert result == "no vars here"

    def test_non_string_input(self):
        assert _replace_vars(123, {}) == 123


class TestExecuteNode:
    async def test_start_node(self):
        node = {"id": "start", "type": "start", "config": {}}
        result = await execute_node(node, {"input": "hello"})
        assert result["status"] == "success"
        assert result["output"] == "hello"

    async def test_end_node(self):
        node = {"id": "end", "type": "end", "config": {}}
        result = await execute_node(node, {"final_output": "done"})
        assert result["status"] == "success"
        assert result["output"] == "done"

    async def test_text_concat(self):
        node = {
            "id": "t1",
            "type": "text",
            "config": {"operation": "concat", "texts": ["Hello", " ", "World"]},
        }
        result = await execute_node(node, {})
        assert result["status"] == "success"
        assert result["output"] == "Hello World"

    async def test_text_replace(self):
        node = {
            "id": "t2",
            "type": "text",
            "config": {"operation": "replace", "texts": ["foo bar"], "old": "foo", "new": "baz"},
        }
        result = await execute_node(node, {})
        assert result["output"] == "baz bar"

    async def test_condition_true(self):
        node = {
            "id": "c1",
            "type": "condition",
            "config": {"condition": "x > 5"},
        }
        result = await execute_node(node, {"x": 10})
        assert result["output"] == "true"

    async def test_condition_false(self):
        node = {
            "id": "c2",
            "type": "condition",
            "config": {"condition": "x > 5"},
        }
        result = await execute_node(node, {"x": 2})
        assert result["output"] == "false"

    async def test_unknown_type(self):
        node = {"id": "u1", "type": "unknown", "config": {}}
        result = await execute_node(node, {})
        assert result["status"] == "success"
        assert "未知" in result["output"]

    async def test_condition_exposes_branch(self):
        node = {"id": "c3", "type": "condition", "config": {"condition": "x > 5"}}
        result = await execute_node(node, {"x": 10})
        assert result["branch"] == "true"

    async def test_condition_invalid_expression_falls_back_to_false(self):
        node = {"id": "c4", "type": "condition", "config": {"condition": "###"}}
        result = await execute_node(node, {})
        assert result["branch"] == "false"

    async def test_contains_operator(self):
        assert _safe_eval_condition('x contains "投诉"', {"x": "这是一条投诉"}) is True
        assert _safe_eval_condition('x contains "投诉"', {"x": "只是咨询"}) is False
        assert _safe_eval_condition('x contains "投诉" or x contains "建议"', {"x": "有建议"}) is True

    async def test_http_error_raises(self, monkeypatch):
        calls = {}

        class FakeResponse:
            status_code = 500
            text = "boom"
            is_error = True

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def request(self, method, url, headers=None, content=None):
                calls["method"] = method
                calls["url"] = url
                return FakeResponse()

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", FakeClient)
        node = {"id": "h1", "type": "http", "config": {"url": "https://x/y", "method": "PUT"}}
        result = await execute_node(node, {})
        assert calls["method"] == "PUT"
        assert result["status"] == "error"
        assert "500" in result["output"]

    async def test_http_headers_accept_json_string(self, monkeypatch):
        calls = {}

        class FakeResponse:
            status_code = 200
            text = "ok"
            is_error = False

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def request(self, method, url, headers=None, content=None):
                calls["headers"] = headers
                calls["content"] = content
                return FakeResponse()

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", FakeClient)
        node = {
            "id": "h2",
            "type": "http",
            "config": {"url": "https://x/y", "method": "POST", "headers": '{"A": "b"}', "body": "{{input}}"},
        }
        result = await execute_node(node, {"input": "payload"})
        assert result["status"] == "success"
        assert calls["headers"] == {"A": "b"}
        assert calls["content"] == b"payload"


class TestAsList:
    def test_plain_split(self):
        assert _as_list("a\nb\n c ", "\n") == ["a", "b", "c"]

    def test_json_array(self):
        assert _as_list('["a", "b", ""]', "\n") == ["a", "b"]

    def test_native_list(self):
        assert _as_list(["a", "b"], "\n") == ["a", "b"]

    def test_dict_becomes_pairs(self):
        assert _as_list({"a": 1}, "\n") == ["a: 1"]

    def test_empty(self):
        assert _as_list("", "\n") == []


class TestLoopNode:
    async def test_loop_collects_items_without_llm(self):
        node = {
            "id": "l1",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\n", "action": "collect", "join": "|"},
        }
        result = await execute_node(node, {"input": "a\nb\nc"})
        assert result["output"] == "a|b|c"

    async def test_loop_calls_llm_per_item_in_order(self, monkeypatch):
        import workflow_engine

        monkeypatch.setattr(workflow_engine, "call_llm", lambda prompt, model, temperature: prompt.upper())
        node = {
            "id": "l2",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\\n", "action": "llm", "prompt": "item={{item}}"},
        }
        result = await execute_node(node, {"input": "a\nb"})
        assert result["output"] == "ITEM=A\n\nITEM=B"

    async def test_loop_respects_max_items(self, monkeypatch):
        import workflow_engine

        monkeypatch.setattr(workflow_engine, "call_llm", lambda prompt, model, temperature: prompt)
        node = {
            "id": "l3",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\n", "action": "collect", "max_items": 2, "join": ","},
        }
        result = await execute_node(node, {"input": "a\nb\nc\nd"})
        assert result["output"] == "a,b"
        assert result["duration_ms"] >= 0

    async def test_loop_keeps_partial_failures(self, monkeypatch):
        import workflow_engine

        def flaky(prompt, model, temperature):
            if "b" in prompt:
                raise RuntimeError("quota")
            return prompt

        monkeypatch.setattr(workflow_engine, "call_llm", flaky)
        node = {
            "id": "l4",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\n", "prompt": "x {{item}}"},
        }
        result = await execute_node(node, {"input": "a\nb"})
        assert result["status"] == "success"
        assert "执行失败" in result["output"]
        assert "x a" in result["output"]

    async def test_loop_raises_when_every_item_fails(self, monkeypatch):
        import workflow_engine

        def boom(prompt, model, temperature):
            raise RuntimeError("no api key")

        monkeypatch.setattr(workflow_engine, "call_llm", boom)
        node = {
            "id": "l5",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\n", "prompt": "x"},
        }
        result = await execute_node(node, {"input": "a\nb"})
        assert result["status"] == "error"
        assert "全部失败" in result["output"]


class TestValidateWorkflow:
    def test_empty(self):
        assert validate_workflow([], []) == ["工作流为空，请先从左侧拖入节点"]

    def test_missing_start_and_end(self):
        problems = validate_workflow([{"id": "l", "type": "llm", "config": {"prompt": "x"}}], [])
        assert any("开始" in p for p in problems)
        assert any("结束" in p for p in problems)
        assert any("没有" in p for p in problems)

    def test_dangling_edge(self):
        nodes = [
            {"id": "start", "type": "start", "config": {}},
            {"id": "end", "type": "end", "config": {}},
        ]
        problems = validate_workflow(nodes, [{"source": "start", "target": "ghost"}])
        assert any("不存在" in p for p in problems)

    def test_valid_graph_has_no_problems(self):
        nodes = [
            {"id": "start", "type": "start", "config": {}},
            {"id": "c", "type": "condition", "config": {"condition": "input"}},
            {"id": "l1", "type": "llm", "config": {"prompt": "hi"}},
            {"id": "l2", "type": "llm", "config": {"prompt": "hi"}},
            {"id": "end", "type": "end", "config": {}},
        ]
        edges = [
            {"source": "start", "target": "c"},
            {"source": "c", "target": "l1", "sourcePort": "true"},
            {"source": "c", "target": "l2", "sourcePort": "false"},
            {"source": "l1", "target": "end"},
            {"source": "l2", "target": "end"},
        ]
        assert validate_workflow(nodes, edges) == []

    def test_missing_required_config(self):
        nodes = [
            {"id": "start", "type": "start", "config": {}},
            {"id": "c", "type": "condition", "config": {"condition": ""}},
            {"id": "end", "type": "end", "config": {}},
        ]
        edges = [
            {"source": "start", "target": "c"},
            {"source": "c", "target": "end", "sourcePort": "true"},
        ]
        problems = validate_workflow(nodes, edges)
        assert len(problems) == 1
        assert "未填写条件表达式" in problems[0]


class TestBranchRouting:
    def test_tagged_edges_are_filtered_by_branch(self):
        from main import _outgoing_edges, _skipped_edges

        edges = [
            {"source": "c", "target": "a", "sourcePort": "true"},
            {"source": "c", "target": "b", "sourcePort": "false"},
        ]
        assert _outgoing_edges(edges, "true") == [edges[0]]
        assert _skipped_edges(edges, "true") == [edges[1]]

    def test_legacy_untagged_edges_take_only_the_first(self):
        from main import _outgoing_edges

        edges = [{"source": "c", "target": "a"}, {"source": "c", "target": "b"}]
        assert _outgoing_edges(edges, "false") == [edges[0]]

    def test_non_branch_node_keeps_every_edge(self):
        from main import _outgoing_edges

        edges = [{"source": "x", "target": "a"}, {"source": "x", "target": "b"}]
        assert _outgoing_edges(edges, None) == edges
