"""
MiniMax API 客户端。
所有大模型调用统一通过本模块，不在业务代码中直接调用外部 API。

连接池策略：
  - 使用模块级 httpx.Client 单例，复用 TCP 连接，避免每次请求都经历
    TCP 握手 + TLS 协商的开销。
  - limits：最多保留 10 条空闲连接；最大并发连接数 20。
  - timeout：连接建立 5 s，读取 60 s（大模型首 token 可能较慢）。
  - 生命周期：应用启动时由 close() 惰性初始化；关闭时调用 close() 释放。
"""
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
_EMBED_URL = "https://api.minimax.chat/v1/embeddings"

# Embedding 向量维度（MiniMax embo-01 固定 1536 维）
EMBEDDING_DIM = 1536

# 每次 Embedding API 最多传入的文本数量
_EMBED_BATCH_SIZE = 32

# ── 连接池配置 ─────────────────────────────────────────────────
# keepalive_expiry：空闲连接最长保留时间（秒），超时后被主动关闭
_LIMITS = httpx.Limits(
    max_keepalive_connections=10,   # 最多保留的空闲长连接数
    max_connections=20,             # 最大并发连接数
    keepalive_expiry=30.0,          # 空闲连接保活时间（秒）
)

# connect：TCP+TLS 握手超时；read：等待服务端首字节超时
_TIMEOUT = httpx.Timeout(
    connect=5.0,    # 连接建立超时（秒）
    read=60.0,      # 读取超时，留出模型推理时间（秒）
    write=10.0,     # 请求体写入超时（秒）
    pool=5.0,       # 从连接池获取连接的等待超时（秒）
)

# 模块级单例，应用启动后复用，不在每次请求时新建
_http_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """惰性初始化 HTTP 客户端单例（同步场景）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(limits=_LIMITS, timeout=_TIMEOUT)
        logger.info("MiniMax HTTP 客户端已初始化（连接池: max=%d）", _LIMITS.max_connections)
    return _http_client


def close() -> None:
    """关闭连接池，释放所有底层 TCP 连接，应在应用关闭时调用"""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        _http_client.close()
        logger.info("MiniMax HTTP 客户端已关闭")
    _http_client = None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.minimax_api_key}",
        "Content-Type": "application/json",
    }


def _chat(system_prompt: str, user_content: str, *, temperature: float = 0.7) -> str:
    """底层同步请求，返回模型回复文本；失败时抛出 RuntimeError"""
    payload = {
        "model": settings.minimax_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    try:
        resp = _get_client().post(_BASE_URL, headers=_headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error("MiniMax HTTP 错误: %s", e)
        raise RuntimeError(f"大模型服务异常: {e.response.status_code}") from e
    except Exception as e:
        logger.error("MiniMax 调用失败: %s", e)
        raise RuntimeError(f"大模型服务不可用: {e}") from e


def _chat_stream(system_prompt: str, user_content: str, *, temperature: float = 0.7):
    """
    流式底层请求，逐 token yield 文本片段。
    使用 httpx Client.stream() 上下文管理器，按行解析 SSE 格式。
    失败时抛出 RuntimeError。
    """
    payload = {
        "model": settings.minimax_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "stream": True,
    }
    try:
        with _get_client().stream("POST", _BASE_URL, headers=_headers(), json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.HTTPStatusError as e:
        logger.error("MiniMax 流式 HTTP 错误: %s", e)
        raise RuntimeError(f"大模型服务异常: {e.response.status_code}") from e
    except Exception as e:
        logger.error("MiniMax 流式调用失败: %s", e)
        raise RuntimeError(f"大模型服务不可用: {e}") from e


def _parse_json(text: str) -> dict | list:
    """从模型回复中提取 JSON，兼容 markdown 代码块包裹"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return json.loads(text)


