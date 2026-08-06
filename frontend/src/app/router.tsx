import { createBrowserRouter, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppShell } from '@/components/layout/AppShell'

const DashboardPage = lazy(() => import('@/app/pages/DashboardPage'))
const ChatPage = lazy(() => import('@/app/pages/ChatPage'))
const SettingsPage = lazy(() => import('@/app/pages/SettingsPage'))
const MonitorPage = lazy(() => import('@/app/pages/MonitorPage'))
const AgentsPage = lazy(() => import('@/app/pages/AgentsPage'))
const AgentDetailPage = lazy(() => import('@/app/pages/AgentDetailPage'))
const KnowledgePage = lazy(() => import('@/app/pages/KnowledgePage'))
const KnowledgeReviewPage = lazy(() => import('@/app/pages/KnowledgeReviewPage'))
const DocumentsPage = lazy(() => import('@/app/pages/DocumentsPage'))
const WorkflowPage = lazy(() => import('@/app/pages/WorkflowPage'))
const ResearchPage = lazy(() => import('@/app/pages/ResearchPage'))
const NewsPage = lazy(() => import('@/app/pages/NewsPage'))
const WatchlistPage = lazy(() => import('@/app/pages/WatchlistPage'))
const ModelsPage = lazy(() => import('@/app/pages/ModelsPage'))
const VectorDbPage = lazy(() => import('@/app/pages/VectorDbPage'))

function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      {
        path: '/',
        element: (
          <SuspenseWrapper>
            <DashboardPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/chat',
        element: (
          <SuspenseWrapper>
            <ChatPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/agents',
        element: (
          <SuspenseWrapper>
            <AgentsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/agents/:id',
        element: (
          <SuspenseWrapper>
            <AgentDetailPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/knowledge',
        element: (
          <SuspenseWrapper>
            <KnowledgePage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/knowledge/review',
        element: (
          <SuspenseWrapper>
            <KnowledgeReviewPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/documents',
        element: (
          <SuspenseWrapper>
            <DocumentsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/workflow',
        element: (
          <SuspenseWrapper>
            <WorkflowPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/research',
        element: (
          <SuspenseWrapper>
            <ResearchPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/news',
        element: (
          <SuspenseWrapper>
            <NewsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/watchlist',
        element: (
          <SuspenseWrapper>
            <WatchlistPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/models',
        element: (
          <SuspenseWrapper>
            <ModelsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/vector-db',
        element: (
          <SuspenseWrapper>
            <VectorDbPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/monitor',
        element: (
          <SuspenseWrapper>
            <MonitorPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: '/settings',
        element: (
          <SuspenseWrapper>
            <SettingsPage />
          </SuspenseWrapper>
        ),
      },
      {
        // 兜底路由：未知路径重定向到首页，避免 React Router 默认 404 报错页
        path: '*',
        element: <Navigate to="/" replace />,
      },
    ],
  },
])
