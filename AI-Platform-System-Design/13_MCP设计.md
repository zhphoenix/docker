# MCP 设计

## 一、定位

MCP（Model Context Protocol）统一工具接口，便于扩展外部工具。

---

## 二、MCP 在系统中的角色

```text
LangGraph Agent
    │
    │ MCP 协议
    ▼
MCP Server
    │
    ├── Obsidian Vault（知识读写）
    ├── GitHub（代码管理，预留）
    ├── Filesystem（文件系统，预留）
    └── 其他工具（预留）
```

---

## 三、Obsidian MCP 集成

### 3.1 已配置工具

| 工具 | 功能 |
|------|------|
| `obsidian_get_note` | 读取笔记内容 |
| `obsidian_write_note` | 写入/创建笔记 |
| `obsidian_append_to_note` | 追加内容到笔记 |
| `obsidian_patch_note` | 部分修改笔记 |
| `obsidian_replace_in_note` | 替换笔记内容 |
| `obsidian_delete_note` | 删除笔记 |
| `obsidian_search_notes` | 搜索笔记 |
| `obsidian_list_notes` | 列出所有笔记 |
| `obsidian_list_tags` | 列出所有标签 |
| `obsidian_manage_tags` | 管理标签 |
| `obsidian_manage_frontmatter` | 管理 YAML frontmatter |
| `obsidian_open_in_ui` | 在 Obsidian 中打开 |

### 3.2 使用场景

- Agent 完成研究后，自动写入研究报告到 Obsidian Vault
- Agent 读取投资人笔记作为推理上下文
- 管理标签和元数据
- 搜索历史研究结论
- 多 Agent 通过 Vault 异步协作（Research → Investment → Knowledge）

### 3.3 Vault 路径

`/mnt/e/Knowledge/Vault/`（Windows 侧 `E:\Knowledge\Vault\`）

### 3.4 注意事项

- MCP 服务依赖 Obsidian 桌面端运行
- Vault 路径必须匹配
- Agent 容器通过 `host.docker.internal` 访问 Windows 侧服务

### 3.5 Vault 作为多 Agent 共享空间

```
     ┌──────────────────────────────┐
     │      Obsidian Vault          │
     │   (Agent 异步协作媒介)    │
     └─────────────┬────────────┘
                   │ MCP
     ┌──────────┬──────────┬──────────┐
     ▼          ▼          ▼          ▼
 Research   Investment  Knowledge   投资人
  Agent      Agent      Agent       (编辑/标注)
```

### 3.6 多 Agent 读写权限矩阵

| Agent | 00_Inbox | 01_Daily | 03_Reports | 03_Companies | 03_Research | 全 Vault |
|-------|----------|----------|------------|--------------|-------------|--------|
| Research Agent | 写 | - | 写 | 读 | 读 | 读 |
| Investment Agent | 写 | - | 读 | 读写 | 读 | 读 |
| Knowledge Agent | 读写 | 读 | 读写 | 读写 | 读写 | 读写（索引维护） |
| 投资人 | 读写 | 读写 | 读写 | 读写 | 读写 | 读写 |

---

## 四、扩展规划

| MCP Server | 用途 | 状态 |
|-----------|------|------|
| Obsidian | 知识管理 | 已配置 |
| GitHub | 代码管理 | 预留 |
| Filesystem | 本地文件 | 预留 |
| Database | 数据库查询 | 预留（当前直接用 Tool） |

---

## 五、设计原则

| 原则 | 说明 |
|------|------|
| 统一接口 | 所有外部工具通过 MCP 协议访问 |
| 可扩展 | 新增工具只需新增 MCP Server |
| 与 Tool 层互补 | 基础设施（Qdrant/PostgreSQL/MinIO）直接用 Tool，知识管理用 MCP |