# 作业管理 API

> 所有接口均需携带 JWT 令牌。

---

## 零、文件上传（独立接口）

> 基础路径：`/api/upload`
>
> 权限：任意已登录用户（学生或教师）。

文件上传已从作业发布/提交接口中独立出来，前端应**先将文件通过本接口上传**，拿到返回的 `file_id` 后再调用作业发布或提交接口。

### 0.1 上传单个文件

```http
POST /api/upload
```

**功能说明：** 每次调用上传一个文件，写入 `files` 通用文件表，返回 `file_id` 和可访问路径 `file_url`。多个文件需多次调用。

**请求格式（multipart/form-data）：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 单个二进制文件，支持 PDF、TXT、DOC、DOCX，最大 10 MB |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "file_id": "f_abc123",
    "file_url": "/files/a1b2c3d4_实验报告.pdf",
    "file_name": "实验报告.pdf",
    "file_size": 204800,
    "extracted_text": "这是从 PDF 中提取的文本内容（若文件可解析则返回纯文本，否则为 null）"
  },
  "message": "uploaded"
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| file_id | string | 文件在 `files` 表中的唯一 ID，用于后续接口（作业发布/提交传此值） |
| file_url | string | 文件在文件服务器上的访问路径，前端可直接用于下载/预览 |
| file_name | string | 原始文件名 |
| file_size | number | 文件大小（字节） |
| extracted_text | string \| null | C++ 文件处理服务提取的文本内容，不可解析时返回 null |

---

## 一、学生端作业 API

> 基础路径：`/api/student/courses/{course_id}/assignments`
>
> 权限：`role = student`

### 1.1 获取作业列表

```http
GET /api/student/courses/{course_id}/assignments
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course | string | 否 | 按课程名筛选 |
| status | string | 否 | open 或 closed |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "assignment_001",
        "title": "进程管理练习",
        "course": "操作系统",
        "due_at": "2026-06-15T23:59:00+08:00",
        "status": "open",
        "submitted": false
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

### 1.2 获取作业详情

```http
GET /api/student/courses/{course_id}/assignments/{assignment_id}
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |
| assignment_id | string | 是 | 作业 ID |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "title": "进程管理练习",
    "course": "操作系统",
    "description": "完成关于进程状态转换的分析题，不少于 500 字。",
    "due_at": "2026-06-15T23:59:00+08:00",
    "status": "open",
    "attachment_url": "/files/assignment_001_topic.pdf",
    "submitted": false
  },
  "message": "ok"
}
```

---

### 1.3 提交作业

```http
POST /api/student/courses/{course_id}/assignments/{assignment_id}/submit
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |
| assignment_id | string | 是 | 作业 ID |

**功能说明：** 学生提交作业，支持文本和文件两种模式。**文件提交时需先将文件通过 `POST /api/upload` 上传，获得 `file_id` 后再调用本接口。**

**请求格式（multipart/form-data）：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| submit_type | string | 是 | `text`（文本）或 `file`（文件） |
| content | string | text 时必填 | 作业正文 |
| file_ids | string | file 时必填 | 已上传文件的 ID，多个以逗号分隔（来自 `/api/upload` 返回的 `file_id`） |

**示例 — 文本提交：**

```text
submit_type=text
content=进程是程序执行的实体...
```

**示例 — 文件提交（先上传了两个文件）：**

```text
submit_type=file
file_ids=f_abc123,f_def456
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "submission_001",
    "assignment_id": "assignment_001",
    "student_id": "user_001",
    "submit_type": "file",
    "submitted_at": "2026-06-08T14:30:00+08:00",
    "status": "submitted"
  },
  "message": "submitted"
}
```

---

### 1.4 查看本人提交详情

```http
GET /api/student/courses/{course_id}/assignments/{assignment_id}/my-submission
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |
| assignment_id | string | 是 | 作业 ID |

**响应示例：**

```json
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "submission_001",
    "assignment_id": "assignment_001",
    "submit_type": "file",
    "content": "学生提交的文本内容（仅 text 类型）",
    "file_urls": ["/files/a1b2c3d4_报告.pdf", "/files/e5f6g7h8_代码.zip"],
    "files": [
      { "filename": "实验报告.pdf", "file_url": "/files/a1b2c3d4_报告.pdf", "file_size": 204800 },
      { "filename": "源代码.zip", "file_url": "/files/e5f6g7h8_代码.zip", "file_size": 51200 }
    ],
    "submitted_at": "2026-06-08T14:30:00+08:00",
    "status": "submitted",
    "score": 88,
    "ai_score": 86,
    "comments": "整体思路正确，但关键概念解释不够完整。",
    "deductions": [
      {
        "point": "进程状态转换条件说明不完整",
        "minus": 6
      }
    ],
    "suggestions": ["补充阻塞态与就绪态的转换条件"],
    "teacher_comment": "补充了一些关键点，酌情加分。",
    "graded_at": "2026-06-09T10:00:00+08:00"
  },
  "message": "ok"
}
```

---

## 二、教师端作业管理 API

> 基础路径：`/api/teacher/courses/{course_id}/assignments`
>
> 权限：`role = teacher`

### 2.1 发布作业

```http
POST /api/teacher/courses/{course_id}/assignments
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |

