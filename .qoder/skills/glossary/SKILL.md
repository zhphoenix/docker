---
name: glossary
description: >
  Enforces the project's canonical terminology across the entire platform
  (Documents / Workflow / Knowledge Hub). Use whenever introducing or modifying
  code, UI text, API enums, database values, pipeline stage descriptions, or
  documentation that involves business terms, document status, task status,
  page naming, or operation verbs. Detects naming conflicts and recommends the
  canonical term defined in docs/design/术语统一规范.md (the single source of
  truth). Apply proactively when working on pages, pipeline stages, status
  enums, or any Chinese/English label in the codebase. Also analyzes code
  structure via Tree-sitter + LLM (see code-analysis) to extract terminology
  usage facts and support consistency checks.
---

# 全平台术语规范

## Purpose（目的）

确保整个平台（Documents / Workflow / Knowledge Hub）在代码、API、数据库、UI
文案、文档中使用**同一套术语**，杜绝同名异义与前后端不一致。

## Canonical Reference（唯一事实来源）

- `docs/design/术语统一规范.md` —— 全平台术语唯一事实来源，禁止凭空发明术语
- 本技能将规范按类拆分为多份分类文档，使用前先定位对应分类

## 分类索引（按类检索）

| 类别 | 文件 | 覆盖内容 |
| --- | --- | --- |
| 页面/模块命名 | [naming/pages.md](naming/pages.md) | Documents / Workflow / Knowledge Hub 三大页面命名 |
| Pipeline 阶段 | [pipeline/stages.md](pipeline/stages.md) | Parse → Chunk → Embedding 三阶段，Entity/Graph 归属 |
| 状态枚举 | [status/enums.md](status/enums.md) | 文档状态 6 态 + 任务状态 4 态 |
| 操作动词 | [actions/verbs.md](actions/verbs.md) | Open / Reprocess / Delete / Re-embed / Graph / Chunks |
| 旧值映射 | [mappings/legacy.md](mappings/legacy.md) | 前端误用值 → 后端真实枚举 |
| 中文文案 | [copywriting/chinese.md](copywriting/chinese.md) | 标题中文、枚举英文小写 |
| 知识平台架构 | [architecture/terms.md](architecture/terms.md) | Knowledge Object/Graph、Agent 与 Service 命名、存储组件标注、禁止新名称 |
| 代码分析 | [code-analysis](code-analysis/README.md) | Tree-sitter + LLM 提取代码中的术语使用事实，结构与语义两级分析，支撑一致性检查 |

## Workflow（工作流）

处理任何涉及术语的改动时，按此执行：

1. **识别新术语**：新增或修改页面、状态、动词、字段名时，识别涉及的术语。
2. **代码分析采集（可选）**：当需从代码库定位术语的既有用法、分布或违规点时，启用
   [code-analysis](code-analysis/README.md) 分类，用 Tree-sitter 提取结构事实 + LLM 做语义判定，
   产出结构化术语事实清单（文件 + 行号 + 值 + 架构层）。
3. **定位分类**：按上表确定所属类别，读取对应分类文档。
4. **复用规范值**：若分类文档中已有规范值，直接复用，禁止自创同义词。
5. **冲突处理**：若发现与规范不一致的命名，改用规范值（不静默重命名已有产物）。
6. **新概念**：若确实无规范值，建议补充到 `docs/design/术语统一规范.md`，**不自动修改**。

## Expected Output（预期输出）

- 一致：继续实现，不打断。
- 冲突：说明不一致点，推荐规范术语，说明理由。
- 新概念：说明未收录，建议经用户确认后补充。

## Constraints（约束）

本技能**绝不**：

- 未经查证规范文档就发明术语
- 为已有概念创建同义词
- 自动修改规范文档或静默重命名
- 忽视项目已记录的术语
- 用 LLM 猜测结构层事实（须由 Tree-sitter 确定性提取）或全文注入源码

## Success Criteria（成功标准）

- 代码、UI、API、数据库、文档术语完全一致
- 术语有唯一事实来源
- 命名歧义最小化