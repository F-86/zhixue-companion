# 智学伴侣 · 数据模型设计

> 数据操作代码位于 `app/db/repositories/`（详情见 [database_layer.md](database_layer.md)），服务层与数据库的交互模式见 [services_db_interaction.md](services_db_interaction.md)。

## 1. E-R 总览

```
User ──< CourseEnrollment >── Course ──< Section
                                  │
                              Assignment ──< Submission ──── AIGradingResult
                                  │
                              AnalysisReport
                              
Course ──< Quiz ──< QuizQuestion
                └── QuizAttempt ──< QuizAnswer

Course ──< ChatMessage
Course ──< Summary
Course ──< LearningPlan ──< PlanTaskProgress
Course ──< Announcement ──< AnnouncementRead
Course ──< Discussion ──< DiscussionReply
Course ──< Question ──< QuestionAnswer

File ──< SubmissionFile >── Submission
```

---

## 2. 用户与课程

### 2.1 User（用户）

```
users
├── id            String PK          UUID，应用层生成
├── username      String UNIQUE       登录名（学号 / 工号）
├── name          String              真实姓名
├── role          String              student | teacher
├── password_hash String              bcrypt 哈希
├── extra         JSON                扩展信息（见下）
└── created_at    DateTime(tz=UTC)
```

**extra 字段结构**

| role | 字段 | 说明 |
|------|------|------|
| student | `class_name` | 班级名称（如"计算机2301"） |
| student | `interests` | 兴趣列表，用于学习计划信号 |
| student | `career_direction` | 就业方向，用于计划个性化 |
| teacher | `courses` | 所教课程列表（string[]） |

**设计意图**：用 JSON extra 而非多个可空列，避免 schema 随业务扩展频繁变更，同时保持单表查询效率。

---

### 2.2 Course（课程）

```
courses
├── id            String PK
├── teacher_id    String INDEX        外键逻辑关联 users.id
├── name          String
├── description   Text nullable
├── code          String(6) UNIQUE    6 位课程码，学生加入用
├── semester      String nullable     如"2025春"
├── cover_image_url String nullable
├── status        String              active | archived
├── created_at    DateTime(tz=UTC)
└── updated_at    DateTime(tz=UTC)    onupdate 自动更新
```

**course_enrollments（学生-课程关联）**

```
course_enrollments
├── id         String PK
├── course_id  String INDEX
├── student_id String INDEX
└── joined_at  DateTime(tz=UTC)
```

**设计意图**：6 位课程码（`_gen_code()`）避免 ID 暴露，学生用码加入；不设唯一约束于 `(course_id, student_id)` 是待完善点（重复加入应拒绝）。

---

### 2.3 Section（课程小节）

```
sections
├── id               String PK
├── course_id        String INDEX
├── title            String
├── description      Text nullable
├── order            Integer          排序序号，越小越靠前
├── material_path    String nullable  课件文件路径
├── material_text    Text nullable    C++ 提取的课件文本
├── material_hash    String nullable  SHA-256，用于增量索引比对
├── created_at       DateTime(tz=UTC)
└── updated_at       DateTime(tz=UTC)
```

**material_hash 工作流**：

```
上传课件 → C++ 提取文本 → 计算 SHA-256
     ↓                          ↓
  存 material_text        与 material_hash 比对
                               ↓（不同 / 首次）
                          删除旧向量 → 重新 Embedding → 更新 hash
```

### 2.4 File（上传文件）

```
files
├── id              String PK
├── filename        String        原始文件名
├── file_path       String        存储路径
├── file_size       Integer       文件大小（字节）
├── extracted_text  Text nullable C++ pybind11 提取的文本
├── uploaded_by     String        上传者 user_id
└── created_at      DateTime(tz=UTC)
```

**设计意图**：通用文件表与业务实体解耦，通过 `SubmissionFile` 关联表桥接到作业提交。`extracted_text` 由 C++ 文件处理后写入，供 AI 批改和查重使用。

### 2.5 SubmissionFile（提交-文件关联）

```
submission_files
├── id              String PK
├── submission_id   String INDEX
├── file_id         String INDEX
└── created_at      DateTime(tz=UTC)
```

多对多关联：一份提交可包含多个文件，一个文件可被多次引用。

---

## 3. 作业系统

### 3.1 Assignment（作业）

```
assignments
├── id               String PK
├── teacher_id       String
├── course_id        String INDEX
├── section_id       String nullable INDEX  可归属到某小节
├── title            String
├── course           String              冗余字段，方便不 JOIN 显示
├── full_score       Float               满分（默认 100）
├── description      Text                作业要求
├── reference_answer Text nullable       参考答案
├── rubric           Text nullable       评分标准
├── attachment_path  String nullable     附件路径
├── attachment_text  Text nullable       C++ 解析的附件文本
├── due_at           DateTime(tz=UTC)    截止时间
├── status           String              open | closed
├── created_at       DateTime(tz=UTC)
└── updated_at       DateTime(tz=UTC)
```