**功能说明：** 教师发布新作业。如有附件，需先将文件通过 `POST /api/upload` 上传，得到 `file_id` 后再传入 `attachment_file_id`。

**请求格式（multipart/form-data）：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 作业标题 |
| course | string | 是 | 课程名称 |
| description | string | 是 | 作业要求说明 |
| due_at | string | 是 | 截止时间（ISO 8601 格式） |
| reference_answer | string | 否 | 参考答案（供 AI 批改参考） |
| rubric | string | 否 | 评分标准（供 AI 批改参考） |
| attachment_file_id | string | 否 | 附件在 `files` 表中的 ID（来自 `/api/upload` 返回的 `file_id`） |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "title": "进程管理练习",
    "course": "操作系统",
    "description": "完成关于进程状态转换的分析题，不少于 500 字。",
    "due_at": "2026-06-15T23:59:00+08:00",
    "status": "open",
    "attachment_url": "/files/a1b2c3d4_题目.pdf",
    "created_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "published"
}
```

---

### 2.2 获取作业列表

```http
GET /api/teacher/courses/{course_id}/assignments
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course | string | 否 | 按课程名筛选 |
| status | string | 否 | open 或 closed |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "assignment_001",
        "title": "进程管理练习",
        "course": "操作系统",
        "due_at": "2026-06-15T23:59:00+08:00",
        "status": "open",
        "submission_count": 25,
        "total_students": 0
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

### 2.3 获取作业详情

