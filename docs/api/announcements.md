# 课程公告 API

> 基础路径：`/api/courses/{course_id}/announcements`
>
> 所有接口均需携带 JWT 令牌。

---

## 说明

教师可在课程内发布公告，用于通知实验室地点、课程安排变更、注意事项等。学生进入课程后可查看所有公告，未读公告数会在课程列表中以角标形式提示。

---

## 1. 教师发布公告

```http
POST /api/courses/{course_id}/announcements
```

**权限：** `role = teacher`，且是该课程的创建者。

**请求体：**

```json
{
  "title": "本周实验课地点变更",
  "content": "本周五（6月7日）的操作系统实验课改在 A303 机房进行，请同学们注意。",
  "is_pinned": false
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 公告标题 |
| content | string | 是 | 公告内容（支持纯文本，最大 5000 字） |
| is_pinned | boolean | 否 | 是否置顶，默认 false |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "notice_001",
    "course_id": "course_001",
    "title": "本周实验课地点变更",
    "content": "本周五（6月7日）的操作系统实验课改在 A303 机房进行，请同学们注意。",
    "is_pinned": false,
    "created_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "published"
}
```

---

## 2. 教师获取课程公告列表

```http
GET /api/courses/{course_id}/announcements
```

**权限：** `role = teacher`

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| page | integer | 否 | 页码，默认 1 |
| page_size | integer | 否 | 每页数量，默认 20 |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "items": [
      {
        "id": "notice_001",
        "title": "本周实验课地点变更",
        "is_pinned": false,
        "read_count": 28,
        "total_students": 35,
        "created_at": "2026-06-04T10:00:00+08:00"
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

## 3. 教师更新公告

```http
PATCH /api/courses/{course_id}/announcements/{notice_id}
```

**权限：** `role = teacher`

**请求体：**

```json
{
  "title": "本周实验课地点变更（已更新）",
  "content": "改在 A305 机房，不是 A303，请重新确认。",
  "is_pinned": true
}
```

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "notice_001",
    "title": "本周实验课地点变更（已更新）",
    "is_pinned": true,
    "updated_at": "2026-06-04T11:00:00+08:00"
  },
  "message": "updated"
}
```

---

## 4. 教师删除公告

```http
DELETE /api/courses/{course_id}/announcements/{notice_id}
```

**权限：** `role = teacher`

**响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "notice_001"
  },
  "message": "deleted"
}
```

---

## 5. 学生获取课程公告列表

```http
GET /api/courses/{course_id}/announcements
```

**功能说明：** 学生获取该课程的所有公告，置顶公告排在最前面。每次调用后，系统自动将该学生对所有返回公告的未读状态标为已读。

**权限：** `role = student`，且已加入该课程。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| page | integer | 否 | 页码，默认 1 |
| page_size | integer | 否 | 每页数量，默认 20 |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "course_id": "course_001",
    "unread_count": 1,
    "items": [
      {
        "id": "notice_001",
        "title": "本周实验课地点变更",
        "content": "本周五（6月7日）的操作系统实验课改在 A303 机房进行，请同学们注意。",
        "is_pinned": false,
        "is_read": false,
        "created_at": "2026-06-04T10:00:00+08:00"
      }
    ],
    "total": 1
  },
  "message": "ok"
}
```

---

## 6. 获取公告详情

```http
GET /api/courses/{course_id}/announcements/{notice_id}
```

**功能说明：** 获取公告详情。学生调用后自动标为已读；教师调用返回已读人数统计。

**权限：** 教师和学生均可访问（教师需是该课程创建者，学生需已加入课程）

**学生调用响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "notice_001",
    "course_id": "course_001",
    "title": "本周实验课地点变更",
    "content": "本周五（6月7日）的操作系统实验课改在 A303 机房进行，请同学们注意。",
    "is_pinned": false,
    "is_read": true,
    "created_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "ok"
}
```

**教师调用响应示例：**

```json
{
  "success": true,
  "data": {
    "id": "notice_001",
    "course_id": "course_001",
    "title": "本周实验课地点变更",
    "content": "本周五（6月7日）的操作系统实验课改在 A303 机房进行，请同学们注意。",
    "is_pinned": false,
    "read_count": 28,
    "total_students": 35,
    "created_at": "2026-06-04T10:00:00+08:00",
    "updated_at": "2026-06-04T10:00:00+08:00"
  },
  "message": "ok"
}
```
