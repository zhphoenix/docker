# Document 页面重构：围绕文档处理流水线的生命周期管理页

## 一、现状分析

### 1.1 当前结构（DocumentsPage.tsx，1840 行，单文件）
主页面 `frontend/src/app/pages/DocumentsPage.tsx` 将所有功能平铺：
- **Header + 刷新**（1578-1589）
- **知识库规模统计**（1592-1625）：Documents/Chunks/Entities/Facts 四卡
- **ImportPanel**（1627-1628）：内嵌 3 个 WindowedDialog（上传 PDF / Import MinIO / Sync Folder）+ Batch Process 触发
- **状态统计**（1631-1646）：按 `STATUS_ORDER` 六个状态卡片
- **RunningTasksPanel**（1648-1649）
- **筛选区**（1651-1691）：symbol 搜索 + status/market Select
- **文档表格 + 分页**（1693-1823）
- **FailedTasksPanel**（1825-1826）
- **DocumentDetailDialog**（1828-1829）

### 1.2 已有组件（可直接复用）
| 组件 | 位置（行） | 数据来源 | 复用方式 |
|------|-----------|---------|---------|
| `ImportPanel` | 154-1121 | uploadDocumentPdf / triggerIngestMinio / uploadFolderPdf / triggerPipeline / triggerBatchEmbed | **整体复用**，仅调整摆放位置与对外暴露 Batch 入口 |
| `RunningTasksPanel` | 1124-1173 | `fetchTasks({status:'running',limit:10})` + refetchInterval 5000 | **复用**，移入 Processing 区 |
| `FailedTasksPanel` | 1176-1227 | `fetchTasks({status:'failed',limit:5})` + retryTask | **复用**，移入 Processing 区 |
| `DocumentDetailDialog` | 1230-1492 | fetchDocumentDetail / fetchDocumentChunks / fetchDocumentEntities | **复用 + 增强**（Overview tab 增加生命周期链示意） |

### 1.3 数据来源（services 层）
- `services/documents.ts`：`DocumentStatus`（pending/waiting_parser/parse_failed/parsed/indexed/error）、`DocumentInfo`、`fetchDocuments / fetchDocumentStats / fetchDocumentDetail / fetchDocumentChunks / fetchDocumentEntities / deleteDocument`、上传/文件夹接口
- `services/tasks.ts`：`TaskStatus`（pending/running/done/failed）、`TaskInfo`（含 `stage/progress/current_name/error_message`）、`fetchTasks / fetchTaskDetail / retryTask / fetchTaskStats / fetchWorkers / triggerPipeline / triggerBatchEmbed / reembedDocument / fetchPipelineStatus`
- `services/knowledge.ts`：`fetchKnowledgeStats`（documents/chunks/entities/facts/quality）、`fetchKnowledgeCollections`

### 1.4 复用 / 重构 / 新增结论
- **直接复用**：`ImportPanel`（3 个导入对话框）、`RunningTasksPanel`、`FailedTasksPanel`、`DocumentDetailDialog`（骨架）
- **需重构**：`DocumentsPage.tsx` 主页面（拆分为区域化组合）、上方统计卡（拆 Storage/Knowledge 两组）、状态统计（改为流水线状态组）
- **需新增**：`PipelineFlow`（①流程介绍）、`ProcessingCenter`（③处理状态 + 控制）、`PipelineProgress`（列表字段）、`StatisticsGrid` 拆分、`DocumentDetail` 生命周期链增强

---

## 二、目标架构对齐（四大区域 ↔ 现有代码映射）

```
① Pipeline（流程介绍）    → 新增 <PipelineFlow />（纯展示，无数据源）
② Import（导入入口）      → 复用 <ImportPanel />（仅保留 3 个导入对话框，Batch 移走）
③ Processing（处理状态）  → 新增 <ProcessingCenter /> = 状态流水线 + Pipeline Control + RunningTasksPanel + FailedTasksPanel
④ Documents（处理结果）   → 复用文档表格 + 筛选 + 分页，新增 <PipelineProgress /> 字段；DocumentDetail 增强生命周期链
```

