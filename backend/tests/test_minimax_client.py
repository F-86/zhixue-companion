"""
MiniMax 客户端完整测试。

测试目标：
  - embed_texts / embed_query：批量 & 单条向量化，含多种返回格式兼容
  - _chat / _chat_stream：底层同步 & 流式请求
  - answer_question / answer_question_stream：智能问答（含 RAG 上下文）
  - generate_summary：知识点总结
  - generate_learning_plan / adjust_learning_plan：学习计划生成与调整
  - grade_quiz_answer：简答题批改
  - grade_submission：作业批改
  - analyze_submissions：查重与比对分析
  - _parse_json：JSON 解析（含 markdown 包裹、截断修复）

外部 HTTP 调用全部 Mock，不产生任何网络请求。
"""
import json

import httpx
import pytest

from app.services import minimax_client


# ═══════════════════════════════════════════════════════════════
# _parse_json 测试
# ═══════════════════════════════════════════════════════════════

class TestParseJson:
    def test_valid_json_object(self):
        result = minimax_client._parse_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_valid_json_array(self):
        result = minimax_client._parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_markdown_code_block(self):
        text = '```json\n{"answer": "你好", "suggestions": ["多练习"]}\n```'
        result = minimax_client._parse_json(text)
        assert result["answer"] == "你好"

    def test_markdown_code_block_no_lang(self):
        text = '```\n{"result": true}\n```'
        result = minimax_client._parse_json(text)
        assert result["result"] is True

    def test_code_block_single_line_wrapping(self):
        text = '```{"key": 1}```'
        result = minimax_client._parse_json(text)
        assert result == {"key": 1}

    def test_truncated_json_repaired(self):
        """末尾截断的 JSON（缺 }）应自动补全。"""
        text = '{"name": "张三", "scores": [95, 88, 72]'
        result = minimax_client._parse_json(text)
        assert result["name"] == "张三"
        assert result["scores"] == [95, 88, 72]

    def test_nested_truncated_json_repaired(self):
        text = '{"outer": {"inner": {"deep": "value"'
        result = minimax_client._parse_json(text)
        assert result["outer"]["inner"]["deep"] == "value"

    def test_raises_on_unparseable(self):
        with pytest.raises(ValueError, match="无法解析 JSON"):
            minimax_client._parse_json("这不是 JSON 内容，完全是乱码 ###")

    def test_leading_trailing_whitespace(self):
        result = minimax_client._parse_json('  \n  {"ok": true}  \n  ')
        assert result == {"ok": True}


# ═══════════════════════════════════════════════════════════════
# _chat 测试
# ═══════════════════════════════════════════════════════════════

class TestChat:
    def test_returns_content_on_success(self, mocker):
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": "这是 AI 的回复"}}],
        }
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        result = minimax_client._chat("系统提示", "用户问题")
        assert result == "这是 AI 的回复"

    def test_raises_on_http_error(self, mocker):
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mocker.MagicMock(), response=mocker.MagicMock(status_code=500)
        )
        mocker.patch.object(minimax_client, "_get_client", return_value=mocker.MagicMock(post=mocker.MagicMock(return_value=fake_resp)))

        with pytest.raises(RuntimeError, match="大模型服务异常"):
            minimax_client._chat("系统", "用户")

    def test_raises_on_network_error(self, mocker):
        mock_client = mocker.MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("连接超时")
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        with pytest.raises(RuntimeError, match="大模型服务不可用"):
            minimax_client._chat("系统", "用户")

    def test_passes_temperature(self, mocker):
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        minimax_client._chat("sys", "user", temperature=0.3)
        call_payload = mock_client.post.call_args[1]["json"]
        assert call_payload["temperature"] == 0.3


# ═══════════════════════════════════════════════════════════════
# _chat_stream 测试
# ═══════════════════════════════════════════════════════════════

