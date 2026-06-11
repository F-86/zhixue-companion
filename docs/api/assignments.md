# 作业管理 API

> 所有接口均需携带 JWT 令牌。
>
> **作业创建**入口在 [课程小节 API](./sections.md) 第 5 节（`POST /api/teacher/courses/{course_id}/sections/{section_id}/assignments`），作业与小节绑定。
>
> 本文档覆盖作业的查看、提交、批改、查重比对等操作。

---

## 一、学生端作业 API

> 基础路径：`/api/student/courses/{course_id}/assignments`
>
> 权限：`role = student`，且已加入该课程。

### 1.1 获取课程作业列表

```http
GET /api/student/courses/{course_id}/assignments
```

**功能说明：** 获取指定课程下的所有作业，可按小节和状态筛选。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| course_id | string | 是 | 课程 ID |

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| section_id | string | 否 | 按小节 ID 筛选 |
| status | string | 否 | open 或 closed |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "items": [
      {
        "id": "assignment_001",
        "title": "进程管理练习",
        "section_id": "section_001",
        "section_title": "第一章：进程管理",
        "due_at": "2026-06-15T23:59:00+08:00",
        "full_score": 100,
        "status": "open",
        "submitted": false,
        "score": null
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

> `submitted` 表示当前学生是否已提交；`score` 为批改后的得分，未批改时为 `null`。

---

### 1.2 获取作业详情

```http
GET /api/student/courses/{course_id}/assignments/{assignment_id}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "course_id": "course_001",
    "section_id": "section_001",
    "section_title": "第一章：进程管理",
    "title": "进程管理练习",
    "description": "完成关于进程状态转换的分析题，不少于 500 字。",
    "due_at": "2026-06-15T23:59:00+08:00",
    "full_score": 100,
    "status": "open",
    "attachment_url": "/files/assignment_001_topic.pdf",
    "submitted": false,
    "score": null
  },
  "message": "ok"
}
```

---

### 1.3 提交作业

```http
POST /api/student/courses/{course_id}/assignments/{assignment_id}/submit
```

**功能说明：** 学生提交作业内容，支持纯文本提交或文件上传（二选一）。文件提交时支持同时上传多个文件，由 C++ 文件处理服务逐文件提取文本。

**请求体（文本提交，Content-Type: application/json）：**

```json
{
  "content": "进程是程序执行的实体，包含程序计数器、寄存器和变量等资源...",
  "submit_type": "text"
}
```

**请求体（文件提交，Content-Type: multipart/form-data）：**

```text
submit_type=file
files=<一个或多个二进制文件，支持 PDF、TXT、DOC，单文件最大 10 MB>
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| submit_type | string | 是 | text（文本） 或 file（文件） |
| content | string | text 时必填 | 作业正文 |
| files | file[] | file 时必填 | 作业文件，支持多文件上传 |

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

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "submission_001",
    "assignment_id": "assignment_001",
    "submit_type": "file",
    "content": "学生提交的文本内容（仅 text/mixed 类型）",
    "file_urls": ["/files/submission_001_report.pdf", "/files/submission_001_code.zip"],
    "files": [
      { "filename": "实验报告.pdf", "file_url": "/files/submission_001_report.pdf", "file_size": 204800 },
      { "filename": "源代码.zip", "file_url": "/files/submission_001_code.zip", "file_size": 51200 }
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
> 权限：`role = teacher`，且是该课程的创建者。
>
> **创建作业**请使用 [课程小节 API](./sections.md) 第 5 节的接口。

### 2.1 获取课程作业列表

```http
GET /api/teacher/courses/{course_id}/assignments
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| section_id | string | 否 | 按小节 ID 筛选 |
| status | string | 否 | open 或 closed |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "items": [
      {
        "id": "assignment_001",
        "title": "进程管理练习",
        "section_id": "section_001",
        "section_title": "第一章：进程管理",
        "due_at": "2026-06-15T23:59:00+08:00",
        "full_score": 100,
        "status": "open",
        "submission_count": 25,
        "total_students": 35
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

### 2.2 获取作业详情

```http
GET /api/teacher/courses/{course_id}/assignments/{assignment_id}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "assignment_001",
    "course_id": "course_001",
    "section_id": "section_001",
    "title": "进程管理练习",
    "description": "完成关于进程状态转换的分析题，不少于 500 字。",
    "reference_answer": "参考答案内容...",
    "rubric": "满分 100 分，概念 40 分，分析 40 分，表达 20 分。",
    "due_at": "2026-06-15T23:59:00+08:00",
    "full_score": 100,
    "status": "open",
    "attachment_url": "/files/assignment_001_topic.pdf",
    "submission_count": 25,
    "total_students": 35,
    "created_at": "2026-06-04T10:00:00+08:00",
    "updated_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "ok"
}
```

---

### 2.3 更新作业

```http
PATCH /api/teacher/courses/{course_id}/assignments/{assignment_id}
```

**请求体：**

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

### 2.4 关闭作业

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

### 2.5 获取作业提交列表

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
        "content": "学生提交的文本内容（仅 text/mixed 类型）",
        "extracted_text": "C++ 从文件中提取的文本内容",
        "file_urls": ["/files/submission_001_report.pdf", "/files/submission_001_code.zip"],
        "files": [
          { "filename": "实验报告.pdf", "file_url": "/files/submission_001_report.pdf", "file_size": 204800 },
          { "filename": "源代码.zip", "file_url": "/files/submission_001_code.zip", "file_size": 51200 }
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

**功能说明：** 教师指定提交 ID 列表，系统调用 MiniMax 对学生提交进行 AI 批改，生成分数、评语、扣分点和修改建议。若学生以文件提交，系统使用 C++ 服务预先提取的文本参与批改。

**请求体：**

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
          {
            "point": "进程状态转换条件说明不完整",
            "minus": 6
          }
        ],
        "suggestions": ["补充阻塞态与就绪态的转换条件", "增加调度算法对比"],
        "confirmed": false
      },
      {
        "submission_id": "submission_002",
        "student_id": "user_002",
        "student_name": "李四",
        "ai_score": null,
        "comments": "无法提取文本内容，请确认提交内容格式正确",
        "deductions": [],
        "suggestions": [],
        "confirmed": false,
        "error": "no_content"
      }
    ]
  },
  "message": "graded"
}
```

> `ai_score` 不会超过作业设置的满分（`full_score`）。若学生只上传了无法解析的文件且未填写文本内容，ai_score 为 `null`，同时返回 `error: "no_content"`。

---

### 3.2 教师确认或调整批改结果

```http
PATCH /api/teacher/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}
```

**功能说明：** 教师对 AI 批改结果进行确认或手动调整最终分数，确认后分数将对学生可见。

**请求体：**

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
    "unconfirmed_count": 3,
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

**功能说明：** 对指定作业的一批提交同时执行查重和多维度比对。系统先调用 C++ 文件处理服务对提交文本进行预处理和指纹提取，再调用 MiniMax 进行语义相似度分析和比对，最终输出统一的分析报告。

**请求体：**

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
| compare_dimensions | array | 否 | 比对维度，默认全部（结构、概念、表达、结论） |

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
