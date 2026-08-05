# 00_Glossary.md — 全平台术语表

> 来源：`docs/design/术语统一规范.md`（唯一术语事实来源）
> 本文件收录术语表类内容：核心概念、推荐名称、定义、推荐写法/不建议写法、备注。

# 全平台术语统一规范

> 本文档是全平台（Documents / Workflow / Knowledge Hub）的**唯一术语事实来源**。
> 所有页面文案、状态枚举、操作动词、Pipeline 阶段描述均以此为准，杜绝同名异义与前后端不一致。

## 1. 页面 / 模块命名

| 路径 | 英文名 | 中文名 | 职责 |
| --- | --- | --- | --- |
| `/documents` | Documents | 文档中心 | 文档上传、解析、分块、向量化状态展示 |
| `/workflow` | Workflow | 处理中心 | 任务/流水线编排与执行 |
| `/knowledge` | Knowledge Hub | 知识中台 | 知识图谱、实体、关系检索 |

> 导航栏与页面标题统一使用英文名（如 `Documents`），副标题/页面描述使用中文名（如「文档中心」）。

## 3. 文档状态枚举（后端事实来源）

以 `services/pipeline.py` 实际写入 `documents` 表 `status` 字段的值为准。

| 枚举值 | 中文标签 | 含义 |
| --- | --- | --- |
| `pending` | 待处理 | 已进入队列，等待处理 |
| `waiting_parser` | 等待解析器 | 等待解析器就绪 |
| `parse_failed` | 解析失败 | 解析阶段失败 |
| `parsed` | 已解析 | 解析完成，等待分块/向量化 |
| `indexed` | 已索引 | Parse + Chunk + Embedding 全完成 |
| `error` | 错误 | 处理过程中出错 |

> 前端**禁止**使用后端不存在的状态值（如 `parsing`、`embedded`）。

## 4. 任务状态

与任务系统（`tasks` 表 `stage` 字段）及 Knowledge Dashboard 现有常量一致：

`pending`（待处理）/ `running`（运行中）/ `done`（已完成）/ `failed`（失败）

## 5. 操作动词中英对照

| 中文 | 英文 |
| --- | --- |
| 查看 | Open |
| 重新处理 | Reprocess |
| 删除 | Delete |
| 重新向量化 | Re-embed |
| 查看图 | Graph |
| 查看分块 | Chunks |

## 7. 中文文案规范

- 标题、按钮、空态、描述使用中文
- 枚举值、字段名使用英文小写（如 `pending`、`indexed`）
- 状态列展示用中文标签（如「待处理」「已索引」），源值用小写英文