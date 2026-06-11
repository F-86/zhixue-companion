# 智学伴侣 · 文件处理层设计

本文档描述 `app/file_processing/` 的架构、接口、降级策略以及与 C++ pybind11 扩展的关系。

> C++ 扩展的原始接口文档见 [cpp_api.md](../cpp_api.md)，本文档聚焦 Python 封装层。

---

## 1. 定位

```
                app/services/analyze_service.py
                app/api/routes_upload.py
                        │
                        ▼
            app/file_processing/processor.py    ← Python 封装层（本文档）
                        │
                        ▼
          cpp_processor/file_processor.so       ← C++ pybind11 扩展
```

`file_processing/` 是对 C++ pybind11 扩展的 **Python 门面层**，职责包括：

| 职责 | 说明 |
|------|------|
| 延迟导入 | C++ 扩展未编译时静默降级，不阻断主进程启动 |
| 异常转换 | 将 C++ 的 `ValueError`/`RuntimeError` 转为日志 + `None`/`[]` |
| 日志桥接 | 将错误详情写入 C++ 日志文件，供调试用 |
| 降级策略 | 扩展不可用时返回安全的默认值，保证服务可用 |

---

## 2. 模块结构

```
app/file_processing/
├── __init__.py       # 公开导出：extract_text, preprocess, get_fingerprint, batch_compare
└── processor.py      # 实现：导入检测、异常封装、降级逻辑
```

### 2.1 `__init__.py`

```python
from app.file_processing.processor import (
    extract_text,
    preprocess,
    get_fingerprint,
    batch_compare,
)
```

对外暴露四个函数，调用方无需关心内部导入细节。

### 2.2 可用性检测

```python
try:
    import file_processor as _fp
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
```

模块加载时即检测，整个进程生命周期内状态不变。日志会明确提示扩展状态：

```
INFO  file_processor 扩展加载成功
# 或
WARNING  file_processor 扩展未找到，文件处理功能将降级（仅支持文本提交）
```

---

## 3. 公开接口

### 3.1 `extract_text(file_path: str) -> str | None`

从上传文件中提取纯文本。

| 项目 | 说明 |
|------|------|
| 支持格式 | `.txt`、`.pdf` |
| 成功返回 | 提取的纯文本字符串 |
| 扩展不可用 | 返回 `None` |
| C++ 异常 | 捕获后返回 `None`，写入 C++ 日志 |
| 调用者 | `routes_upload.py`（文件上传时） |

**降级含义**：返回 `None` 意味着提交内容为空字符串，学生需手动输入文本内容。不阻断提交流程。

### 3.2 `preprocess(text: str) -> list[str]`

对文本进行去噪和分段，返回段落列表。

| 项目 | 说明 |
|------|------|
| 处理步骤 | 去除连续空白行 → 去除不可见字符 → 按双换行切分 → 过滤短段落（< 10 字符） |
| 扩展不可用 | 返回 `[]` |
| 输入为空 | 返回 `[]` |
| 调用者 | `analyze_service.py`（查重分析预处理） |

### 3.3 `get_fingerprint(text: str, window_size: int = 5) -> list[int]`

计算文本指纹（滑动窗口哈希），用于快速相似度粗筛。

| 项目 | 说明 |
|------|------|
| 算法 | Rabin-Karp 风格滑动窗口哈希 |
| window_size | 2~20，默认 5（词数） |
| 返回值 | 哈希值整数列表，长度 ≈ 词数 − window_size + 1 |
| 扩展不可用 | 返回 `[]` |
| 调用者 | `analyze_service.py`（构建指纹数据存入 `AnalysisReport.fingerprint_data`） |

### 3.4 `batch_compare(texts: list[str], threshold: float = 0.8) -> list[tuple[int, int, float]]`

对多份文本进行两两指纹相似度粗筛。

| 项目 | 说明 |
|------|------|
| threshold | 0.0~1.0，默认 0.8，超过此值的对才返回 |
| 返回值 | `[(i, j, similarity), ...]` 三元组列表 |
| **降级行为** | 扩展不可用时返回**全量两两组合**（similarity=1.0） |
| 异常时 | 返回 `[]` |
| 调用者 | `analyze_service.py`（查重分析的预筛选阶段） |

