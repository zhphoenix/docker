# AI 行为规范（行为宪法）

本文件定义 AI 助手在 AI-Platform 项目中的工作原则与不可逾越的边界。
详细可执行规则见 `specs/` 目录；设计原理解释见 `AI-Platform-System-Design/`。

## 核心原则

1. **先读后写**：修改任何模块前，先阅读对应的 specs/ 约束和设计文档
2. **分层不可破坏**：严格遵守 API → Agents → Graph → Nodes → Tools 单向依赖
3. **Prompt 外置**：所有 Prompt 存放于 `langgraph/agent/prompts/`，禁止硬编码在代码中
4. **最小变更**：只改必要的，不做未被要求的重构
5. **设计文档同步**：代码变更涉及架构/接口时，同步更新 AI-Platform-System-Design/ 对应文档

## 禁止事项

- 禁止在 Node 中直接访问基础设施（必须通过 Tool）
- 禁止在 Tool 中包含业务逻辑
- 禁止反向依赖（Tool 不可 import Node，Node 不可 import API）
- 禁止读取或输出 .env 文件内容
- 禁止使用 nohup/后台运行测试命令，必须前台执行
- 禁止提交 .env、模型文件、data/ 目录到 Git

## 规范消费路径

| 需求 | 去哪里找 |
|------|----------|
| 分层红线、依赖方向 | `specs/architecture.yaml` |
| 编码风格、命名约定 | `AI-Platform-System-Design/21_Coding_Guidelines.md` |
| Agent 角色定义 | `langgraph/agent/prompts/{agent}/system.md` |
| 运行时策略 | `langgraph/agent/config/policies.yaml` |
| 设计原理与上下文 | `AI-Platform-System-Design/` 编号文档 |

## 文档体系关系

```
AI-Platform-System-Design/  →  解释源（为什么这样设计）
specs/                      →  约束源（必须/禁止做什么，机器可执行）
prompts/                    →  角色源（Agent 身份与能力边界）
policies.yaml               →  运行源（运行时参数与路由策略）
```

设计文档变更时检查 specs/ 是否需同步；specs/ 是设计文档的"编译产物"，不独立创作。