### 布局（对应设计文档 §12）
```
Header（系统状态：Pipeline Running / Queue / Workers / Parser / Embedding ← fetchWorkers + fetchPipelineStatus）
├─ ① PipelineFlow（Upload→Parse→Chunk→Entity→Embedding→Graph→Ready 横向步骤条）
├─ ② Import 区（3 入口卡片）+ Pipeline Control（Start/Resume Failed/Retry/Batch Run）
├─ ③ Processing Queue（状态组：Pending|Parsing|Chunking|Embedding|Graph|Completed|Failed）
│     └─ RunningTasksPanel + FailedTasksPanel
├─ ④ Storage Statistics（Documents/Chunks/Size/Raw）‖ Knowledge Statistics（Entities/Relations/Facts/Events）
└─ ④ Documents List（Code|Company|Year|Type|Pipeline Progress|Chunks|Updated|Actions）
      └─ DocumentDetailDialog（Overview 生命周期链 + Metadata + Chunk/Knowledge 统计）
```

---

## 三、后端接口对齐（避免虚拟状态）

### 3.1 真实数据源（不可虚构）
- **文档状态**（`DocumentStatus`，6 值）：`pending / waiting_parser / parse_failed / parsed / indexed / error`
- **任务状态**（`TaskStatus`，4 值）：`pending / running / done / failed`；`TaskInfo.stage` 记录真实处理阶段字符串

### 3.2 前端「流水线状态」映射（双源派生，不改后端）
| 前端流水线状态 | 派生来源（真实数据） | 说明 |
|---------------|--------------------|------|
| Pending | `status==='pending'` | 待处理 |
| Parsing | `status==='waiting_parser'` 或 running 任务 `stage` 含 parse | 等待/解析中 |
| Chunking | running 任务 `stage` 含 chunk | 由任务 stage 派生，非文档状态 |
| Embedding | running 任务 `stage` 含 embed / embed | 由任务 stage 派生 |
| Extracting Entity | running 任务 `stage` 含 extract / knowledge_extraction 任务 | 由任务 stage 派生 |
| Building Graph | running 任务 `stage` 含 graph | 由任务 stage 派生 |
| Completed | `status==='indexed'` | 已索引=完成 |
| Failed | `status==='parse_failed' \|\| status==='error'` | 失败 |

> **关键规则**：`parsed` 状态本身无法区分 Chunking/Embedding/Graph（文档状态粒度不足），因此**细粒度阶段一律从 `TaskInfo.stage` + `fetchPipelineStatus()` 读取**；前端只做「文档状态→粗粒度」+「任务 stage→细粒度」两层映射，绝不发明后端不存在的新状态值。为满足设计文档的 8 态展示，新增一个**纯前端归一化函数** `normalizePipelineStatus(docStatus, runningTaskStage)`，返回统一展示枚举，但底层仍读真实字段。

### 3.3 组件间数据流
- `ProcessingCenter` 用 `fetchTaskStats()`（pending/running/done/failed）+ `fetchPipelineStatus()`（document_status）+ `fetchTasks({status:'running'})` 的 stage 聚合出 7 态数量
- 列表 `PipelineProgress` 用 `doc.status` + 对应文档的 running 任务 stage（可选，默认以 status 粗粒度展示勾选链）

---

## 四、分阶段实施

### 阶段一：抽取 Pipeline 流程组件（纯展示，风险最低）
- **涉及文件**：新增 `frontend/src/components/documents/PipelineFlow.tsx`
- **改动要点**：横向步骤条（Upload→Parse→Chunk→Entity Extraction→Embedding→Knowledge Graph→Search/Agent），每步带说明 tooltip/副文本；纯静态，无数据依赖
- **完成标准**：页面顶部渲染 PipelineFlow 且无数据请求、控制台无报错

### 阶段二：重构导入区（ImportCenter 包装 + Batch 迁移）
- **涉及文件**：修改 `DocumentsPage.tsx`；新增 `frontend/src/components/documents/ImportCenter.tsx`
- **改动要点**：
  - `ImportCenter` 包装现有 `ImportPanel`，仅保留 Upload Local Files / Import From MinIO / Folder Sync 三个入口（3 个 WindowedDialog 原样复用）
  - 将 `ImportPanel` 内的 Batch Process 触发逻辑（pipelineMutation / batchEmbedMutation）抽到 `ProcessingCenter` 的 Pipeline Control
  - 新增 `PipelineControl`（Start Pipeline→triggerPipeline / Resume Failed→retryTask / Retry / Batch Run→triggerBatchEmbed）
- **完成标准**：三个导入对话框行为不变；Batch 按钮移至 Processing 区且可正常触发

