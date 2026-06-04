# 个性化学习计划 API

> 基础路径：`/api/student/courses/{course_id}/learning-plans`
>
> 权限：`role = student`，且已加入该课程。
>
> 所有接口均需携带 JWT 令牌。

---

## 数据信号说明

学习计划生成时，后端会**自动采集**该学生在本课程内的所有可用数据，无需前端传入。数据信号包括以下几类：

| 信号类型 | 值（`data_sources`） | 采集内容 | 用途 |
| --- | --- | --- | --- |
| 作业成绩 | `scores` | 各作业得分、扣分点 | 定位掌握程度薄弱环节 |
| 测试成绩 | `quizzes` | 各测试得分、错题内容 | 从客观题错误直接提取薄弱知识点 |
| 个人信息 | `profile` | `interests`（兴趣）、`career_direction`（岗位方向） | 调整计划侧重和举例方向 |
| AI 问答记录 | `chat_sessions` | 最近提问内容 | 识别反复疑惑的概念 |
| 知识点总结记录 | `summaries` | 已生成总结的小节标题 | 识别主动复习覆盖情况 |
| 提问记录 | `questions` | 向教师提问的问题标题 | 定位认知卡点 |
| 讨论参与记录 | `discussions` | 参与讨论的话题标题 | 辅助判断学习投入度 |
| 课程材料（RAG） | `course_materials` | 与薄弱知识点相关的课件片段 | 确保计划任务与课程实际内容对齐 |

**个人信息**可在 [认证 API](./auth.md) 的「更新个人信息」接口中填写。

---

## 一、计划生成与查看

### 1.1 生成个性化学习计划

```http
POST /api/student/courses/{course_id}/learning-plans
```

**功能说明：** 后端自动采集上述全部可用数据，结合 RAG 检索课程材料，调用 MiniMax 生成定制化学习计划。

**请求体：**

```json
{
  "goal": "两周内提升进程调度相关知识点的掌握程度",
  "available_time_per_day": 60
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| goal | string | 否 | 学习目标描述，不填则由 AI 根据采集到的薄弱点自动制定 |
| available_time_per_day | integer | 否 | 每天可用学习时间（分钟），默认 60 |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "plan_001",
    "course_id": "course_001",
    "course_name": "操作系统",
    "career_direction": "backend",
    "version": 1,
    "parent_plan_id": null,
    "data_sources": ["scores", "quizzes", "profile", "chat_sessions", "questions", "course_materials"],
    "analysis": {
      "current_level": "基础概念掌握一般，进程调度和内存分页部分偏弱",
      "weak_points": ["进程状态转换", "调度算法对比"],
      "career_relevance": "进程调度和并发模型是后端开发的重要基础，建议重点加强",
      "priority": "先补齐进程状态转换，再横向对比调度算法"
    },
    "rag_references": [
      {
        "section_id": "section_001",
        "section_title": "第一章：进程管理",
        "file_name": "section_001_slides.pdf",
        "excerpt": "进程的五种状态及转换条件如下..."
      }
    ],
    "plan": [
      {
        "day": 1,
        "task": "精读课件第 12-18 页「进程状态转换图」，重点理解阻塞态与挂起态的区别",
        "duration_minutes": 60,
        "section_id": "section_001",
        "section_title": "第一章：进程管理"
      },
      {
        "day": 2,
        "task": "整理 FCFS、SJF、时间片轮转三种算法差异，结合后端开发场景理解",
        "duration_minutes": 60,
        "section_id": "section_001",
        "section_title": "第一章：进程管理"
      }
    ],
    "created_at": "2026-06-10T20:00:00+08:00"
  },
  "message": "created"
}
```

> `version` 为计划版本号，首次生成为 1，每次调整后 +1。`parent_plan_id` 指向被替代的上一版计划。

---

### 1.2 获取学习计划列表

