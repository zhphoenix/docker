# 代码结构与语义分析规范

> 本分类是 glossary 技能**扩展能力**：从代码库中结构化、语义化地提取"术语使用事实"，
> 支撑术语一致性检查。基于 **Tree-sitter（语法精确）+ LLM（语义深刻）** 两级分析管线。

## 目的

glossary 的核心是"校验代码/UI/API/数据库中的术语是否与规范一致"。本分类提供**采集能力**，
把散落在代码中的命名、枚举、动词、状态、页面名等事实，用结构化方式提取出来，交给术语规范对照。

## 两层分析深度

### 结构层（Structure Layer）—— 语法精确、可复现

通过 Tree-sitter 解析 AST，**确定性**提取以下事实（同输入 → 同输出）：

| 维度 | 提取内容 | 说明 |
| --- | --- | --- |
| 函数 / 方法 | 签名、参数、返回值、调用关系、职责（单行） | 定位 API 路由、Service 方法、工具函数中的命名 |
| 类 / 模块 | 继承、组合、依赖关系 | 识别 Entity / Service / Agent 等类命名 |
| 依赖拓扑 | import graph（跨模块 import 关系） | 追踪术语从定义处到使用处的传播路径 |
| 架构层级 | API → Service → Storage 分层 | 将术语归位到正确架构层，校验层级命名 |

### 语义层（Semantic Layer）—— 语义深刻、可解释

将 Tree-sitter 提取的结构化摘要 + 关键源码片段交给 LLM，完成：

- **业务意图识别**：某字段 / 函数背后的业务含义
- **设计模式识别**：如 Repository、Strategy、Factory 等模式
- **潜在术语违规**：命名与架构层不符、同义词混用、大小写不一致
- **跨模块一致性**：同一概念在不同模块是否使用同一名称

## 分析管线（Tree-sitter + LLM）

```
源码 → [Tree-sitter 解析 AST] → 结构化摘要(JSON)
                                   ↓
                          [LLM 语义分析] → 术语事实清单
                                   ↓
                     [对照术语规范分类文档] → 一致性结论
```

### 管线原则
- **语法精确**：Tree-sitter 负责确定性提取（函数签名 / 类 / import），不靠 LLM 猜测。
- **语义深刻**：LLM 只做 Tree-sitter 做不到的事（意图、模式、判定）。
- **摘要优先**：只把结构化摘要传给 LLM，绝不整文件注入，防止上下文溢出。
- **可复现**：结构层结果严格可复现；语义层结果用于解释，不推翻结构层事实。

## 触发条件

以下场景自动启用本分类：

1. 检查**代码中的命名 / 枚举 / 状态 / 动词**是否与规范一致时（引入新代码、重构、审查）。
2. 新增或修改**页面、状态、API 字段、数据库列**时，需从代码定位既有用法。
3. 需要回答"这个词在代码里怎么用的 / 用在哪"这类问题。
4. 术语规范冲突排查时，需定位违规点所在文件与行号。

## 输入 / 输出格式

### 输入
- 目标代码路径（文件或目录）+ 预估规模
- 待核对术语（可选，默认全量扫描）

### 输出（结构化）
```json
{
  "extracted": [
    {
      "file": "frontend/src/pages/KnowledgeHub.tsx",
      "line": 42,
      "layer": "UI",
      "kind": "enum",
      "value": "processing",
      "context": "documentStatus"
    }
  ],
  "analysis": [
    {
      "term": "processing",
      "canonical": "processing",
      "status": "consistent",
      "note": "与 status/enums.md 一致"
    }
  ]
}
```

### 产出物
- 一致性结论：`一致 / 冲突 / 新概念`
- 冲突时给出：文件 + 行号 + 违规值 + 推荐规范值 + 理由

### 落盘位置
- 结构化术语事实清单写入 `scripts/collect_out/glossary_term_facts.json`。
- `scripts/collect_out/` 是**统一技能分析输出目录**：与 project-inventory 的采集产物同处，
  两者产物集中管理、便于复用。
- 一致性结论（一致 / 冲突 / 新概念）作为对话输出，不落盘。

## 与其他分类文档的协作

| 分析产出 | 协作分类 | 作用 |
| --- | --- | --- |
| 页面 / 模块命名 | [naming/pages.md](../naming/pages.md) | 校验页面名是否偏离规范 |
| 状态枚举 | [status/enums.md](../status/enums.md) | 校验代码中的状态值 |
| 操作动词 | [actions/verbs.md](../actions/verbs.md) | 校验按钮 / 接口动词 |
| 架构层归属 | [architecture/terms.md](../architecture/terms.md) | 校验 Agent / Service / 存储命名与分层 |
| 中文文案 | [copywriting/chinese.md](../copywriting/chinese.md) | 校验 UI 文案 |
| 旧值映射 | [mappings/legacy.md](../mappings/legacy.md) | 识别前端误用值 → 后端真实枚举 |

## 约束

本分类**绝不**：

- 用 LLM 猜测结构层事实（必须由 Tree-sitter 提取）
- 全文注入源码（只传结构化摘要）
- 修改代码或规范文档（只做采集与判定）
- 未经规范分类对照就下"冲突"结论