### 阶段三：新增处理中心 / 流水线状态
- **涉及文件**：新增 `frontend/src/components/documents/ProcessingCenter.tsx`；修改 `DocumentsPage.tsx`
- **改动要点**：
  - 聚合 `fetchTaskStats()` + `fetchPipelineStatus()` + `fetchTasks({status:'running'})` 的 stage，按 3.2 映射表归一化为 7 态数量卡片
  - 内嵌复用 `RunningTasksPanel` + `FailedTasksPanel` + `PipelineControl`
  - `normalizePipelineStatus` 归一化函数放 `services/documents.ts` 或独立 `lib/pipeline-status.ts`
- **完成标准**：Processing Queue 七态数量与 RunningTasksPanel/FailedTasksPanel 数据一致；点击状态卡可联动筛选文档列表

### 阶段四：改造文档列表与详情
- **涉及文件**：新增 `frontend/src/components/documents/PipelineProgress.tsx`、`StatisticsGrid.tsx`；修改 `DocumentsPage.tsx`、`DocumentDetailDialog`
- **改动要点**：
  - 列表新增 `Pipeline Progress` 列（Upload✓/Parse✓/Chunk✓/Embedding✓/Graph✓ 勾选链或进度条，由 `doc.status` 派生）
  - 统计拆两组：Storage（Documents/Chunks/Storage Size/Raw Files←`fetchDocumentStats`）‖ Knowledge（Entities/Relations/Facts/Events←`fetchKnowledgeStats`，Relations/Events 后端无则显示 '—' 并用 tooltip 说明）
  - `DocumentDetailDialog` Overview tab 增加生命周期链（Uploaded→Parsed→Chunks→Embedding→Extracted→Stored Qdrant→Stored KG），Metadata/Chunk 统计/Knowledge 统计分组展示
- **完成标准**：列表、统计、详情均按新结构渲染；筛选/分页/删除/重新向量化/详情抽屉行为回归正常

### 阶段五：收尾与回归
- **涉及文件**：全量检查 `frontend/src/app/pages/DocumentsPage.tsx` 及新增组件
- **改动要点**：清理原平铺区域、删除不再使用的内联统计卡、统一文案（对齐术语规范）、确认 Header 系统状态（fetchWorkers/fetchPipelineStatus）
- **完成标准**：`npm run build` 通过、TS 无类型错误、浏览器逐项验证通过

---

## 五、风险与验证

### 5.1 风险点
| 风险 | 影响 | 缓解 |
|------|------|------|
| 移动 ImportPanel/Batch 导致导入对话框状态丢失 | 上传/导入中断 | 组件状态保持 local，仅调整位置；阶段二单独验证 |
| 状态筛选与流水线状态卡不一致 | 用户困惑 | 状态卡点击仍走 `handleFilterChange(setStatus)` 同一路径 |
| 任务轮询（RunningTasksPanel refetchInterval 5000）卡顿 | 页面性能 | 保留原轮询，ProcessingCenter 复用同一 queryKey，避免重复轮询 |
| 前端 8 态展示与后端 6 态不匹配 | 出现虚拟状态 | 严格按 3.2 双源映射，新状态仅前端展示层，不写回 |
| Relations/Events 无后端字段 | 显示 '—' 误导 | 缺失字段显示 '—' + tooltip「后端暂未提供」 |
| 详情抽屉生命周期链与真实进度不符 | 误导用户 | 生命周期链仅做静态示意，动态进度读 `doc.status` + 任务 stage |

### 5.2 每阶段验证
- **阶段一**：类型检查；浏览器进入 /documents 顶部出现 PipelineFlow，无 console 报错
- **阶段二**：依次打开 3 个导入对话框（上传/Import MinIO/Sync Folder）确认可打开关闭；Batch 按钮在 Processing 区可触发任务
- **阶段三**：确认七态数量 = RunningTasksPanel + FailedTasksPanel 数据；点击状态卡筛选生效
- **阶段四**：列表 Pipeline Progress 正确；统计两组正确；打开详情抽屉看生命周期链与 3 个 tab
- **阶段五**：全量回归

### 5.3 回归检查清单
1. `npm run build`（或 `tsc --noEmit`）零错误
2. 导入：Upload PDF / Import MinIO / Folder Sync 三对话框可开可关、上传成功
3. 筛选：symbol 搜索、status Select、market Select、分页均正常
4. 详情抽屉：WindowedDialog 可移动/缩放/最大化/最小化/关闭，Overview/Chunks/Entities 三 tab 可切换
5. 任务轮询：RunningTasksPanel 每 5s 刷新、FailedTasksPanel retry 可用
6. 控制台无红色报错、无未捕获异常
7. 刷新页面后所有 query（documents/stats/knowledge-stats）重新加载正常