```http
GET /api/student/courses/{course_id}/learning-plans
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| status | string | 否 | active、completed 或 archived |

---

### 1.3 获取学习计划详情

```http
GET /api/student/courses/{course_id}/learning-plans/{plan_id}
```

---

### 1.4 更新学习计划状态

```http
PATCH /api/student/courses/{course_id}/learning-plans/{plan_id}/status
```

**请求体：** `{ "status": "completed" }`

**状态说明：**

| 值 | 说明 |
| --- | --- |
| active | 进行中（默认） |
| completed | 学生主动标记完成 |
| archived | 被新版本替代后自动归档，也可手动归档 |

---

## 二、进度跟踪

### 2.1 标记任务完成

```http
POST /api/student/courses/{course_id}/learning-plans/{plan_id}/progress
```

**功能说明：** 学生标记某天任务的完成情况，可同时填写文字反馈。重复调用时更新已有记录。

**请求体：**

```json
{
  "day": 1,
  "completed": true,
  "feedback": "已掌握，进程状态转换比较清楚了"
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| day | integer | 是 | 对应计划中的 day 字段 |
| completed | boolean | 是 | 是否完成 |
| feedback | string | 否 | 完成情况说明，也是多轮调整的输入来源 |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "plan_id": "plan_001",
    "day": 1,
    "completed": true,
    "feedback": "已掌握，进程状态转换比较清楚了",
    "completed_at": "2026-06-11T21:00:00+08:00"
  },
  "message": "updated"
}
```

---

### 2.2 获取计划进度

```http
GET /api/student/courses/{course_id}/learning-plans/{plan_id}/progress
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "plan_id": "plan_001",
    "version": 1,
    "total_days": 5,
    "completed_days": 2,
    "completion_rate": 0.40,
    "tasks": [
      {
        "day": 1,
        "task": "精读课件第 12-18 页「进程状态转换图」",
        "duration_minutes": 60,
        "section_id": "section_001",
        "section_title": "第一章：进程管理",
        "completed": true,
        "feedback": "已掌握，进程状态转换比较清楚了",
        "completed_at": "2026-06-11T21:00:00+08:00"
      },
      {
        "day": 2,
        "task": "整理 FCFS、SJF、时间片轮转三种算法差异",
        "duration_minutes": 60,
        "section_id": "section_001",
        "section_title": "第一章：进程管理",
        "completed": false,
        "feedback": null,
        "completed_at": null
      }
    ]
  },
  "message": "ok"
}
```

---

## 三、效果反馈

### 3.1 查看计划实施效果

```http
GET /api/student/courses/{course_id}/learning-plans/{plan_id}/effect
```

**功能说明：** 对比计划创建时间前后的作业得分变化，量化学习计划的实际效果。

**响应示例：**

```json
{
  "success": true,
  "data": {
    "plan_id": "plan_001",
    "plan_created_at": "2026-06-10T20:00:00+08:00",
    "assignment_effect": {
      "before": {
        "count": 2,
        "avg_rate": 0.68,
        "records": [
          { "title": "进程管理练习", "score": 68, "full_score": 100, "rate": 0.68 }
        ]
      },
      "after": {
        "count": 1,
        "avg_rate": 0.85,
        "records": [
          { "title": "调度算法分析", "score": 85, "full_score": 100, "rate": 0.85 }
        ]
      },
      "improvement": 0.17
    },
    "note": "improvement > 0 表示计划实施后成绩有所提升"
  },
  "message": "ok"
}
```

> `improvement = 0.17` 表示均分提升了 17 个百分点。

---

## 四、多轮调整

### 4.1 调整学习计划

```http
POST /api/student/courses/{course_id}/learning-plans/{plan_id}/adjust
```

**功能说明：** 当学生觉得计划过难、过于简单或需要改变侧重时，可提交反馈申请调整。系统会：
1. 读取当前计划的完成进度（已打卡的任务）
2. 将进度数据 + 学生反馈 + 原计划一起发给 MiniMax
3. AI 保留已完成任务，只调整剩余部分
4. 将旧计划状态改为 `archived`，返回新版本计划（`version +1`）

**请求体：**

```json
{
  "feedback": "第 2、3 天关于调度算法的内容对我来说太难了，希望增加基础题练习，减少代码实现的要求",
  "available_time_per_day": 45
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| feedback | string | 是 | 学生对当前计划的反馈，描述哪里难/简单/想调整 |
| available_time_per_day | integer | 否 | 重新指定每天可用时间，不填则沿用上一版设置 |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "plan_002",
    "course_id": "course_001",
    "course_name": "操作系统",
    "career_direction": "backend",
    "version": 2,
    "parent_plan_id": "plan_001",
    "data_sources": ["scores", "quizzes", "profile", "chat_sessions", "course_materials"],
    "analysis": {
      "adjustment_reason": "第 2-3 天调度算法内容对学生难度较大，将代码实现改为概念梳理和基础练习",
      "completed_days": 1,
      "remaining_days": 4
    },
    "plan": [
      {
        "day": 1,
        "task": "精读课件第 12-18 页「进程状态转换图」",
        "duration_minutes": 45,
        "section_id": "section_001",
        "section_title": "第一章：进程管理"
      },
      {
        "day": 2,
        "task": "阅读 FCFS 和 SJF 算法概念，完成课件中 5 道填空题，不要求代码实现",
        "duration_minutes": 45,
        "section_id": "section_001",
        "section_title": "第一章：进程管理"
      }
    ],
    "created_at": "2026-06-13T09:00:00+08:00"
  },
  "message": "adjusted"
}
```

> 调整后旧计划（`plan_001`）状态变为 `archived`，新计划（`plan_002`）自动激活。通过 `parent_plan_id` 可以追溯完整的版本链。

---

## 五、计划版本链示例

```
plan_001 (version=1, status=archived)
    ↓ parent_plan_id
plan_002 (version=2, status=archived)
    ↓ parent_plan_id
plan_003 (version=3, status=active)   ← 当前进行中
```

学生可通过 `GET /learning-plans?status=archived` 查看所有历史版本。