```http
GET /api/teacher/courses/{course_id}/assignments/{assignment_id}
```

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |
| assignment_id | string | 是 | 作业 ID |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "title": "进程管理练习",
    "course": "操作系统",
    "description": "完成关于进程状态转换的分析题，不少于 500 字。",
    "reference_answer": "参考答案内容...",
    "rubric": "满分 100 分，概念 40 分，分析 40 分，表达 20 分。",
    "due_at": "2026-06-15T23:59:00+08:00",
    "status": "open",
    "attachment_url": "/files/a1b2c3d4_题目.pdf",
    "submission_count": 25,
    "created_at": "2026-06-04T10:00:00+08:00",
    "updated_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "ok"
}
```

---

### 2.4 更新作业

```http
PATCH /api/teacher/courses/{course_id}/assignments/{assignment_id}
```

**请求体（application/json）：**

```json
{
  "description": "完成关于进程状态转换的分析题，不少于 800 字。",
  "due_at": "2026-06-18T23:59:00+08:00"
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "description": "完成关于进程状态转换的分析题，不少于 800 字。",
    "due_at": "2026-06-18T23:59:00+08:00",
    "updated_at": "2026-06-05T10:00:00+08:00"
  },
  "message": "updated"
}
```

---

### 2.5 关闭作业

```http
POST /api/teacher/courses/{course_id}/assignments/{assignment_id}/close
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "status": "closed"
  },
  "message": "closed"
}
```

---

### 2.6 获取作业提交列表

```http
GET /api/teacher/courses/{course_id}/assignments/{assignment_id}/submissions
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "assignment_id": "assignment_001",
    "items": [
      {
        "id": "submission_001",
        "student_id": "user_001",
        "student_name": "张三",
        "submit_type": "file",
        "content": "学生提交的文本内容（仅 text 类型）",
        "extracted_text": "C++ 从文件中提取的文本内容",
        "file_urls": ["/files/a1b2c3d4_报告.pdf", "/files/e5f6g7h8_代码.zip"],
        "files": [
          { "filename": "实验报告.pdf", "file_url": "/files/a1b2c3d4_报告.pdf", "file_size": 204800 },
          { "filename": "源代码.zip", "file_url": "/files/e5f6g7h8_代码.zip", "file_size": 51200 }
        ],
        "submitted_at": "2026-06-08T14:30:00+08:00",
        "status": "submitted",
        "score": 88,
        "ai_score": 86,
        "confirmed": true
      }
    ],
    "total": 25
  },
  "message": "ok"
}
```

---

## 三、教师端 AI 批改 API

> 基础路径：`/api/teacher/courses/{course_id}/assignments/{assignment_id}`
>
> 权限：`role = teacher`

### 3.1 AI 批改作业

```http
POST /api/teacher/courses/{course_id}/assignments/{assignment_id}/grade
```

**请求体（application/json）：**

```json
{
  "submission_ids": ["submission_001", "submission_002"],
  "need_teacher_confirm": true
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| submission_ids | array | 是 | 待批改的提交 ID 列表 |
| need_teacher_confirm | boolean | 否 | 是否需要教师二次确认（默认 true） |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "assignment_id": "assignment_001",
    "results": [
      {
        "submission_id": "submission_001",
        "student_id": "user_001",
        "student_name": "张三",
        "ai_score": 86,
        "comments": "整体思路正确，但关键概念解释不够完整。",
        "deductions": [
          { "point": "进程状态转换条件说明不完整", "minus": 6 }
        ],
        "suggestions": ["补充阻塞态与就绪态的转换条件", "增加调度算法对比"],
        "confirmed": false
      }
    ]
  },
  "message": "graded"
}
```

---

### 3.2 教师确认或调整批改结果

```http
PATCH /api/teacher/submissions/{submission_id}/grade
```

**请求体（application/json）：**

```json
{
  "final_score": 88,
  "confirmed": true,
  "teacher_comment": "补充了一些关键点，酌情加分。"
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "submission_id": "submission_001",
    "final_score": 88,
    "confirmed": true
  },
  "message": "updated"
}
```

---

### 3.3 获取批改报告

```http
GET /api/teacher/courses/{course_id}/assignments/{assignment_id}/grading-report
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "assignment_id": "assignment_001",
    "average_score": 82.5,
    "graded_count": 25,
    "common_mistakes": ["概念解释不完整", "缺少案例分析"],
    "weak_points": ["进程状态转换", "线程共享资源"],
    "teaching_suggestions": ["建议下一节课用流程图讲解状态转换", "安排一次概念对比小测"]
  },
  "message": "ok"
}
```

---

## 四、教师端 AI 查重与作业比对 API

> 权限：`role = teacher`

### 4.1 触发查重与比对分析

```http
POST /api/teacher/courses/{course_id}/assignments/{assignment_id}/analyze
```

**请求体（application/json）：**

```json
{
  "submission_ids": ["submission_001", "submission_002", "submission_003"],
  "similarity_threshold": 0.8,
  "compare_dimensions": ["structure", "concept", "expression", "conclusion"]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| submission_ids | array | 是 | 参与分析的提交 ID 列表 |
| similarity_threshold | number | 否 | 相似度告警阈值，默认 0.8（0.0~1.0） |
| compare_dimensions | array | 否 | 比对维度，默认全部（structure, concept, expression, conclusion） |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "report_id": "report_001",
    "assignment_id": "assignment_001",
    "suspicious_pairs": [
      {
        "submission_a": "submission_001",
        "student_a": "张三",
        "submission_b": "submission_002",
        "student_b": "李四",
        "similarity": 0.87,
        "risk_level": "high",
        "similar_segments": ["对进程定义的表述高度一致", "结论段落结构相同"],
        "ai_reason": "两份作业在观点顺序、关键句表达和例子选择上高度相似，存在参考同一来源的可能。"
      }
    ],
    "comparison_details": [
      {
        "submission_id": "submission_001",
        "student_name": "张三",
        "strengths": ["对线程区别解释较完整", "结合了具体场景举例"],
        "weaknesses": ["缺少调度算法对比"],
        "dimension_scores": {
          "structure": "完整",
          "concept": "准确",
          "expression": "流畅",
          "conclusion": "一般"
        }
      }
    ],
    "common_issues": ["都没有结合具体场景举例"],
    "teaching_suggestions": ["课堂上补充进程状态转换案例", "强调概念解释和例子结合"],
    "created_at": "2026-06-09T10:00:00+08:00"
  },
  "message": "analyzed"
}
```

---

### 4.2 获取分析报告

```http
GET /api/teacher/courses/{course_id}/assignments/{assignment_id}/analyze-report
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "report_id": "report_001",
    "assignment_id": "assignment_001",
    "suspicious_pairs": ["..."],
    "comparison_details": ["..."],
    "common_issues": ["都没有结合具体场景举例"],
    "created_at": "2026-06-09T10:00:00+08:00"
  },
  "message": "ok"
}
```
