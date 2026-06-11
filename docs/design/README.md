# 智学伴侣 · 设计文档索引

本目录收录项目所有设计文档，覆盖总体架构到专项模块。

| 文档 | 说明 |
|------|------|
| [architecture.md](architecture.md) | 整体架构、分层模型、技术选型决策 |
| [data_model.md](data_model.md) | 完整数据模型（17+ 张表），含 E-R 关系、字段说明、设计意图 |
| [database_layer.md](database_layer.md) | 数据库层设计：仓库模式、会话管理、向量存储、初始化流程 |
| [services_db_interaction.md](services_db_interaction.md) | 服务层与数据库层交互：三种实现模式、Session 生命周期、权限校验链 |
| [file_processing.md](file_processing.md) | 文件处理层设计：Python 封装层接口、降级策略、C++ 扩展关系 |
| [ai_design.md](ai_design.md) | AI 功能设计：RAG 检索、学习计划、智能问答、批改、查重 |
| [security_design.md](security_design.md) | 安全设计：JWT、密码存储、权限模型、防御策略 |

> API 接口文档见 [../api/](../api/) 目录。

## 快速导航

- **了解项目全貌** → [architecture.md](architecture.md)
- **理解数据结构** → [data_model.md](data_model.md)
- **理解数据库层** → [database_layer.md](database_layer.md)
- **理解服务与数据交互** → [services_db_interaction.md](services_db_interaction.md)
- **理解文件处理层** → [file_processing.md](file_processing.md)
- **对接 API** → [../api/](../api/)
- **深入 AI 功能** → [ai_design.md](ai_design.md)
- **安全评审** → [security_design.md](security_design.md)