class TestChatStream:
    def test_yields_delta_chunks(self, mocker):
        lines = [
            'data: {"choices":[{"delta":{"content":"你好"}}]}',
            'data: {"choices":[{"delta":{"content":"，"}}]}',
            'data: {"choices":[{"delta":{"content":"世界"}}]}',
            'data: [DONE]',
        ]

        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status = mocker.MagicMock()
        mock_resp.iter_lines.return_value = lines
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)

        mock_client = mocker.MagicMock()
        mock_client.stream.return_value = mock_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        chunks = list(minimax_client._chat_stream("sys", "user"))
        assert "".join(chunks) == "你好，世界"

    def test_skips_empty_delta(self, mocker):
        lines = [
            'data: {"choices":[{"delta":{"content":""}}]}',
            'data: {"choices":[{"delta":{"content":"有效内容"}}]}',
            'data: [DONE]',
        ]
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status = mocker.MagicMock()
        mock_resp.iter_lines.return_value = lines
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mock_client = mocker.MagicMock()
        mock_client.stream.return_value = mock_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        chunks = list(minimax_client._chat_stream("sys", "user"))
        assert "".join(chunks) == "有效内容"

    def test_ignores_invalid_json_lines(self, mocker):
        lines = [
            'data: 这不是有效的 JSON',
            'data: {"choices":[{"delta":{"content":"hello"}}]}',
            'data: [DONE]',
        ]
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status = mocker.MagicMock()
        mock_resp.iter_lines.return_value = lines
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mock_client = mocker.MagicMock()
        mock_client.stream.return_value = mock_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        chunks = list(minimax_client._chat_stream("sys", "user"))
        assert "".join(chunks) == "hello"

    def test_raises_on_http_error(self, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mocker.MagicMock(), response=mocker.MagicMock(status_code=503)
        )
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mock_client = mocker.MagicMock()
        mock_client.stream.return_value = mock_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        with pytest.raises(RuntimeError, match="大模型服务异常"):
            list(minimax_client._chat_stream("sys", "user"))


# ═══════════════════════════════════════════════════════════════
# embed_texts / embed_query 测试
# ═══════════════════════════════════════════════════════════════

