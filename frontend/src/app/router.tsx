import { createBrowserRouter } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppShell } from '@/components/layout/AppShell'

const DashboardPage = lazy(() => import('@/app/pages/DashboardPage'))
const ChatPage = lazy(() => import('@/app/pages/ChatPage'))
const SettingsPage = lazy(() => import('@/app/pages/SettingsPage'))
const MonitorPage = lazy(() => import('@/app/pages/MonitorPage'))
const AgentsPage = lazy(() => import('@/app/pages/AgentsPage'))
const KnowledgePage = lazy(() => import('@/app/pages/KnowledgePage'))
const DocumentsPage = lazy(() => import('@/app/pages/DocumentsPage'))
const WorkflowPage = lazy(() => import('@/app/pages/WorkflowPage'))
const ResearchPage = lazy(() => import('@/app/pages/ResearchPage'))
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
        path: '/knowledge',
        element: (
          <SuspenseWrapper>
            <KnowledgePage />
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
    ],
  },
])
