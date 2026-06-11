# 智学伴侣 API 文档

## 概述

本文档为智学伴侣后端 API 设计的入口索引。后端使用 Python FastAPI 实现，前端 React 通过 HTTP JSON 接口访问后端服务，后端再根据业务需要访问数据库、MiniMax 大模型 API 和 C++ 文件处理服务。

**基础路径：** `/api`

---

## 通用约定

### 默认响应格式

```json
{
  "success": true,
  "data": {},
  "message": "ok"
}
```

### 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": "BAD_REQUEST",
    "message": "请求参数不合法"
  }
}
```

### HTTP 状态码

| 状态码 | 说明 |
| --- | --- |
| 200 | 请求成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未登录或 Token 无效 |
| 403 | 无权限（角色不匹配） |
| 404 | 资源不存在 |
| 422 | 参数校验失败 |
| 500 | 服务内部错误 |
| 502 | 大模型服务调用失败 |

### 时间格式

所有时间字段统一使用 ISO 8601 格式：

```text
2026-06-04T10:00:00+08:00
```

### 认证方式

除注册和登录接口外，所有接口均需在请求头中携带 JWT 令牌：

```text
Authorization: Bearer <token>
```

### 角色枚举

| 值 | 说明 |
| --- | --- |
| student | 学生 |
| teacher | 教师 |

### 作业状态枚举

| 值 | 说明 |
| --- | --- |
| open | 进行中（学生可提交） |
| closed | 已关闭（截止或教师手动关闭） |

### 课程状态枚举

| 值 | 说明 |
| --- | --- |
| active | 进行中 |
| archived | 已归档（只读，不可再加入） |

### 岗位方向枚举（career_direction）

| 值 | 中文 |
| --- | --- |
| backend | 后端开发 |
| frontend | 前端开发 |
| product | 产品经理 |
| algorithm | 算法工程师 |
| data | 数据分析 |
| devops | 运维/DevOps |
| other | 其他 |

---

## 模块索引

| 模块 | 文件 | 路由前缀 | 说明 |
| --- | --- | --- | --- |
| 认证与用户信息 | [api/auth.md](api/auth.md) | `/api/auth` | 注册、登录、个人信息（含兴趣/岗位方向）、修改密码 |
| 文件上传 | [api/assignments.md](api/assignments.md#零文件上传独立接口) | `/api/upload` | 独立文件上传接口，上传到文件服务器后返回可访问路径 |
| 课程管理 | [api/courses.md](api/courses.md) | `/api/teacher/courses`<br>`/api/student/courses` | 教师创建课程/按学号添加学生、课程码、学生加入/退出课程 |
| 课程小节 | [api/sections.md](api/sections.md) | `/api/teacher/courses/{id}/sections`<br>`/api/student/courses/{id}/sections` | 课程小节 CRUD、小节下发布作业 |
| 作业管理与批改 | [api/assignments.md](api/assignments.md) | `/api/student/courses/{id}/assignments`<br>`/api/teacher/courses/{id}/assignments` | 学生提交作业、教师管理/批改/查重/比对 |
| 课程公告 | [api/announcements.md](api/announcements.md) | `/api/courses/{id}/announcements` | 教师发布公告、学生查看（含已读状态） |
| 讨论 | [api/discussions.md](api/discussions.md) | `/api/courses/{id}/discussions` | 教师发起讨论，师生均可回复 |
| 提问 | [api/questions.md](api/questions.md) | `/api/courses/{id}/questions` | 学生向教师提问，支持公开/私密，教师回答 |
| 测试 | [api/quizzes.md](api/quizzes.md) | `/api/teacher/courses/{id}/quizzes`<br>`/api/student/courses/{id}/quizzes` | 教师发布测试（单选/多选/判断/简答），学生作答，系统自动批改 |
| 分数与成绩 | [api/scores.md](api/scores.md) | `/api/student/courses/{id}/scores`<br>`/api/student/scores`（跨课程聚合）<br>`/api/teacher/courses/{id}/scores` | 学生查看成绩明细和排名、教师查看班级分布 |
| 智能问答 | [api/chat.md](api/chat.md) | `/api/student/courses/{id}/chat` | 基于课程材料 RAG 检索的 AI 问答、会话历史 |
| 知识点总结 | [api/summaries.md](api/summaries.md) | `/api/student/courses/{id}/summaries` | 基于课程材料 RAG 或自定义文本生成结构化总结 |
| 个性化学习计划 | [api/learning_plans.md](api/learning_plans.md) | `/api/student/courses/{id}/learning-plans` | 综合 8 类信号生成计划；支持进度打卡、效果反馈、多轮调整 |

---

## 后端路由规划

| 模块 | 路由前缀 | 建议文件 |
| --- | --- | --- |
| 健康检查 | `/api/health` | `app/main.py` |
| 认证与用户信息 | `/api/auth` | `app/api/routes_auth.py` |
| 文件上传 | `/api/upload` | `app/api/routes_upload.py` |
| 课程管理 | `/api/teacher/courses`<br>`/api/student/courses` | `app/api/routes_courses.py` |
| 课程小节 | `/api/teacher/courses/{id}/sections`<br>`/api/student/courses/{id}/sections` | `app/api/routes_sections.py` |
| 作业管理与批改 | `/api/student/courses/{id}/assignments`<br>`/api/teacher/courses/{id}/assignments` | `app/api/routes_student_assignments.py`<br>`app/api/routes_teacher_assignments.py` |
| 课程公告 | `/api/courses/{id}/announcements` | `app/api/routes_announcements.py` |
| 讨论 | `/api/courses/{id}/discussions` | `app/api/routes_discussions.py` |
| 提问 | `/api/courses/{id}/questions` | `app/api/routes_questions.py` |
| 测试 | `/api/teacher/courses/{id}/quizzes`<br>`/api/student/courses/{id}/quizzes` | `app/api/routes_quizzes.py` |
| 分数与成绩 | `/api/student/courses/{id}/scores`<br>`/api/student/scores`<br>`/api/teacher/courses/{id}/scores` | `app/api/routes_scores.py` |
| 智能问答 | `/api/student/courses/{id}/chat` | `app/api/routes_chat.py` |
| 知识点总结 | `/api/student/courses/{id}/summaries` | `app/api/routes_summaries.py` |
| 个性化学习计划 | `/api/student/courses/{id}/learning-plans` | `app/api/routes_learning_plans.py` |

---

## 健康检查

```http
GET /api/health
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "service": "zhixue-companion-api"
  },
  "message": "ok"
}
```

---

## 前端接口封装建议

前端建议将 API 调用集中放在 `src/api` 目录中，统一在请求拦截器中注入 JWT 令牌：

```ts
// src/api/client.ts
import axios from 'axios';

const client = axios.create({ baseURL: '/api' });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default client;
```

建议按模块拆分封装文件：

| 文件 | 说明 |
| --- | --- |
| `src/api/auth.ts` | 注册、登录、获取/更新个人信息 |
| `src/api/courses.ts` | 课程加入、列表、详情 |
| `src/api/sections.ts` | 小节列表、详情 |
| `src/api/assignments.ts` | 学生提交、查看作业；教师发布、批改 |
| `src/api/announcements.ts` | 公告列表、详情 |
| `src/api/scores.ts` | 成绩明细、班级分布 |
| `src/api/chat.ts` | 智能问答、会话历史 |
| `src/api/summaries.ts` | 知识点总结 |
| `src/api/learningPlans.ts` | 个性化学习计划 |
