import { createBrowserRouter } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { PlaceholderPage } from '@/components/common/PlaceholderPage'

const DashboardPage = lazy(() => import('@/app/pages/DashboardPage'))
const ChatPage = lazy(() => import('@/app/pages/ChatPage'))
const SettingsPage = lazy(() => import('@/app/pages/SettingsPage'))
const MonitorPage = lazy(() => import('@/app/pages/MonitorPage'))

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
        element: <PlaceholderPage title="Agent Center" description="管理和监控 AI Agent" />,
      },
      {
        path: '/knowledge',
        element: <PlaceholderPage title="Knowledge Base" description="知识库管理与检索" />,
      },
      {
        path: '/documents',
        element: <PlaceholderPage title="Documents" description="文档管理与解析" />,
      },
      {
        path: '/workflow',
        element: <PlaceholderPage title="Workflow" description="工作流编排与执行" />,
      },
      {
        path: '/research',
        element: <PlaceholderPage title="Research Center" description="投研分析中心" />,
      },
      {
        path: '/models',
        element: <PlaceholderPage title="Models" description="模型管理与部署" />,
      },
      {
        path: '/vector-db',
        element: <PlaceholderPage title="Vector Database" description="向量数据库管理" />,
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
    ],
  },
])
