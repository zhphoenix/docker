# AI Platform UI 构建计划

## 技术栈确认

| 层面 | 选型 |
|------|------|
| 框架 | React 19 + TypeScript |
| 构建 | Vite 6 |
| 样式 | TailwindCSS 4 |
| 组件库 | shadcn/ui |
| 动画 | Framer Motion |
| 图标 | Lucide React |
| 路由 | React Router 7 |
| 状态管理 | Zustand |
| 数据请求 | TanStack Query (React Query) |
| 项目位置 | `/mnt/e/ai-platform/frontend/` |

---

## Phase 1: 项目脚手架

### 1.1 初始化 Vite 项目
- 在 `/mnt/e/ai-platform/frontend/` 创建 Vite + React + TypeScript 项目
- 安装核心依赖：
  ```
  tailwindcss @tailwindcss/vite framer-motion lucide-react
  react-router-dom zustand @tanstack/react-query
  ```
- 初始化 shadcn/ui（选择 New York 风格，使用 CSS 变量）

### 1.2 建立目录结构
按 UI 规范第二十章要求：
```
frontend/src/
├── app/              # 路由与页面入口
├── components/
│   ├── common/       # 通用组件（shadcn/ui 扩展）
│   ├── layout/       # AppShell, Sidebar, Header, StatusBar
│   ├── dashboard/
│   ├── chat/
│   └── settings/
├── hooks/
├── services/         # API Client
├── stores/           # Zustand stores
├── theme/            # Theme Provider + Design Tokens
├── styles/           # 全局样式
├── types/
├── utils/
└── assets/
```

### 1.3 配置文件
- `vite.config.ts` — 配置 TailwindCSS 插件、路径别名 `@/`、代理 `/v1/*` 到 FastAPI `:8100`
- `tsconfig.json` — 严格模式
- `.env` — `VITE_API_BASE_URL=http://localhost:8100`

---

## Phase 2: Design System 基础

### 2.1 Design Tokens（UI 规范第六、七章）
在 `src/styles/tokens.css` 定义 CSS 变量：

| Token 类别 | 关键值 |
|-----------|--------|
| Color | `--color-primary: #0A84FF`, `--color-text: #111827`, `--color-bg: #F8F8F8`, `--color-danger: #FF453A`, `--color-success: #30D158`, `--color-warning: #FFD60A` |
| Radius | `--radius-base: 16px`, `--radius-dialog: 18px`, `--radius-button: 14px` |
| Shadow | `--shadow-soft: 0 4px 12px rgba(0,0,0,.08)` |
| Spacing | 4/8/12/16/24/32/48/64 |
| Glass | `--glass-bg: rgba(255,255,255,.60)`, `--glass-blur: 30px` |

### 2.2 主题系统（UI 规范第十五章）
- `src/theme/ThemeProvider.tsx` — 支持 Light / Dark / Auto(System)
- 使用 `class` 策略切换 `dark` 类
- Dark 模式 token 定义

### 2.3 TailwindCSS 配置
- 将 Design Tokens 映射到 Tailwind 的 `theme.extend`
- 确保所有组件通过 token 引用样式，禁止硬编码

---

## Phase 3: 全局 Layout（UI 规范第四、五章）

### 3.1 AppShell 组件
```
┌──────────────────────────────────────────────────────┐
│ ● ● ●                 AI Platform          [search]  │
├─────────────┬────────────────────────────────────────┤
│             │                                        │
│ Sidebar     │             Main Content               │
│ (可折叠)     │           (Outlet/Router)              │
│             │                                        │
├─────────────┴────────────────────────────────────────┤
│ Status Bar                                           │
└──────────────────────────────────────────────────────┘
```

### 3.2 Sidebar 组件
- 毛玻璃效果：`backdrop-filter: blur(30px)` + `background: rgba(255,255,255,.72)`
- 导航项：Dashboard / Chat / Agents / Knowledge / Documents / Workflow / Research / Models / Vector DB / Settings
- 功能要求：Hover 动画、当前页面高亮、支持折叠/展开
- 使用 Lucide Icons（Outline 风格）

### 3.3 Header 组件
- macOS 风格红绿灯按钮（装饰性）
- 页面标题
- Command+K 搜索入口（预留 Command Palette）

### 3.4 StatusBar 组件
- 显示后端服务连接状态
- 显示当前模型信息

### 3.5 路由配置
使用 React Router，所有页面懒加载（`React.lazy`）：
- `/` → Dashboard
- `/chat` → Chat
- `/agents` → Agent Center（占位）
- `/knowledge` → Knowledge（占位）
- `/documents` → Documents（占位）
- `/workflow` → Workflow（占位）
- `/research` → Research（占位）
- `/models` → Models（占位）
- `/vector-db` → Vector DB（占位）
- `/settings` → Settings

---

## Phase 4: 核心页面（首批 3 个）

### 4.1 Dashboard 页面
- 概览卡片：文档数量、Agent 数量、知识库状态、系统健康
- 最近活动列表
- 快捷操作入口
- 使用 Card 组件 + Grid 布局

### 4.2 Chat 页面
- 对话列表侧栏
- 消息区域（支持 Markdown 渲染、代码高亮）
- 流式输出支持（SSE 对接 FastAPI `/v1/chat/completions`）
- 输入框 + 发送按钮
- Agent 思考/工具调用状态展示（UI 规范第十三章）

### 4.3 Settings 页面
- 主题切换（Light / Dark / Auto）
- API 端点配置
- 基础偏好设置

---

## Phase 5: API 服务层

### 5.1 API Client
- `src/services/api-client.ts` — 封装 fetch，统一错误处理
- `src/services/chat.ts` — Chat API（SSE 流式）
- `src/services/health.ts` — 健康检查
- `src/services/models.ts` — 模型列表

### 5.2 React Query 配置
- `src/services/query-client.ts`
- 全局 QueryClient Provider

### 5.3 Zustand Store
- `src/stores/app-store.ts` — 全局应用状态（sidebar 折叠、主题、当前页面）
- `src/stores/chat-store.ts` — 聊天状态

---

## Phase 6: 动画与交互（UI 规范第十一、十二章）

- 页面切换：Fade + Slide（Framer Motion）
- Sidebar 折叠：Spring 动画
- 按钮点击：Scale 0.98
- 加载状态：Skeleton
- Hover Lift 效果
- 统一动画时间：150~300ms

---

## Phase 7: Docker 集成

### 7.1 Dockerfile
- 多阶段构建：Node 构建 → Nginx 部署
- 产物放入 `/usr/share/nginx/html`

### 7.2 Nginx 配置
- SPA 路由 fallback（`try_files $uri /index.html`）
- 反向代理 `/v1/*` → `langgraph:8100`

### 7.3 Docker Compose
- 在根 `compose.yml` 的 `include` 中添加 `frontend/compose.yml`
- 前端映射端口 `:3001`（避免与 OpenWebUI `:3000` 冲突）

---

## 执行顺序

1. Phase 1 → 2. Phase 2 → 3. Phase 3 → 4. Phase 5（API 层可与 Phase 3 并行）→ 5. Phase 4 → 6. Phase 6 → 7. Phase 7

## 验收标准

- `npm run dev` 启动后可看到完整 Layout（Sidebar + Header + Main Content）
- 侧边栏导航可切换页面，当前页面高亮
- 主题切换（Light/Dark）正常工作
- Dashboard 页面展示概览卡片
- Chat 页面可发送消息并接收流式响应
- `docker compose up` 可通过浏览器访问前端
