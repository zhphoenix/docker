# 状态枚举规范（文档状态 + 任务状态）

> 来源：`docs/design/术语统一规范.md` §3、§4

## 文档状态枚举（后端事实来源）

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

## 任务状态（tasks 表 stage 字段）

与任务系统（`tasks` 表 `stage` 字段）及 Knowledge Dashboard 现有常量一致：

`pending`（待处理）/ `running`（运行中）/ `done`（已完成）/ `failed`（失败）

## 使用约束

- 枚举值一律小写英文（`pending`、`indexed`）
- 展示用中文标签（如「待处理」「已索引」）
- 源值用小写英文，禁止混用大写的 `Pending`、`Parsing`