**降级行为是关键设计**：C++ 扩展的粗筛目的是**减少**送入 MiniMax 的比对对数量。若扩展不可用，返回全量组合意味着让 MiniMax 分析所有对，虽然成本更高，但功能完整可用。

---

## 4. 降级策略矩阵

| 场景 | `extract_text` | `preprocess` | `get_fingerprint` | `batch_compare` |
|------|:--:|:--:|:--:|:--:|
| C++ 扩展未编译 (`_AVAILABLE=False`) | 返回 `None` | 返回 `[]` | 返回 `[]` | 返回全量组合 `[(0,1,1.0),(0,2,1.0),...]` |
| C++ 抛 `ValueError`（参数非法） | 返回 `None` + 日志 | 返回 `[]` | 返回 `[]` | 返回 `[]` |
| C++ 抛 `RuntimeError`（文件/解析失败） | 返回 `None` + 日志 | — | — | 返回 `[]` |

**核心原则**：文件处理层的函数永不抛异常给上层，所有错误都转为安全默认值 + 日志记录。

---

## 5. 与业务层的交互

### 5.1 文件上传流程

```
POST /api/upload
    │
    ▼
routes_upload.py
    │ 保存文件到磁盘
    ▼
file_processing.extract_text(save_path)
    │
    ├── 成功 → 返回文本 → 存入 File.extracted_text
    │
    └── None → 文本为空，不影响文件记录创建
```

用户上传课件/作业附件时，系统同步调用 `extract_text`。文本提取失败（如 PDF 不含文本层）不阻断上传，只是后续 AI 批改/分析可能无文本可用。

### 5.2 查重分析流程

```
POST /api/teacher/assignments/{id}/analyze
    │
    ▼
analyze_service.analyze()
    │
    ├── 1. 收集所有提交文本
    │
    ├── 2. get_fingerprint(text)  → 每份提交的指纹
    │       存入 AnalysisReport.fingerprint_data（调试用）
    │
    ├── 3. batch_compare(texts, threshold)  → 可疑对列表
    │       降级时返回全量组合
    │
    ├── 4. 将可疑对 + 原始文本送给 MiniMax 精确分析
    │
    └── 5. 合并 MiniMax 结果，写入 AnalysisReport
```

C++ 粗筛的理想效果是：100 份提交 × 99/2 ≈ 4950 个组合对 → 经指纹粗筛 → 仅 20~50 个可疑对送入 MiniMax，大幅节省 API 调用成本。

---

## 6. 日志体系

| 日志通道 | 写入位置 | 内容 |
|---------|---------|------|
| Python `logging` | stderr / uvicorn 日志 | 扩展加载状态、每次函数调用的异常概要 |
| C++ `write_log` | `logs/file_processor.log` | C++ 内部错误的详细信息（PDF 解析失败原因等） |

两层日志各司其职：Python 日志用于运维监控，C++ 日志用于定位具体文件处理问题。

---

## 7. 扩展与迁移

### 7.1 新增文件格式支持

1. 在 C++ `extractor.cpp` 中增加新格式的解析逻辑
2. 重新编译 `file_processor.so`
3. Python 封装层无需修改（`extract_text` 接口不变）

### 7.2 从 pybind11 迁移到 gRPC 微服务

1. 新建独立 gRPC 服务，提供相同的四个接口
2. 修改 `app/file_processing/processor.py`，将 `import file_processor` 替换为 gRPC stub 调用
3. 业务层代码（`analyze_service.py`、`routes_upload.py`）无需任何修改

封装层的存在使替换实现零业务影响。

### 7.3 扩展不可用时的功能影响

| 功能 | 影响 |
|------|------|
| 课件文本提取 | 小节无 `material_text`，RAG 检索无数据，问答退化为通用回答 |
| 作业附件文本提取 | 提交无 `extracted_text`，AI 批改/查重无文本可用 |
| 查重指纹粗筛 | 跳过预筛选，全量送入 MiniMax（成本增加，功能可用） |
