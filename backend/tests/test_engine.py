from workflow_engine import _safe_eval_condition, execute_node, _replace_vars


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
