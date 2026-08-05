# 建立 Project_Inventory 技能

## 目标
创建 `Project_Inventory` skill，使 Agent 能依据 `docs/bu_skill.md` 的三大原则（代码是真实来源 / 禁止推测 / 只描述当前实现），扫描项目真实实现并生成/维护 `docs/00_Project_Inventory.md`（15 章节唯一事实索引）。

本次交付物：仅技能文件，不执行盘点、不修改 `docs/00_Project_Inventory.md` 内容、不修改任何代码。

## 交付物
- 新建技能目录：`.qoder/skills/project-inventory/`
- 新建技能入口：`.qoder/skills/project-inventory/SKILL.md`（带 frontmatter，格式对齐 glossary / open-code-review）

## SKILL.md 内容结构

### frontmatter
- `name: project-inventory`
- `description`: 说明适用范围与触发时机（盘点项目真实实现、生成/维护 `docs/00_Project_Inventory.md`、为架构/API/UI 设计提供事实索引）

### 1. Purpose（角色与目的）
- 扮演资深软件架构师，盘点当前项目真实实现，建立唯一事实索引
- 文档必须客观、可验证、不推测、不包含未来规划、与代码一致

### 2. 三大工作原则（严格贯彻 bu_skill.md）
- 源码是真实来源：分析顺序 代码 → 目录结构 → Docker Compose → 配置文件 → 数据库 → API → 历史设计文档（仅参考）；设计文档与代码不一致时以代码为准
- 禁止推测：不存在的模块（Knowledge Graph / Agent / Workflow / API / Docker Service）统一标记 `Not Implemented` 或 `Unknown`
- 只描述当前实现：规划中的内容不得写成已完成状态

### 3. 数据采集步骤（覆盖真实实现）
定义由 Agent 执行的采集清单，逐项定位真实实现：
1. 仓库结构：`os.walk` 扫描根目录，记录各目录职责，空目录注明
2. 前端：扫描 `frontend/src/`（app 路由/pages、components、hooks、services、stores、lib、types），统计页面/组件/路由/API 调用
3. 后端：扫描 `langgraph/`（api 路由、agents、services、tools、graphs、nodes、pipelines、collectors、storage、schemas、providers、skills）
4. 数据库：解析 `postgres/init/*.sql` 表/视图/函数/扩展；确认是否存在 Knowledge Graph（Apache AGE）
5. 对象存储：解析 `minio/`（bucket 初始化脚本、`init-buckets.sh`）
6. 向量库：解析 `qdrant/init_qdrant.py` 与 `scripts/batch_embed_to_qdrant.py`（collection、vector size、distance、payload）
7. AI 服务：解析 `embedding/`、`reranker/`、`docling/`、`paddleocr/`、`sisyphus/` 的 compose 与配置
8. Docker 服务：解析根 `compose.yml` 及各子目录 compose（image、port、health、dependency）
9. API：读取 `langgraph/api/` 的 FastAPI 路由注册，收集 Method/Path/Description/Status
10. Agent/技能：扫描 `langgraph/agents/`、`langgraph/skills/`、`.qoder/skills/`、`mcp-knowledge/`、`mcp-news/`

### 4. 自动采集脚本设计（选项B 的实现方案）
明确：技能执行时，Agent 应生成一次性的 `scripts/collect_inventory.py`（临时脚本，采集后由用户决定是否保留），其职责：
- 目录/文件扫描：`os.walk` 汇总 `frontend/src`、`langgraph`、各服务目录结构
- 解析 Docker Compose：用 `yaml.safe_load` 读取根 `compose.yml` 及各子目录 compose，提取服务名、image、ports、depends_on
- 解析 FastAPI 路由：扫描 `langgraph/api` 下 router 定义，正则提取 `@router.get/post/...` 路径与函数名
- 解析数据库表：读取 `postgres/init/*.sql`，正则提取 `CREATE TABLE/VIEW/FUNCTION` 与扩展
- 解析 Qdrant 集合：读取 `qdrant/init_qdrant.py` 与 batch 脚本中的 collection 名称/向量维度/距离度量
- 前置检查：脚本运行前先确认 `docker compose ps` 与 `.env` 是否存在（技能不读取 `.env` 内容）
- 输出：采集结果以 JSON/结构化 markdown 落盘供 Agent 归纳，Agent 依据脚本采集结果填写 15 章节

### 5. 输出文档结构（15 章节模板）
定义 `docs/00_Project_Inventory.md` 的章节，每章给出表格/字段模板：
1. Project Overview（名称/定位/版本/技术栈/当前状态）
2. Repository Structure（目录职责表）
3. Frontend Inventory（Module/Status/Description）
4. Backend Inventory（Router/Service/Repository/Models/Schemas）
5. Database Inventory（Schema/Table/View/Function/Extension）
6. Object Storage Inventory（Bucket/用途/状态）
7. Vector Database Inventory（Collection/Vector Size/Distance/Payload）
8. AI Services Inventory（Embedding/Reranker/LLM/Docling/OCR 状态）
9. Docker Services Inventory（Image/Port/Health/Dependency）
10. API Inventory（Method/Path/Description/Status）
11. Agent Inventory（LangGraph/MCP/Workflow/Scheduler，无则标记）
12. Knowledge Inventory（Documents/Chunks/Embedding/Graph/Entity/Relation）
13. Current Module Status（模块矩阵 Module/Status/Progress/Notes）
14. Current Technical Debt（只记录事实，不给方案）
15. Architecture Baseline（前端/后端/数据/AI/部署架构，一律依据代码）

### 6. 状态分类与进度估算规范
- 状态枚举：`Implemented` / `Partial` / `Planned` / `Unknown`（不存在 → `Not Implemented`）
- 进度估算：Progress 必须依据真实实现（如：模块已实现页面+后端+API 计 80%，仅页面存在计 20%，未开始计 0%），禁止凭空赋值

### 7. 更新/维护 Workflow（运行方式）
定义一个可重复执行的流程：用户触发（如 "/project-inventory" 或描述"盘点项目"）→ Agent 按采集步骤（含生成采集脚本）扫描 → 对照现有 `docs/00_Project_Inventory.md` 差异 → 更新 15 章节 → 输出变更摘要。技能遵循：不静默修改、改动以代码为准。

### 8. Constraints（约束）
- 不推测、不发明不存在模块、不将规划写成已完成
- 不修改代码、不提出架构优化建议、不设计未来功能
- 不读取 `.env` 内容
- 不静默重命名已有产物；新模块标记 `Unknown`/`Not Implemented`

### 9. Success Criteria（成功标准）
- Inventory 中每项均可通过代码验证
- 状态区分准确（Implemented/Partial/Planned/Unknown）
- 与代码一致、可作后续架构/API/UI/Agent 设计的唯一事实来源

## 验证
- 检查 SKILL.md 能否被技能系统识别（frontmatter 合法、name 唯一）
- 目录结构正确（`.qoder/skills/project-inventory/SKILL.md`）
- 不触碰 `docs/00_Project_Inventory.md` 与其他代码

## 假设
- 技能存放位置采用 `.qoder/skills/project-inventory/`（与 glossary 同级）
- 采集脚本由技能执行时生成，不预置为常驻文件
- 本次仅建技能，不执行盘点