**冗余 course 字段**：列表接口不 JOIN courses 表，减少查询复杂度，写入时由服务层保证一致性。

---

### 3.2 Submission（提交）

```
submissions
├── id              String PK
├── assignment_id   String
├── student_id      String
├── submit_type     String          text | file
├── content         Text nullable   文本提交内容
├── file_path       String nullable 文件路径
├── extracted_text  Text nullable   C++ pybind11 提取的文本
├── submitted_at    DateTime(tz=UTC)
└── status          String          submitted
```

---

### 3.3 AIGradingResult（AI 批改结果）

```
ai_grading_results
├── id              String PK
├── submission_id   String UNIQUE    一份提交只有一条批改记录
├── ai_score        Float nullable   AI 建议分
├── comments        Text nullable    总体评语
├── deductions      JSON             扣分点列表 [{"point": "...", "minus": 5}, ...]
├── suggestions     JSON             修改建议列表
├── confirmed       Boolean          教师是否已确认（默认 False）
├── final_score     Float nullable   教师最终分（可覆盖 ai_score）
├── teacher_comment Text nullable    教师补充评语
└── created_at      DateTime(tz=UTC)
```

**双分字段设计**：`ai_score` 是 AI 建议，`final_score` 是教师最终结果。未 confirmed 时 `final_score` 为 null，学情分析只使用 `confirmed=True` 的记录。

---

### 3.4 AnalysisReport（查重比对报告）

```
analysis_reports
├── id                  String PK
├── assignment_id       String          每作业最多一份报告
├── suspicious_pairs    JSON            可疑对列表
├── comparison_details  JSON            比对详情
├── common_issues       JSON            共同问题
├── teaching_suggestions JSON          教学建议
├── fingerprint_data    JSON            C++ 指纹数据（调试用）
└── created_at          DateTime(tz=UTC)
```

**存储策略**：每次分析覆盖更新（`upsert by assignment_id`），不保留历史分析版本。

---

## 4. 测验系统

### 4.1 Quiz（测验）

```
quizzes
├── id                String PK
├── course_id         String INDEX
├── section_id        String nullable INDEX
├── teacher_id        String
├── title             String
├── description       Text nullable
├── time_limit_minutes Integer nullable  None = 不限时
├── status            String            open | closed
├── created_at        DateTime(tz=UTC)
└── updated_at        DateTime(tz=UTC)
```

---

### 4.2 QuizQuestion（测验题目）

```
quiz_questions
├── id              String PK
├── quiz_id         String INDEX
├── question_type   String       single_choice | multi_choice | true_false | short_answer
├── content         Text         题目内容
├── options         JSON         选择题选项 [{"key": "A", "text": "..."}]
├── correct_answer  Text nullable 答案（选择题=key，判断题=true/false，简答=参考文本）
├── explanation     Text nullable 解析
├── score           Float         题目分值（默认 10）
├── order           Integer       显示顺序
└── created_at      DateTime(tz=UTC)
```

---

### 4.3 QuizAttempt / QuizAnswer（作答记录）

```
quiz_attempts
├── id           String PK
├── quiz_id      String INDEX
├── student_id   String INDEX
├── status       String          in_progress | submitted
├── total_score  Float nullable  客观题自动得分 + 简答题 AI 批改后累计
├── full_score   Float nullable
├── started_at   DateTime(tz=UTC)
└── submitted_at DateTime nullable

quiz_answers
├── id           String PK
├── attempt_id   String INDEX
├── question_id  String INDEX
├── answer       Text nullable   学生答案
├── is_correct   Boolean nullable 客观题判断 / 简答题 AI 批改后填入
├── score        Float nullable
├── ai_feedback  Text nullable   简答题 AI 评语
└── created_at   DateTime(tz=UTC)
```

---

## 5. AI 功能相关

### 5.1 ChatMessage（问答消息）

```
chat_messages
├── id          String PK
├── user_id     String
├── session_id  String INDEX    同一会话的消息共享 session_id
├── course_id   String nullable INDEX
├── section_id  String nullable
├── role        String          user | assistant
├── content     Text
└── created_at  DateTime(tz=UTC)
```

**会话管理**：session_id 由客户端首次为空时服务端生成（UUID），后续请求携带以延续会话。每次查询加载最近 10 条历史（5 轮对话）。

---

