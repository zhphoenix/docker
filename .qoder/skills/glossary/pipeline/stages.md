# 文档 Pipeline 三阶段规范

> 来源：`docs/design/术语统一规范.md` §2

## 真实阶段（固定三阶段）

```
Parse → Chunk → Embedding
```

| 阶段 | 名称 | 职责 |
| --- | --- | --- |
| Parse | 解析 | Docling 解析文档（MinIO 下载 → 解析） |
| Chunk | 分块 | 将解析结果分片为 Chunk |
| Embedding | 向量化 | 向量化并写入 Qdrant / PostgreSQL |

## 阶段离散规则

- **Entity / Graph（实体 / 图）不属文档 Pipeline**，由独立「知识图谱模块（KG）」处理
- 在文档详情区标注「由知识图谱模块处理」
- **不放入文档阶段进度条**
- 禁止将 Entity / Graph 作为 Pipeline 的第四、第五阶段展示

## 使用约束

- 阶段命名固定为 `Parse` / `Chunk` / `Embedding`，禁止改用 `解析/分块/向量化` 作为代码枚举值
- 中文文案展示阶段时可用「解析 / 分块 / 向量化」