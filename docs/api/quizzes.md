# 测试 API

> 所有接口均需携带 JWT 令牌。

---

## 说明

教师在课程内发布测试，学生作答后系统自动批改。支持四种题型：

| 题型 | `question_type` | 批改方式 |
| --- | --- | --- |
| 单选题 | `single_choice` | 自动（精确匹配选项 key） |
| 多选题 | `multi_choice` | 自动（集合比较） |
| 判断题 | `true_false` | 自动（`"true"` / `"false"`） |
| 简答题 | `short_answer` | AI 批改（MiniMax） |

测试成绩会被纳入个性化学习计划生成的数据信号（错题自动提取为薄弱知识点）。

---

## 一、教师端

### 1.1 发布测试

```http
POST /api/teacher/courses/{course_id}/quizzes
```

**权限：** `role = teacher`

**请求体：**

```json
{
  "title": "进程管理小测",
  "description": "考察第一章进程管理核心概念，共 4 道题。",
  "section_id": "section_001",
  "time_limit_minutes": 20,
  "questions": [
    {
      "question_type": "single_choice",
      "content": "进程调度的基本单位是？",
      "options": [
        { "key": "A", "text": "进程" },
        { "key": "B", "text": "线程" },
        { "key": "C", "text": "程序" },
        { "key": "D", "text": "作业" }
      ],
      "correct_answer": "B",
      "explanation": "线程是 CPU 调度的基本单位，进程是资源分配的基本单位。",
      "score": 25,
      "order": 1
    },
    {
      "question_type": "true_false",
      "content": "阻塞态的进程仍然占用 CPU 资源。",
      "correct_answer": "false",
      "explanation": "阻塞态的进程等待 I/O 等事件，不占用 CPU。",
      "score": 25,
      "order": 2
    },
    {
      "question_type": "multi_choice",
      "content": "以下哪些是进程的基本状态？",
      "options": [
        { "key": "A", "text": "就绪" },
        { "key": "B", "text": "运行" },
        { "key": "C", "text": "阻塞" },
        { "key": "D", "text": "挂起" }
      ],
      "correct_answer": "[\"A\", \"B\", \"C\"]",
      "explanation": "挂起不是进程的基本三态，属于扩展状态。",
      "score": 25,
      "order": 3
    },
    {
      "question_type": "short_answer",
      "content": "简述进程与线程的区别（不少于 3 点）。",
      "correct_answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位；同一进程内的线程共享地址空间，进程间相互独立；线程上下文切换开销小于进程切换；进程拥有独立的内存空间。",
      "score": 25,
      "order": 4
    }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 测试标题 |
| description | string | 否 | 测试说明 |
| section_id | string | 否 | 关联小节，不填则为课程级测试 |
| time_limit_minutes | integer | 否 | 时间限制（分钟），不填则不限时 |
| questions | array | 是 | 题目列表 |

**题目字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| question_type | string | 是 | `single_choice` / `multi_choice` / `true_false` / `short_answer` |
| content | string | 是 | 题目内容 |
| options | array | 选择题必填 | 选项列表，每项含 `key` 和 `text` |
| correct_answer | string | 是 | 正确答案；多选题用 JSON 数组字符串，如 `"[\"A\",\"C\"]"` |
| explanation | string | 否 | 解析说明，作答后展示给学生 |
| score | float | 否 | 本题分值，默认 10 分 |
| order | integer | 否 | 排序序号 |

---

### 1.2 获取测试列表

```http
GET /api/teacher/courses/{course_id}/quizzes
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| section_id | string | 否 | 按小节筛选 |
| status | string | 否 | open 或 closed |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "items": [
      {
        "id": "quiz_001",
        "title": "进程管理小测",
        "section_id": "section_001",
        "status": "open",
        "question_count": 4,
        "time_limit_minutes": 20,
        "attempt_count": 18,
        "created_at": "2026-06-10T10:00:00+08:00"
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

### 1.3 关闭 / 重开测试

```http
PATCH /api/teacher/courses/{course_id}/quizzes/{quiz_id}
```

**请求体：** `{ "status": "closed" }`

---

### 1.4 查看学生作答汇总

```http
GET /api/teacher/courses/{course_id}/quizzes/{quiz_id}/attempts
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "quiz_id": "quiz_001",
    "attempt_count": 18,
    "average_score": 76.4,
    "items": [
      {
        "attempt_id": "attempt_001",
        "student_id": "user_001",
        "student_name": "张三",
        "total_score": 75.0,
        "full_score": 100.0,
        "submitted_at": "2026-06-10T10:25:00+08:00"
      }
    ]
  },
  "message": "ok"
}
```

---

## 二、学生端

### 2.1 获取测试列表

```http
GET /api/student/courses/{course_id}/quizzes
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "items": [
      {
        "id": "quiz_001",
        "title": "进程管理小测",
        "section_id": "section_001",
        "question_count": 4,
        "time_limit_minutes": 20,
        "attempt_status": "submitted",
        "score": 75.0
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

> `attempt_status` 为 `null` 表示尚未开始，`in_progress` 表示已开始未提交，`submitted` 表示已提交。

---

### 2.2 获取测试详情

```http
GET /api/student/courses/{course_id}/quizzes/{quiz_id}
```

**功能说明：** 返回测试题目，不包含正确答案和解析。

---

### 2.3 开始作答

```http
POST /api/student/courses/{course_id}/quizzes/{quiz_id}/start
```

**功能说明：** 创建作答记录，返回 `attempt_id`，后续保存答案和提交时需携带。每个学生每个测试只能开始一次。

**响应示例：**

```json
{
  "success": true,
  "data": {
    "attempt_id": "attempt_001",
    "started_at": "2026-06-10T10:05:00+08:00"
  },
  "message": "started"
}
```

> 如果已经开始了该测试，调用此接口会返回 `400：已开始过该测试，请直接提交`。此时应改用 [2.4 获取作答进度](#24-获取作答进度) 获取 `attempt_id` 并继续作答。

---

### 2.4 获取作答进度

```http
GET /api/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}
```

**功能说明：** 获取当前作答进度，返回已保存的逐题答案，用于刷新页面后恢复作答状态。

**响应示例：**

```json
{
  "success": true,
  "data": {
    "attempt_id": "attempt_001",
    "status": "in_progress",
    "started_at": "2026-06-10T10:05:00+08:00",
    "submitted_at": null,
    "answers": {
      "q_001": "B",
      "q_002": "false"
    },
    "answered_count": 2
  },
  "message": "ok"
}
```

> `answers` 为 `{question_id: answer}` 的映射，仅包含已保存过答案的题目。如果 `status` 为 `submitted`，则不能再修改答案。`attempt_id` 可从 [2.2 获取测试详情](#22-获取测试详情) 的 `attempt.id` 字段获取。

---

### 2.5 逐题保存答案

```http
PUT /api/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/answers
```

**功能说明：** 逐题保存/更新答案。学生可边做边保存，已保存的答案可多次覆盖更新。仅限 `in_progress` 状态的 attempt。

**请求体：**

```json
{
  "question_id": "q_001",
  "answer": "B"
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "question_id": "q_001",
    "saved": true
  },
  "message": "saved"
}
```

> 单选题答案为选项 key（如 `"B"`），多选题答案为 JSON 数组字符串（如 `"[\"A\",\"C\"]"`），判断题为 `"true"` / `"false"`，简答题为文本。

---

### 2.6 提交答案

```http
POST /api/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/submit
```

**功能说明：** 提交所有题目的答案，系统自动批改：客观题立即给分，简答题调用 MiniMax 批改。

- 请求体中传入的答案将覆盖之前通过"逐题保存"保存的答案
- 未在请求体中传入、但之前已逐题保存过的答案也会被自动批改
- 既未传入也未保存的题目得 0 分

因此，学生可以：
1. 所有题目都在请求体中一次性提交（传统模式）
2. 部分逐题保存 + 部分在提交时传参
3. 全部逐题保存，提交时只需传空数组 `{"answers": []}`

---

### 2.6 提交答案

```http
POST /api/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/submit
```

**功能说明：** 提交所有题目的答案，系统自动批改：客观题立即给分，简答题调用 MiniMax 批改。

- 请求体中传入的答案将覆盖之前通过"逐题保存"保存的答案
- 未在请求体中传入、但之前已逐题保存过的答案也会被自动批改
- 既未传入也未保存的题目得 0 分

因此，学生可以：
1. 所有题目都在请求体中一次性提交（传统模式）
2. 部分逐题保存 + 部分在提交时传参
3. 全部逐题保存，提交时只需传空数组 `{"answers": []}`

**请求体：**

```json
{
  "answers": [
    { "question_id": "q_001", "answer": "B" },
    { "question_id": "q_002", "answer": "false" },
    { "question_id": "q_003", "answer": "[\"A\",\"B\",\"C\"]" },
    { "question_id": "q_004", "answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位..." }
  ]
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "attempt_id": "attempt_001",
    "total_score": 75.0,
    "full_score": 100.0,
    "results": [
      { "question_id": "q_001", "is_correct": true, "score": 25.0, "ai_feedback": null, "correct_answer": "B", "explanation": "线程是 CPU 调度的基本单位..." },
      { "question_id": "q_002", "is_correct": true, "score": 25.0, "ai_feedback": null, "correct_answer": "false", "explanation": null },
      { "question_id": "q_003", "is_correct": false, "score": 0.0, "ai_feedback": null, "correct_answer": "[\"A\",\"B\",\"C\"]", "explanation": "挂起不是进程的基本三态..." },
      { "question_id": "q_004", "is_correct": true, "score": 25.0, "ai_feedback": "回答较完整，提到了资源分配和调度单位的区别，但未涉及内存共享方面的差异。", "correct_answer": "进程是资源分配...", "explanation": null }
    ]
  },
  "message": "submitted"
}
```

---

### 2.7 查看测试结果

```http
GET /api/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/result
```

**功能说明：** 查看已提交的测试完整结果，包含正确答案、解析和 AI 评语。

---

## 三、测试成绩与学习计划的关系

测试提交后，系统自动将以下信息纳入学习计划生成的数据信号：

- **得分/满分**：反映整体掌握程度
- **错题内容**（截取前 50 字）：直接作为薄弱知识点，与作业扣分点共同用于 RAG 检索相关课程材料

因此，测试做得越多，学习计划的薄弱点识别越准确。
