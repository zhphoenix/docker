# 00_Architecture_Decisions.md — 架构决策

> 来源：`docs/design/术语统一规范.md`（唯一术语事实来源）
> 本文件收录架构决策类内容：术语冲突清单、Agent 与模块命名对齐、演进规划等。

## 6. 旧值映射表

前端误用值 → 后端真实枚举：

| 旧（误用） | 新（真实） | 说明 |
| --- | --- | --- |
| `parsing` | `parsed` / `indexed` | 解析中不存在，按 `parsed` 或 `indexed` 展示 |
| `embedded` | `indexed` | 已完成向量化即 `indexed` |
| `failed` | `parse_failed` / `error` | 解析失败用 `parse_failed`，其他错误用 `error` |