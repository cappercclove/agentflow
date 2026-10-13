from workflow_engine import (
    _as_list,
    _exec_loop,
    _replace_vars,
    _safe_eval_condition,
    execute_node,
    validate_graph_shape,
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

    def test_or_is_the_looser_operator(self):
        # Reads as "命中 x，或者 y 且 z 同时成立". x alone decides it, so a rule that
        # matched on x must still take the true branch.
        assert _safe_eval_condition("x or y and z", {"x": "yes", "y": "", "z": ""}) is True
        assert _safe_eval_condition("x or y and z", {"x": "", "y": "yes", "z": ""}) is False

    def test_and_binds_tighter_than_or(self):
        assert _safe_eval_condition("x and y or z", {"x": "yes", "y": "", "z": "yes"}) is True
        assert _safe_eval_condition("x and y or z", {"x": "yes", "y": "", "z": ""}) is False

    def test_contains_binds_tighter_than_or(self):
        assert _safe_eval_condition('a contains "x" or b', {"a": "example", "b": ""}) is True
        assert _safe_eval_condition('a contains "x" or b', {"a": "sample", "b": ""}) is False

    def test_empty_expr(self):
        assert _safe_eval_condition("", {}) is False

    def test_missing_var(self):
        assert _safe_eval_condition("x == 1", {}) is False

    def test_truthy_value(self):
        assert _safe_eval_condition("x", {"x": "hello"}) is True
        assert _safe_eval_condition("x", {"x": ""}) is False


class TestNumericConditionsOnText:
    def test_string_number_compares_as_number(self):
        # Node output is always text, so `score > 50` used to raise TypeError and the
        # node quietly took the false branch.
        assert _safe_eval_condition("score > 50", {"score": "100"}) is True
        assert _safe_eval_condition("score > 50", {"score": "9"}) is False
        assert _safe_eval_condition("score == 1", {"score": "1"}) is True
        assert _safe_eval_condition("score >= 3.5", {"score": "3.5"}) is True

    def test_text_against_text_is_untouched(self):
        assert _safe_eval_condition('name == "abc"', {"name": "abc"}) is True
        assert _safe_eval_condition("name == 1", {"name": "abc"}) is False

    def test_incomparable_text_still_raises(self):
        try:
            _safe_eval_condition("count > 5", {"count": "many"})
        except TypeError:
            return
        raise AssertionError("expected TypeError for text against a number")

    async def test_condition_note_reports_the_real_error(self):
        logged = []

        async def send_log(node_id, status, message):
            logged.append(message)

        result = await execute_node(
            {"id": "c", "type": "condition", "config": {"condition": "count > 5"}},
            {"count": "many"},
            send_log,
        )
        assert result["branch"] == "false"
        assert any("表达式无法求值" in m for m in logged)


class TestLlmEmptyResponse:
    def test_missing_content_raises_a_readable_error(self, monkeypatch):
        from types import SimpleNamespace
        import llm_client

        completions = SimpleNamespace(create=lambda **_kw: SimpleNamespace(choices=[]))
        monkeypatch.setattr(llm_client, "get_client", lambda model=None: SimpleNamespace(
            chat=SimpleNamespace(completions=completions)))

        try:
            llm_client.call_llm("hi")
        except RuntimeError as e:
            assert "没有返回内容" in str(e)
        else:
            raise AssertionError("an empty completion should not pass as an answer")

    def test_content_none_raises_too(self, monkeypatch):
        from types import SimpleNamespace
        import llm_client

        choice = SimpleNamespace(message=SimpleNamespace(content=None))
        completions = SimpleNamespace(create=lambda **_kw: SimpleNamespace(choices=[choice]))
        monkeypatch.setattr(llm_client, "get_client", lambda model=None: SimpleNamespace(
            chat=SimpleNamespace(completions=completions)))

        try:
            llm_client.call_llm("hi")
        except RuntimeError:
            return
        raise AssertionError("content=None should not pass as an answer")


class TestModelAliases:
    def test_a_tier_can_point_at_another_model_id(self, monkeypatch):
        from types import SimpleNamespace
        import llm_client

        asked = {}

        def create(model=None, **_kw):
            asked["model"] = model
            choice = SimpleNamespace(message=SimpleNamespace(content=" 收到 "))
            return SimpleNamespace(choices=[choice])

        monkeypatch.setattr(llm_client, "get_client", lambda model=None: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        monkeypatch.setenv("BAILIAN_MODEL_TURBO", "qwen-flash")

        assert llm_client.call_llm("hi", "qwen-turbo") == "收到"
        assert asked["model"] == "qwen-flash"

    def test_unset_overrides_keep_the_public_names(self, monkeypatch):
        import llm_client

        for name in ("BAILIAN_MODEL", "BAILIAN_MODEL_TURBO", "BAILIAN_MODEL_MAX"):
            monkeypatch.delenv(name, raising=False)
        assert llm_client._get_model_map() == {
            "qwen-plus": "qwen-plus", "qwen-turbo": "qwen-turbo", "qwen-max": "qwen-max"}


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

    def test_substituted_text_is_not_scanned_again(self):
        # An upstream node that echoes a template must not pull in a value that
        # belongs to a different node, and the result cannot depend on dict order.
        assert _replace_vars("{{p}}", {"p": "{{q}}", "q": "LEAKED"}) == "{{q}}"
        assert _replace_vars("{{p}}", {"q": "LEAKED", "p": "{{q}}"}) == "{{q}}"

    def test_unknown_placeholder_stays(self):
        assert _replace_vars("{{missing}} tail", {"other": "x"}) == "{{missing}} tail"


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
        assert result["status"] == "error"
        assert "未知" in result["output"]

    async def test_node_that_is_not_an_object(self):
        result = await execute_node("start", {})
        assert result["status"] == "error"

    async def test_text_config_that_is_not_an_object(self, monkeypatch):
        # Used to raise AttributeError, which surfaced as a 500 on 检查 and 运行.
        import workflow_engine

        monkeypatch.setattr(workflow_engine, "call_llm", lambda prompt, model, temperature: "OK")
        node = {"id": "l1", "type": "llm", "config": "prompt = hi"}
        assert validate_workflow(
            [{"id": "s", "type": "start"}, node, {"id": "e", "type": "end"}],
            [{"source": "s", "target": "l1"}, {"source": "l1", "target": "e"}],
        )
        result = await execute_node(node, {})
        assert result["status"] == "success"
        assert result["output"] == "OK"

    async def test_llm_prompt_that_is_not_a_string_is_rendered_as_json(self, monkeypatch):
        import workflow_engine

        seen = {}

        def capture(prompt, model, temperature):
            seen["prompt"] = prompt
            return "OK"

        monkeypatch.setattr(workflow_engine, "call_llm", capture)
        await execute_node({"id": "l2", "type": "llm", "config": {"prompt": ["a", "b"]}}, {})
        assert seen["prompt"] == '["a", "b"]'

    async def test_llm_temperature_is_not_passed_through_broken(self, monkeypatch):
        import workflow_engine

        seen = {}

        def capture(prompt, model, temperature):
            seen["temperature"] = temperature
            return "OK"

        monkeypatch.setattr(workflow_engine, "call_llm", capture)
        await execute_node({"id": "l3", "type": "llm", "config": {"prompt": "x", "temperature": "hot"}}, {})
        assert seen["temperature"] == 0.7
        await execute_node({"id": "l4", "type": "llm", "config": {"prompt": "x", "temperature": -5}}, {})
        assert seen["temperature"] == 0
        await execute_node({"id": "l5", "type": "llm", "config": {"prompt": "x", "temperature": 9}}, {})
        assert seen["temperature"] == 2

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

    async def test_an_answer_that_opens_like_a_failure_is_not_one(self, monkeypatch):
        import workflow_engine

        monkeypatch.setattr(
            workflow_engine, "call_llm",
            lambda prompt, model, temperature: "[第 1 项] 是正确答案",
        )
        node = {
            "id": "l6",
            "type": "loop",
            "config": {"source": "{{input}}", "separator": "\n", "prompt": "x {{item}}"},
        }
        result = await _exec_loop(node, {"input": "a\nb"})
        assert "1 项失败" not in result["note"]
        assert result["output"] == "[第 1 项] 是正确答案\n\n[第 1 项] 是正确答案"


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


class TestGraphShapeValidation:
    def test_empty_or_wrong_container(self):
        assert validate_graph_shape([], []) == ["文件里没有节点"]
        assert validate_graph_shape("start", []) == ["文件里没有节点"]

    def test_draft_without_start_end_is_accepted(self):
        nodes = [{"id": "a", "type": "llm"}, {"id": "b", "type": "end"}]
        assert validate_graph_shape(nodes, [{"source": "a", "target": "b"}]) == []

    def test_missing_id_and_type_are_located_by_position(self):
        problems = validate_graph_shape([{"type": "llm"}, {"id": "a"}], [])
        assert "第 1 个节点缺少 id" in problems
        assert "节点「a」缺少 type" in problems

    def test_a_node_with_neither_id_nor_type_names_both(self):
        problems = validate_graph_shape([{}], [])
        assert "第 1 个节点缺少 id" in problems
        assert "节点「1」缺少 type" in problems

    def test_duplicate_ids(self):
        problems = validate_graph_shape([{"id": "a", "type": "llm"}, {"id": "a", "type": "end"}], [])
        assert any("重复" in p for p in problems)

    def test_edges_must_point_at_real_nodes(self):
        nodes = [{"id": "a", "type": "llm"}]
        problems = validate_graph_shape(nodes, [{"source": "a", "target": "ghost"}])
        assert problems == ["第 1 条连线的 target 指向不存在的节点: ghost"]

    def test_non_object_entries(self):
        problems = validate_graph_shape(["start"], "not-a-list")
        assert "第 1 个节点不是对象" in problems
        assert "edges 必须是数组" in problems

    def test_hostile_id_is_rejected(self):
        # The editor drops ids into CSS selectors, data attributes and inline
        # handlers, so an imported file must not be able to carry quoting chars.
        for bad in ["x',alert(1),'", 'a" onload="alert(1)', "节点", "1abc", "a" * 100]:
            problems = validate_graph_shape([{"id": bad, "type": "llm"}], [])
            assert any("节点 ID 只能用" in p for p in problems), bad

    def test_ordinary_ids_pass(self):
        ids = ["start", "end", "llm_1", "cond-2", "_x", "text_1760000000000"]
        nodes = [{"id": i, "type": "llm"} for i in ids]
        edges = [{"source": ids[0], "target": ids[1]}]
        assert validate_graph_shape(nodes, edges) == []


class TestMissingIdGuard:
    def test_validate_reports_nodes_without_id(self):
        problems = validate_workflow(
            [{"type": "start"}, {"type": "end", "config": {}}],
            [],
        )
        assert any("缺少 id" in p for p in problems)

    def test_validate_survives_junk_entries(self):
        # A workflow row can hold anything, and validate runs before every execute:
        # this used to raise AttributeError instead of reporting a problem.
        assert validate_workflow(["start", 3], []) == ["第 1 个节点不是对象", "第 2 个节点不是对象"]
        assert validate_workflow([{"id": "a", "type": "start"}], ["x"]) == ["第 1 条连线不是对象"]


class TestNodeGuards:
    """Everything a hand-written or stale graph can put in a node field."""

    async def test_text_node_treats_a_bare_string_as_one_item(self):
        # Iterating a str used to feed one character at a time into the operation,
        # so 「hello」 split into five pieces and a dict concatenated its keys.
        result = await execute_node(
            {"id": "t1", "type": "text", "config": {"operation": "split", "texts": "a,b,c", "separator": ","}},
            {},
        )
        assert result["output"] == ["a", "b", "c"]

    async def test_text_node_rejects_a_mapping_for_texts(self):
        result = await execute_node(
            {"id": "t2", "type": "text", "config": {"operation": "concat", "texts": {"a": "1", "b": "2"}}},
            {},
        )
        assert result["status"] == "error"
        assert "数组" in result["output"]

    async def test_text_node_renders_non_string_items(self):
        result = await execute_node(
            {"id": "t3", "type": "text", "config": {"operation": "concat", "texts": [1, {"k": "v"}, None]}},
            {},
        )
        assert result["output"] == '1{"k": "v"}'

    async def test_node_must_be_an_object_to_run(self):
        result = await execute_node("just a string", {})
        assert result["status"] == "error"
        assert "不是对象" in result["output"]

    def test_shape_check_requires_a_dict_config(self):
        problems = validate_graph_shape([{"id": "a", "type": "llm", "config": "oops"}], [])
        assert any("config 不是对象" in p for p in problems)

    def test_shape_check_requires_numeric_coordinates(self):
        for bad in ["NaN", "100", None, [1]]:
            problems = validate_graph_shape([{"id": "a", "type": "llm", "x": bad, "y": 1}], [])
            assert any("坐标 x 不是数字" in p for p in problems), bad

    def test_shape_check_accepts_a_missing_position(self):
        assert validate_graph_shape([{"id": "a", "type": "llm"}], []) == []

    def test_shape_check_allows_an_empty_canvas(self):
        assert validate_graph_shape([], [], allow_empty=True) == []
        assert validate_graph_shape([], []) == ["文件里没有节点"]

    async def test_http_node_blocks_the_cloud_metadata_address(self, monkeypatch):
        attempted = {}

        class ExplodingClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                raise AssertionError("the request must never leave for a metadata address")

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", ExplodingClient)
        for url in ["http://169.254.169.254/latest/meta-data/", "http://100.100.100.200/latest/"]:
            result = await execute_node({"id": "h", "type": "http", "config": {"url": url}}, {})
            assert result["status"] == "error"
            assert "元数据" in result["output"]
        assert not attempted

    async def test_http_node_caps_the_stored_response(self, monkeypatch):
        import workflow_engine

        class BigResponse:
            status_code = 200
            text = "x" * (workflow_engine.MAX_HTTP_OUTPUT_CHARS + 5000)
            is_error = False

        class BigClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def request(self, method, url, headers=None, content=None):
                return BigResponse()

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", BigClient)
        logged = []

        async def capture_log(node_id, status, message):
            logged.append(message)

        result = await execute_node({"id": "h2", "type": "http", "config": {"url": "https://x/y"}},
                                    {}, send_log=capture_log)
        assert len(result["output"]) == workflow_engine.MAX_HTTP_OUTPUT_CHARS
        assert any("截断" in m for m in logged)

    async def test_http_node_accepts_a_url_that_is_not_a_string(self, monkeypatch):
        seen = {}

        class OkResponse:
            status_code = 200
            text = "fine"
            is_error = False

        class OkClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def request(self, method, url, headers=None, content=None):
                seen["url"] = url
                return OkResponse()

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", OkClient)
        result = await execute_node({"id": "h3", "type": "http", "config": {"url": " https://x/y "}}, {})
        assert seen["url"] == "https://x/y"
        assert result["status"] == "success"


class TestTextFieldGuards:
    """A number where the engine needs text used to leak str's own TypeError."""

    async def test_loop_join_names_the_field_instead_of_crashing(self):
        result = await execute_node(
            {"id": "l", "type": "loop", "config": {"source": "{{input}}", "action": "collect", "join": 5}},
            {"input": "a\nb"},
        )
        assert result["status"] == "error"
        assert "结果连接符" in result["output"]
        assert "int" in result["output"]

    async def test_loop_separator_names_the_field_instead_of_crashing(self):
        result = await execute_node(
            {"id": "l", "type": "loop", "config": {"source": "{{input}}", "action": "collect", "separator": [","]}},
            {"input": "a,b"},
        )
        assert result["status"] == "error"
        assert "「分隔符」需要是文本" in result["output"]

    async def test_text_split_separator_is_reported_per_node(self):
        result = await execute_node(
            {"id": "t", "type": "text", "config": {"operation": "split", "texts": ["{{input}}"], "separator": 1}},
            {"input": "a b"},
        )
        assert result["status"] == "error"
        assert "分隔符" in result["output"]

    async def test_text_replace_pair_must_be_text(self):
        result = await execute_node(
            {"id": "t", "type": "text",
             "config": {"operation": "replace", "texts": ["abc"], "old": 1, "new": "x"}},
            {},
        )
        assert result["status"] == "error"
        assert "查找" in result["output"]

    async def test_missing_separator_still_uses_the_default(self):
        result = await execute_node(
            {"id": "l", "type": "loop", "config": {"source": "{{input}}", "action": "collect", "join": None}},
            {"input": "a\nb"},
        )
        assert result["output"] == "a\n\nb"

    async def test_http_headers_of_an_unusable_type_are_refused(self, monkeypatch):
        class ExplodingClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                raise AssertionError("the request must not go out with headers the panel cannot show")

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr("workflow_engine.httpx.AsyncClient", ExplodingClient)
        for bad in [123, True, ["a=b"]]:
            result = await execute_node(
                {"id": "h", "type": "http", "config": {"url": "https://x/y", "headers": bad}}, {})
            assert result["status"] == "error", bad
            assert "请求头" in result["output"], bad

    async def test_empty_headers_stay_quiet(self):
        from workflow_engine import _as_headers

        assert _as_headers(None) == {}
        assert _as_headers("") == {}
        assert _as_headers({}) == {}


class TestRequiredConfigPresence:
    def test_an_explicit_null_counts_as_missing(self):
        # str(None) is "None", so this passed 检查 and then asked the model for nothing.
        nodes = [
            {"id": "start", "type": "start", "config": {}},
            {"id": "c", "type": "condition", "config": {"condition": None}},
            {"id": "l", "type": "llm", "config": {"prompt": None}},
            {"id": "end", "type": "end", "config": {}},
        ]
        edges = [
            {"source": "start", "target": "c"},
            {"source": "c", "target": "l", "sourcePort": "true"},
            {"source": "l", "target": "end"},
        ]
        problems = validate_workflow(nodes, edges)
        assert any("未填写条件表达式" in p for p in problems)
        assert any("未填写提示词" in p for p in problems)


class TestLlmFailureMessages:
    def test_a_number_for_the_model_falls_back_to_the_default_tier(self, monkeypatch):
        from types import SimpleNamespace
        import llm_client

        asked = {}

        def create(model=None, **_kw):
            asked["model"] = model
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

        monkeypatch.setattr(llm_client, "get_client", lambda model=None: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        for bad in [12, None, "  "]:
            assert llm_client.call_llm("hi", bad) == "ok"
            assert asked["model"] == "qwen-plus", bad

    def test_an_empty_prompt_is_refused_before_the_request(self, monkeypatch):
        import llm_client

        monkeypatch.setattr(llm_client, "get_client",
                            lambda model=None: (_ for _ in ()).throw(AssertionError("no call expected")))
        for bad in ["", "   ", None]:
            try:
                llm_client.call_llm(bad)
            except ValueError as e:
                assert "提示词为空" in str(e)
            else:
                raise AssertionError(f"prompt {bad!r} should not reach the provider")

    def test_a_connection_failure_is_explained_in_chinese(self, monkeypatch):
        from types import SimpleNamespace
        import httpx
        import llm_client
        from openai import APIConnectionError

        def boom(**_kw):
            raise APIConnectionError(request=httpx.Request("POST", "https://x/y"))

        monkeypatch.setattr(llm_client, "get_client", lambda model=None: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=boom))))
        try:
            llm_client.call_llm("hi")
        except RuntimeError as e:
            assert "无法连接大模型服务" in str(e)
        else:
            raise AssertionError("a dead endpoint should raise a readable error")
