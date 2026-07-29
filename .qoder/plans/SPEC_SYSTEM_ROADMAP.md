# 分层规范系统 — 规划状态跟踪

> 本文件为分层规范系统（CLAUDE.md + specs/ + tasks/ + prompts/）的唯一状态入口。
> 最后更新：2026-07-27

---

## 总体状态

| 阶段 | 状态 | 完成日期 |
|------|------|----------|
| P1 核心落地 | ✅ 已完成 | 2026-07-27 |
| P2 扩展 specs/ | ⏸️ 待定（Deferred） | — |
| P3 CI 自动校验 | ⏸️ 待定（Deferred） | — |
| P4 Agent 角色完善 | ⏸️ 待定（Deferred） | — |

---

## P1：核心落地（已完成）

### 交付文件

| 文件 | 用途 | 验证结果 |
|------|------|----------|
| `CLAUDE.md` | AI 行为宪法（42 行） | ✅ 覆盖 5 原则 + 6 禁止 + 消费路径表 |
| `specs/architecture.yaml` | 分层架构约束（18 条规则） | ✅ YAML 合法，覆盖 §2-§5 |
| `langgraph/agent/prompts/investment/system.md` | Investment Agent 角色定义 | ✅ `load_prompt("investment/system")` 正常 |

### 同步更新的设计文档

| 文件 | 变更内容 |
|------|----------|
| `AI-Platform-System-Design/03_项目目录设计.md` | 新增 §二a 项目根目录规范文件；prompts/ 补充 Agent 子目录 |
| `AI-Platform-System-Design/README.md` | 新增「规范体系」导航段；清理末尾重复内容 |

### 关键设计决策

- `specs/` 定位为设计文档的"编译产物"（约束源），不独立创作
- 每条规则含 `source` 字段回溯设计文档章节，避免双源脱节
- `CLAUDE.md` 命名保留（行业事实标准），内容模型无关

---

## P2：扩展 specs/（待定）

**范围：** 从现有设计文档提取更多领域的可执行约束文件

| 计划文件 | 来源文档 | 预计规则数 |
|----------|----------|-----------|
| `specs/coding.yaml` | 21_Coding_Guidelines.md | ~15 条（异步/错误处理/导入顺序） |
| `specs/testing.yaml` | 18_测试规范.md | ~10 条（三层测试准入） |
| `specs/rag.yaml` | 11_RAG设计.md | ~8 条（chunk/embedding/retrieval 参数约束） |
| `specs/docker.yaml` | 04_Docker部署.md | ~6 条（网络/卷/健康检查） |
| `specs/security.yaml` | 新增（无现有源） | ~10 条（密钥/权限/注入防护） |

**启动条件：** 当需要让 AI 助手或 CI 在编码时消费更多领域规则时

---

## P3：CI/pre-commit 自动校验（待定）

**范围：** 让 specs/*.yaml 从"文档"变为"门禁"

- 编写 pre-commit hook 或 CI step，解析 specs/ YAML 并校验代码合规性
- 优先实现 ARCH-003（nodes/ 不得 import 基础设施库）的自动检测
- 可选：集成到 GitHub Actions 或本地 git hook

**启动条件：** 当团队协作规模扩大，或人工审查违规频率上升时

---

## P4：完善 prompts/ 各 Agent 角色定义（待定）

**范围：** 补齐所有注册 Agent 的独立 system prompt + 能力边界声明

| Agent | 当前状态 | 待办 |
|-------|----------|------|
| chat | ✅ 已有 `chat/system.md` | — |
| research | ✅ 已有 `research/system.md` | — |
| investment | ✅ 已有 `investment/system.md` | — |
| knowledge | ⚠️ 复用 `chat/system.md` | 创建 `knowledge/system.md` |

- 考虑在 prompts/ 中增加 `can/cannot` 结构化能力边界声明
- 与 `policies.yaml` 的 routing rules 对齐

**启动条件：** 当 Knowledge Agent 正式启用，或 Agent 数量 > 6 时

---

## 回溯指引

- 规范体系总览 → `CLAUDE.md`「文档体系关系」
- 架构约束详情 → `specs/architecture.yaml`
- 设计原理 → `AI-Platform-System-Design/` 编号文档
- 本文件路径 → `.qoder/plans/SPEC_SYSTEM_ROADMAP.md`