class TestEmbedTexts:
    def test_empty_list_returns_empty(self):
        assert minimax_client.embed_texts([]) == []

    def test_format_a_data(self, mocker):
        """OpenAI-like 格式：{"data": [{"embedding": [...], "index": 0}, ...]}"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 1},
                {"embedding": [0.4, 0.5, 0.6], "index": 0},
            ]
        }
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        result = minimax_client.embed_texts(["text A", "text B"])
        # 应按 index 排序：index 0 → index 1
        assert result == [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]

    def test_format_b_vectors(self, mocker):
        """格式 B：{"vectors": [[...], ...]}"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {
            "vectors": [[0.1, 0.2], [0.3, 0.4]],
        }
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        result = minimax_client.embed_texts(["text A", "text B"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_default_type_is_db(self, mocker):
        """默认 text_type 应为 'db'。"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {"vectors": [[0.1]]}
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        minimax_client.embed_texts(["test"])
        call_payload = mock_client.post.call_args[1]["json"]
        assert call_payload["type"] == "db"

    def test_query_type(self, mocker):
        """embed_query 应使用 type='query'。"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {"vectors": [[0.1]]}
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        minimax_client.embed_query("查询文本")
        call_payload = mock_client.post.call_args[1]["json"]
        assert call_payload["type"] == "query"

    def test_batches_large_inputs(self, mocker):
        """超过 _EMBED_BATCH_SIZE 的输入应分批请求。"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {"vectors": [[0.1]]}
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        # 构造超过一批的文本列表
        batch_size = minimax_client._EMBED_BATCH_SIZE
        texts = ["text"] * (batch_size + 5)

        minimax_client.embed_texts(texts)
        # 应调用 post 两次
        assert mock_client.post.call_count >= 2

    def test_raises_on_unknown_format(self, mocker):
        """返回格式既无 data 也无 vectors 时应抛出 RuntimeError。"""
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {"unexpected_key": "value"}
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        with pytest.raises(RuntimeError, match="格式未知"):
            minimax_client.embed_texts(["test"])

    def test_raises_on_http_error(self, mocker):
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mocker.MagicMock(), response=mocker.MagicMock(status_code=401)
        )
        mocker.patch.object(minimax_client, "_get_client", return_value=mocker.MagicMock(post=mocker.MagicMock(return_value=fake_resp)))

        with pytest.raises(RuntimeError, match="Embedding 服务异常"):
            minimax_client.embed_texts(["test"])


class TestEmbedQuery:
    def test_returns_single_vector(self, mocker):
        fake_resp = mocker.MagicMock()
        fake_resp.raise_for_status = mocker.MagicMock()
        fake_resp.json.return_value = {"vectors": [[0.1, 0.2, 0.3]]}
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = fake_resp
        mocker.patch.object(minimax_client, "_get_client", return_value=mock_client)

        result = minimax_client.embed_query("查询文本")
        assert result == [0.1, 0.2, 0.3]


# ═══════════════════════════════════════════════════════════════
# answer_question 测试
# ═══════════════════════════════════════════════════════════════

class TestAnswerQuestion:
    def test_returns_answer_and_suggestions(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "answer": "进程有五种状态。",
            "suggestions": ["复习课件第一章", "做练习题巩固"],
        }))

        result = minimax_client.answer_question(
            "进程有哪些状态？", "操作系统", [], ""
        )
        assert result["answer"] == "进程有五种状态。"
        assert len(result["suggestions"]) == 2

    def test_includes_course_context_in_prompt(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "answer": "ok", "suggestions": [],
        }))

        minimax_client.answer_question("问题？", "操作系统", [], "进程管理是核心概念。")
        call_args = mock_chat.call_args[0]
        system_prompt = call_args[0]
        assert "操作系统" in system_prompt
        assert "进程管理是核心概念" in system_prompt

    def test_includes_history_in_user_content(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "answer": "ok", "suggestions": [],
        }))
        history = [
            {"role": "user", "content": "什么是进程？"},
            {"role": "assistant", "content": "进程是运行中的程序。"},
        ]

        minimax_client.answer_question("那线程呢？", "操作系统", history, "")
        user_content = mock_chat.call_args[0][1]
        assert "什么是进程？" in user_content
        assert "进程是运行中的程序" in user_content

    def test_fallback_on_json_parse_error(self, mocker):
        """JSON 解析失败时返回原始文本作为 answer，suggestions 为空列表。"""
        mocker.patch.object(minimax_client, "_chat", return_value="这不是 JSON，是纯文本回答。")

        result = minimax_client.answer_question("问题？", None, [], "")
        assert result["answer"] == "这不是 JSON，是纯文本回答。"
        assert result["suggestions"] == []

    def test_no_course_and_no_history(self, mocker):
        """无课程、无历史的最简调用。"""
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "answer": "你好！", "suggestions": ["多读书"],
        }))
        result = minimax_client.answer_question("你好", None, [], "")
        assert result["answer"] == "你好！"


# ═══════════════════════════════════════════════════════════════
# answer_question_stream 测试
# ═══════════════════════════════════════════════════════════════

class TestAnswerQuestionStream:
    def test_yields_chunks_from_stream(self, mocker):
        def fake_stream(system, user, temperature=None):
            yield "进程"
            yield "有"
            yield "五种状态。"

        mocker.patch.object(minimax_client, "_chat_stream", side_effect=fake_stream)

        chunks = list(minimax_client.answer_question_stream("问题？", "操作系统", [], ""))
        assert "".join(chunks) == "进程有五种状态。"

    def test_includes_course_and_context_in_stream(self, mocker):
        mock_stream = mocker.patch.object(minimax_client, "_chat_stream", return_value=iter(["test"]))

        list(minimax_client.answer_question_stream("问题？", "数学", [], "向量基础"))
        system_prompt = mock_stream.call_args[0][0]
        assert "数学" in system_prompt
        assert "向量基础" in system_prompt

    def test_empty_history_and_course(self, mocker):
        mocker.patch.object(minimax_client, "_chat_stream", return_value=iter(["ok"]))
        chunks = list(minimax_client.answer_question_stream("hi", None, [], ""))
        assert "".join(chunks) == "ok"


# ═══════════════════════════════════════════════════════════════
# generate_summary 测试
# ═══════════════════════════════════════════════════════════════

class TestGenerateSummary:
    def test_structured_summary(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "overview": "本章介绍了进程管理的核心概念。",
            "key_points": ["进程定义", "状态转换", "调度算法"],
            "difficult_points": ["阻塞态与就绪态的转换条件"],
            "review_tips": ["画出状态转换图", "对比不同调度算法"],
        }))

        result = minimax_client.generate_summary(
            "第一章", "进程管理内容...", "structured", "操作系统"
        )
        assert result["overview"] == "本章介绍了进程管理的核心概念。"
        assert len(result["key_points"]) == 3
        assert len(result["difficult_points"]) == 1
        assert len(result["review_tips"]) == 2

    def test_brief_summary_type(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "overview": "简要概述。",
            "key_points": ["要点1"],
            "difficult_points": [],
            "review_tips": [],
        }))
        result = minimax_client.generate_summary("标题", "内容", "brief", None)
        assert result["overview"] == "简要概述。"

    def test_review_summary_type(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "overview": "复习清单概述。",
            "key_points": [],
            "difficult_points": [],
            "review_tips": ["建议1", "建议2"],
        }))
        result = minimax_client.generate_summary("标题", "内容", "review", None)
        assert result["overview"] == "复习清单概述。"

    def test_fallback_on_parse_error(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value="纯文本总结内容。")
        result = minimax_client.generate_summary("标题", "内容", "structured", None)
        assert result["overview"] == "纯文本总结内容。"
        assert result["key_points"] == []

    def test_includes_course_in_prompt(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "overview": "ok", "key_points": [], "difficult_points": [], "review_tips": [],
        }))
        minimax_client.generate_summary("标题", "内容", "structured", "操作系统")
        assert "操作系统" in mock_chat.call_args[0][0]


# ═══════════════════════════════════════════════════════════════
# generate_learning_plan 测试
# ═══════════════════════════════════════════════════════════════

class TestGenerateLearningPlan:
    def test_returns_analysis_and_plan(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "analysis": {
                "current_level": "中等",
                "weak_points": ["进程调度", "内存分页"],
                "priority": "先复习进程调度",
            },
            "plan": [
                {"day": 1, "task": "复习进程管理", "duration_minutes": 60},
                {"day": 2, "task": "做练习题", "duration_minutes": 45},
            ],
        }))

        basis = {"avg_score": 72, "completed_assignments": 5}
        result = minimax_client.generate_learning_plan(
            "操作系统", "期末考试 90 分", basis, 120
        )
        assert result["analysis"]["current_level"] == "中等"
        assert len(result["plan"]) == 2
        assert result["plan"][0]["day"] == 1

    def test_fallback_on_parse_error(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value="无法解析的计划文本")
        result = minimax_client.generate_learning_plan("课程", "目标", {}, 60)
        assert result == {"analysis": {}, "plan": []}

    def test_includes_all_params_in_user_prompt(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "analysis": {}, "plan": [],
        }))
        minimax_client.generate_learning_plan("操作系统", "90分", {"score": 80}, 90)
        user_content = mock_chat.call_args[0][1]
        assert "操作系统" in user_content
        assert "90分" in user_content
        assert "90" in user_content  # available_minutes


# ═══════════════════════════════════════════════════════════════
# grade_quiz_answer 测试
# ═══════════════════════════════════════════════════════════════

class TestGradeQuizAnswer:
    def test_returns_score_and_feedback(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "score": 8.0,
            "feedback": "回答基本正确，但缺少对具体条件的说明。",
        }))

        result = minimax_client.grade_quiz_answer(
            "什么是进程？", "进程是程序执行的实体。", "进程是运行的程序。", 10.0
        )
        assert result["score"] == 8.0
        assert "具体条件" in result["feedback"]

    def test_clamps_score_to_max(self, mocker):
        """AI 给出的分数不应超过满分。"""
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "score": 15.0,  # 超过满分 10
            "feedback": "很好",
        }))
        result = minimax_client.grade_quiz_answer("题目", "答案", "学生答案", 10.0)
        assert result["score"] <= 10.0

    def test_fallback_on_parse_error(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value="回答不够全面，建议补充。")
        result = minimax_client.grade_quiz_answer("Q", "A", "SA", 10.0)
        assert result["score"] == 0.0
        assert isinstance(result["feedback"], str)

    def test_uses_low_temperature(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "score": 7, "feedback": "ok",
        }))
        minimax_client.grade_quiz_answer("Q", "A", "SA", 10.0)
        assert mock_chat.call_args[1]["temperature"] == 0.3


# ═══════════════════════════════════════════════════════════════
# grade_submission 测试
# ═══════════════════════════════════════════════════════════════

class TestGradeSubmission:
    def test_with_reference_and_rubric(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "ai_score": 85.0,
            "comments": "整体思路正确，概念解释较完整。",
            "deductions": [{"point": "缺少案例分析", "minus": 10}],
            "suggestions": ["补充一个实际案例"],
        }))

        result = minimax_client.grade_submission(
            "学生作业内容...",
            "参考答案：应当包含A、B、C三点。",
            "概念 40 分，分析 30 分，表达 30 分。",
            100.0,
        )
        assert result["ai_score"] == 85.0
        assert len(result["deductions"]) == 1
        assert result["deductions"][0]["minus"] == 10

    def test_without_reference_answer(self, mocker):
        """无参考答案时仍应独立评价。"""
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "ai_score": 70.0,
            "comments": "内容较为全面，但逻辑结构有待加强。",
            "deductions": [],
            "suggestions": ["建议先列提纲再展开", "多用具体数据支撑"],
        }))

        result = minimax_client.grade_submission(
            "学生作业内容...", "（无参考答案）", "", 100.0
        )
        assert result["ai_score"] == 70.0
        assert len(result["suggestions"]) == 2

    def test_clamps_score_to_max(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "ai_score": 120.0, "comments": "很好", "deductions": [], "suggestions": [],
        }))
        result = minimax_client.grade_submission("内容", "答案", "标准", 50.0)
        assert result["ai_score"] <= 50.0

    def test_fallback_on_parse_error(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value="这篇作业写得很好，但缺少深度分析。")
        result = minimax_client.grade_submission("内容", "答案", "标准", 100.0)
        assert result["ai_score"] == 0.0
        assert "作业" in result["comments"]

    def test_uses_low_temperature(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "ai_score": 80, "comments": "ok", "deductions": [], "suggestions": [],
        }))
        minimax_client.grade_submission("c", "r", "u", 100)
        assert mock_chat.call_args[1]["temperature"] == 0.3


# ═══════════════════════════════════════════════════════════════
# adjust_learning_plan 测试
# ═══════════════════════════════════════════════════════════════

class TestAdjustLearningPlan:
    def test_returns_adjusted_plan(self, mocker):
        original_plan = [
            {"day": 1, "task": "复习进程管理", "duration_minutes": 60},
            {"day": 2, "task": "做练习题", "duration_minutes": 45},
            {"day": 3, "task": "复习内存管理", "duration_minutes": 60},
        ]
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "analysis": {
                "adjustment_reason": "学生进程管理已掌握，跳至内存管理",
                "completed_days": [1],
                "remaining_days": 2,
            },
            "plan": [
                {"day": 1, "task": "复习进程管理（已完成）", "duration_minutes": 60},
                {"day": 2, "task": "复习内存管理（提前）", "duration_minutes": 60},
                {"day": 3, "task": "做综合练习", "duration_minutes": 60},
            ],
        }))

        progress = [{"day": 1, "completed": True, "feedback": "已掌握进程管理"}]
        result = minimax_client.adjust_learning_plan(
            "操作系统", original_plan, progress, "进程管理已经学会了，可以提前学内存管理。", 90
        )
        assert "analysis" in result
        assert len(result["plan"]) == 3

    def test_fallback_on_parse_error(self, mocker):
        original = [{"day": 1, "task": "任务1"}]
        mocker.patch.object(minimax_client, "_chat", return_value="无法生成新计划")
        result = minimax_client.adjust_learning_plan("课程", original, [], "无反馈", 60)
        assert result["plan"] == original  # 应保留原计划

    def test_includes_all_params_in_prompt(self, mocker):
        original = [{"day": 1, "task": "复习", "duration_minutes": 30}]
        progress = [{"day": 1, "completed": True, "feedback": "懂了"}]
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "analysis": {}, "plan": original,
        }))

        minimax_client.adjust_learning_plan("数学", original, progress, "太简单了", 60)
        user_content = mock_chat.call_args[0][1]
        assert "数学" in user_content
        assert "太简单了" in user_content


# ═══════════════════════════════════════════════════════════════
# analyze_submissions 测试
# ═══════════════════════════════════════════════════════════════

class TestAnalyzeSubmissions:
    def test_with_suspect_pairs(self, mocker):
        submissions = [
            {"id": "s1", "student_name": "张三", "text": "进程状态包括..."},
            {"id": "s2", "student_name": "李四", "text": "进程状态有..."},
        ]
        suspect_pairs = [(0, 1, 0.92)]
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "suspicious_pairs": [
                {
                    "submission_a": "s1", "student_a": "张三",
                    "submission_b": "s2", "student_b": "李四",
                    "similarity": 0.92, "risk_level": "high",
                    "similar_segments": ["进程状态描述高度一致"],
                    "ai_reason": "多段表述高度相似",
                }
            ],
            "comparison_details": [],
            "common_issues": ["缺乏案例分析"],
            "teaching_suggestions": ["强调独立完成"],
        }))

        result = minimax_client.analyze_submissions(
            submissions, suspect_pairs, ["structure", "concept"]
        )
        assert len(result["suspicious_pairs"]) == 1
        assert result["suspicious_pairs"][0]["risk_level"] == "high"
        assert result["common_issues"] == ["缺乏案例分析"]

    def test_without_suspect_pairs(self, mocker):
        """无可疑对时仍应完成比对分析。"""
        submissions = [
            {"id": "s1", "student_name": "张三", "text": "内容A"},
        ]
        mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "suspicious_pairs": [],
            "comparison_details": [
                {
                    "submission_id": "s1",
                    "student_name": "张三",
                    "strengths": ["逻辑清晰"],
                    "weaknesses": ["缺少深度"],
                    "dimension_scores": {"structure": "良好"},
                }
            ],
            "common_issues": [],
            "teaching_suggestions": [],
        }))

        result = minimax_client.analyze_submissions(submissions, [], ["structure"])
        assert result["suspicious_pairs"] == []
        assert len(result["comparison_details"]) == 1

    def test_fallback_on_parse_error(self, mocker):
        mocker.patch.object(minimax_client, "_chat", return_value="分析失败，请重试。")
        result = minimax_client.analyze_submissions(
            [{"id": "s1", "student_name": "张三", "text": "内容"}], [], ["structure"]
        )
        assert result["suspicious_pairs"] == []
        assert result["comparison_details"] == []
        assert result["teaching_suggestions"] == ["分析失败，请重试。"]

    def test_includes_dimensions_in_prompt(self, mocker):
        mock_chat = mocker.patch.object(minimax_client, "_chat", return_value=json.dumps({
            "suspicious_pairs": [], "comparison_details": [],
            "common_issues": [], "teaching_suggestions": [],
        }))
        minimax_client.analyze_submissions(
            [{"id": "s1", "student_name": "张三", "text": "内容"}],
            [],
            ["structure", "expression", "conclusion"],
        )
        user_content = mock_chat.call_args[0][1]
        assert "structure" in user_content
        assert "expression" in user_content
