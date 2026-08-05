# 旧值映射表（前端误用值 → 后端真实枚举）

> 来源：`docs/design/术语统一规范.md` §6

## 映射表

| 旧（误用） | 新（真实） | 说明 |
| --- | --- | --- |
| `parsing` | `parsed` / `indexed` | 解析中不存在，按 `parsed` 或 `indexed` 展示 |
| `embedded` | `indexed` | 已完成向量化即 `indexed` |
| `failed` | `parse_failed` / `error` | 解析失败用 `parse_failed`，其他错误用 `error` |

## 使用场景

- 前端展示历史数据或旧接口返回时，若出现左侧误用值，按右侧真实枚举映射
- 撰写调用后端状态处理逻辑时，直接使用真实枚举，无需映射
- 新增代码**禁止**再写入左侧误用值