### 5.2 Summary（知识总结）

```
summaries
├── id           String PK
├── user_id      String
├── course_id    String nullable INDEX
├── section_id   String nullable INDEX
├── title        String
├── source_text  Text nullable    自由输入时有值，RAG 模式为 None
├── summary_type String           structured | brief | review
├── rag_used     Boolean          内容是否来自课程材料 RAG
├── result       JSON             结构化结果（overview/key_points/...）
└── created_at   DateTime(tz=UTC)
```

---

### 5.3 LearningPlan（学习计划）

```
learning_plans
├── id              String PK
├── student_id      String
├── course_id       String INDEX
├── course          String          冗余课程名
├── version         Integer         版本号，初始 1，调整时 +1
├── parent_plan_id  String nullable INDEX  调整时指向上一版
├── data_sources    JSON            信号来源标签列表
├── basis           JSON            生成依据（成绩/问答/总结/etc.）
├── plan            JSON            按天任务列表
├── analysis        JSON            学情分析（current_level/weak_points/...）
├── status          String          active | completed | archived
├── created_at      DateTime(tz=UTC)
└── updated_at      DateTime(tz=UTC)
```

**版本链设计**：调整计划时，旧版 status 改为 `archived`，新版的 `parent_plan_id` 指向旧版，形成链式版本历史。

---

### 5.4 PlanTaskProgress（计划任务进度）

```
plan_task_progress
├── id            String PK
├── plan_id       String INDEX
├── student_id    String INDEX
├── day           Integer      对应 plan 数组中的 day 字段
├── completed     Boolean
├── feedback      Text nullable 如"太难了"、"已掌握"
├── completed_at  DateTime nullable
└── created_at    DateTime(tz=UTC)
```

---

## 6. 课程互动

### 6.1 Announcement（公告）

```
announcements
├── id          String PK
├── course_id   String INDEX
├── title       String
├── content     Text
├── is_pinned   Boolean        置顶
├── created_at  DateTime(tz=UTC)
└── updated_at  DateTime(tz=UTC)

announcement_reads（已读记录）
├── id               String PK
├── announcement_id  String INDEX
├── student_id       String INDEX
└── read_at          DateTime(tz=UTC)
```

---

### 6.2 Discussion / DiscussionReply（讨论）

```
discussions
├── id          String PK
├── course_id   String INDEX
├── section_id  String nullable INDEX
├── title       String
├── content     Text
├── created_by  String              user_id（教师或学生均可发起）
├── status      String              open | closed
├── created_at  DateTime(tz=UTC)
└── updated_at  DateTime(tz=UTC)

discussion_replies
├── id              String PK
├── discussion_id   String INDEX
├── author_id       String
├── content         Text
└── created_at      DateTime(tz=UTC)
```

---

### 6.3 Question / QuestionAnswer（提问）

```
questions
├── id          String PK
├── course_id   String INDEX
├── section_id  String nullable INDEX
├── asked_by    String          学生 user_id
├── title       String
├── content     Text nullable
├── visibility  String          public | private
├── status      String          unanswered | answered
└── created_at  DateTime(tz=UTC)

question_answers
├── id           String PK
├── question_id  String UNIQUE INDEX  一问只有一答
├── answered_by  String               教师 user_id
├── content      Text
└── answered_at  DateTime(tz=UTC)
```

---

## 7. 数据一致性策略

| 场景 | 策略 |
|------|------|
| 软外键 | 不设数据库级外键约束，由应用层 `_require_*` 函数保证 |
| 级联删除 | 删小节时服务层显式删关联作业：`db.query(Assignment).filter(...).delete()` |
| 冗余字段 | `assignment.course` / `learning_plan.course` 写入时由服务层保证与主表一致 |
| 向量库同步 | 删小节时调用 `delete_chunks_by_section()`，向量库与关系库保持一致 |
| 批改状态 | `confirmed=False` 为 AI 建议，`confirmed=True` + `final_score not null` 才计入成绩 |

---

## 8. 主键策略

所有表使用 `str(uuid.uuid4())` 作为主键，应用层生成（非数据库自增）。

**优点**：
- 不依赖数据库特性，SQLite 和 PostgreSQL 行为一致
- 可在创建对象时就知道 ID，无需 flush/refresh
- 便于水平拆分（无全局自增冲突）

**注意**：UUID 字符串以 `String` 类型存储而非 `UUID` 类型，兼容 SQLite。

---

## 9. 时区约定

所有 `DateTime` 字段均声明 `timezone=True`，存储 UTC 时间。  
默认值函数：

```python
def _now() -> datetime:
    return datetime.now(timezone.utc)
```

前端展示时再转换为本地时间。