# ── 公开方法 ──────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    调用 MiniMax Embedding API，批量将文本转为向量。
    返回与 texts 等长的向量列表，每个向量维度为 1536。
    单次最多 _EMBED_BATCH_SIZE 条，自动分批处理。
    """
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i: i + _EMBED_BATCH_SIZE]
        payload = {
            "model": settings.minimax_embedding_model,
            "input": batch,
            "type": "query",  # query 模式，适用于检索场景
        }
        try:
            resp = _get_client().post(_EMBED_URL, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            # MiniMax 返回格式：{"data": [{"embedding": [...], "index": 0}, ...]}
            sorted_items = sorted(data["data"], key=lambda x: x["index"])
            all_embeddings.extend(item["embedding"] for item in sorted_items)
        except httpx.HTTPStatusError as e:
            logger.error("MiniMax Embedding HTTP 错误: %s", e)
            raise RuntimeError(f"Embedding 服务异常: {e.response.status_code}") from e
        except Exception as e:
            logger.error("MiniMax Embedding 调用失败: %s", e)
            raise RuntimeError(f"Embedding 服务不可用: {e}") from e
    return all_embeddings


def embed_query(text: str) -> list[float]:
    """对单条查询文本向量化，返回 1536 维向量。"""
    return embed_texts([text])[0]

def answer_question(question: str, course: str | None, history: list[dict], context: str = "") -> dict:
    """
    学生智能问答。
    返回: {"answer": str, "suggestions": list[str]}
    """
    history_text = ""
    if history:
        history_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in history[-6:]  # 最近 3 轮
        )
    course_hint = f"当前课程：{course}。" if course else ""
    context_hint = f"\n\n以下是与问题相关的课程材料，请优先基于这些内容作答：\n{context}" if context else ""
    system = (
        f"你是一个专业的学习助手。{course_hint}{context_hint}"
        "请用简洁、准确的中文回答学生的问题，并在最后给出 2-3 条中文学习建议。"
        '以 JSON 格式返回，格式为：{"answer": "...", "suggestions": ["...", "..."]}'
    )
    user = f"{history_text}\n学生问题：{question}" if history_text else question
    raw = _chat(system, user)
    try:
        return _parse_json(raw)
    except Exception:
        return {"answer": raw, "suggestions": []}


def answer_question_stream(question: str, course: str | None, history: list[dict], context: str = ""):
    """
    学生智能问答（流式版本）。
    yield 文本片段，拼接后即为完整回答。
    prompt 不要求 JSON 格式，直接输出自然语言答案。
    """
    history_text = ""
    if history:
        history_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in history[-6:]  # 最近 3 轮
        )
    course_hint = f"当前课程：{course}。" if course else ""
    context_hint = f"\n\n以下是与问题相关的课程材料，请优先基于这些内容作答：\n{context}" if context else ""
    system = (
        f"你是一个专业的学习助手。{course_hint}{context_hint}"
        "请用简洁、准确的中文回答学生的问题。"
    )
    user = f"{history_text}\n学生问题：{question}" if history_text else question
    yield from _chat_stream(system, user)


def generate_summary(title: str, source_text: str, summary_type: str, course: str | None) -> dict:
    """
    知识点总结。
    返回: {"overview": str, "key_points": [], "difficult_points": [], "review_tips": []}
    """
    course_hint = f"课程：{course}，" if course else ""
    type_map = {"structured": "结构化总结", "brief": "简要摘要", "review": "复习清单"}
    type_desc = type_map.get(summary_type, "结构化总结")
    system = (
        f"你是一个专业的学习内容整理助手。{course_hint}请对以下内容生成{type_desc}。"
        "所有输出必须使用中文。"
        "以 JSON 格式返回，包含字段：overview（中文概述）、key_points（中文要点列表）、"
        "difficult_points（中文难点列表）、review_tips（中文复习建议列表）。"
    )
    raw = _chat(system, f"标题：{title}\n\n内容：{source_text}")
    try:
        return _parse_json(raw)
    except Exception:
        return {"overview": raw, "key_points": [], "difficult_points": [], "review_tips": []}


def generate_learning_plan(course: str, goal: str, basis: dict, available_minutes: int) -> dict:
    """
    生成个性化学习计划。
    返回: {"analysis": {...}, "plan": [{"day": 1, "task": "...", "duration_minutes": 60}, ...]}
    """
    system = (
        "你是一个专业的学习规划助手。根据学生的成绩、作业完成情况和学习目标，"
        "生成一份按天安排的学习计划。"
        "以 JSON 格式返回，包含字段：analysis（包含 current_level、weak_points、priority）"
        "和 plan（每天任务列表，每项含 day、task、duration_minutes）。"
    )
    user = (
        f"课程：{course}\n学习目标：{goal}\n每天可用时间：{available_minutes} 分钟\n"
        f"学情数据：{json.dumps(basis, ensure_ascii=False)}"
    )
    raw = _chat(system, user)
    try:
        return _parse_json(raw)
    except Exception:
        return {"analysis": {}, "plan": []}


def grade_quiz_answer(question: str, correct_answer: str, student_answer: str, score: float) -> dict:
    """
    AI 批改简答题。
    返回: {"score": float, "feedback": str}
    """
    system = (
        "你是一个严谨的简答题批改助手。根据参考答案对学生回答评分，满分为给定的 score 值。"
        "所有输出必须使用中文。"
        "以 JSON 格式返回，包含字段：score（实际得分，不超过满分）、feedback（中文简短评语，指出优缺点）。"
    )
    user = (
        f"满分：{score}\n"
        f"题目：{question}\n"
        f"参考答案：{correct_answer}\n"
        f"学生回答：{student_answer}"
    )
    raw = _chat(system, user, temperature=0.3)
    try:
        result = _parse_json(raw)
        result["score"] = min(float(result.get("score", 0)), score)
        return result
    except Exception:
        return {"score": 0.0, "feedback": raw}


def adjust_learning_plan(
    course: str,
    original_plan: list,
    progress: list,
    student_feedback: str,
    available_minutes: int,
) -> dict:
    """
    基于学生的完成进度和反馈，对已有计划进行增量调整。
    progress: [{"day": 1, "completed": true, "feedback": "已掌握"}, ...]
    返回: {"analysis": {...}, "plan": [...]}，plan 为完整调整后的新计划。
    """
    system = (
        "你是一个专业的学习规划助手。学生已按照原计划执行了一段时间，"
        "现在根据完成情况和反馈，对剩余计划进行调整。"
        "保留已完成的任务，只调整未完成部分。"
        "以 JSON 格式返回，包含字段：analysis（包含 adjustment_reason、completed_days、remaining_days）"
        "和 plan（完整的新计划列表，已完成的任务也要包含，day 编号保持连续）。"
    )
    user = (
        f"课程：{course}\n"
        f"每天可用时间：{available_minutes} 分钟\n"
        f"原计划：{json.dumps(original_plan, ensure_ascii=False)}\n"
        f"完成情况：{json.dumps(progress, ensure_ascii=False)}\n"
        f"学生反馈：{student_feedback}"
    )
    raw = _chat(system, user)
    try:
        return _parse_json(raw)
    except Exception:
        return {"analysis": {}, "plan": original_plan}


def grade_submission(content: str, reference_answer: str, rubric: str) -> dict:
    """
    AI 批改单份作业。
    返回: {"ai_score": float, "comments": str, "deductions": [], "suggestions": []}
    """
    system = (
        "你是一个严谨的作业批改助手。根据参考答案和评分标准对学生作业进行评分。"
        "所有输出必须使用中文，包括 comments、deductions、suggestions 中的全部文字内容。"
        "以 JSON 格式返回，包含字段：ai_score（0-100 的数字分数）、comments（中文总体评语）、"
        "deductions（扣分点列表，每项含 point 和 minus 字段，point 用中文描述）、"
        "suggestions（中文修改建议列表）。"
    )
    user = (
        f"【评分标准】\n{rubric}\n\n"
        f"【参考答案】\n{reference_answer}\n\n"
        f"【学生作业】\n{content}"
    )
    raw = _chat(system, user, temperature=0.3)
    try:
        result = _parse_json(raw)
        # 确保 ai_score 是数字
        result["ai_score"] = float(result.get("ai_score", 0))
        return result
    except Exception:
        return {"ai_score": 0.0, "comments": raw, "deductions": [], "suggestions": []}


def analyze_submissions(
    submissions: list[dict],
    suspect_pairs: list[tuple[int, int, float]],
    compare_dimensions: list[str],
) -> dict:
    """
    AI 查重与作业比对（合并）。
    submissions: [{"id": str, "student_name": str, "text": str}, ...]
    suspect_pairs: C++ 粗筛结果 [(i, j, similarity), ...]
    返回: {"suspicious_pairs": [...], "comparison_details": [...], "common_issues": [...], "teaching_suggestions": [...]}
    """
    # 构造待分析的可疑对文本
    pairs_text = ""
    for i, j, sim in suspect_pairs:
        a = submissions[i]
        b = submissions[j]
        pairs_text += (
            f"\n--- 可疑对（指纹相似度 {sim:.2f}）---\n"
            f"学生A（{a['student_name']}）：{a['text'][:500]}\n"
            f"学生B（{b['student_name']}）：{b['text'][:500]}\n"
        )

    all_texts = "\n".join(
        f"学生{s['student_name']}：{s['text'][:300]}" for s in submissions
    )
    dims = "、".join(compare_dimensions)

    system = (
        "你是一个专业的作业分析助手，负责查重和作业比对。"
        "所有输出必须使用中文，包括 ai_reason、strengths、weaknesses、common_issues、"
        "teaching_suggestions 等全部文字内容。"
        "以 JSON 格式返回，包含字段：\n"
        "- suspicious_pairs: 可疑对列表，每项含 submission_a、student_a、submission_b、student_b、"
        "similarity、risk_level（high/medium/low）、similar_segments（列表）、ai_reason（中文）\n"
        "- comparison_details: 每份作业的比对详情列表，每项含 submission_id、student_name、"
        "strengths（中文列表）、weaknesses（中文列表）、dimension_scores（字典）\n"
        "- common_issues: 中文共同问题列表\n"
        "- teaching_suggestions: 中文教学建议列表"
    )
    user = (
        f"比对维度：{dims}\n\n"
        f"所有提交：\n{all_texts}\n\n"
        f"需重点关注的可疑对：{pairs_text if pairs_text else '无'}"
    )
    raw = _chat(system, user, temperature=0.3)
    try:
        return _parse_json(raw)
    except Exception:
        return {
            "suspicious_pairs": [],
            "comparison_details": [],
            "common_issues": [],
            "teaching_suggestions": [raw],
        }
