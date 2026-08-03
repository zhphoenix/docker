import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  MessageSquare,
  Bot,
  BookOpen,
  FolderOpen,
  GitBranch,
  BarChart3,
  Newspaper,
  Brain,
  Database,
  Activity,
  Settings,
  PanelLeftClose,
  PanelLeft,
  ClipboardCheck,
} from 'lucide-react'
import { useAppStore } from '@/stores/app-store'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/knowledge', icon: BookOpen, label: 'Knowledge' },
  { to: '/knowledge/review', icon: ClipboardCheck, label: 'Review' },
  { to: '/documents', icon: FolderOpen, label: 'Documents' },
  { to: '/workflow', icon: GitBranch, label: 'Workflow' },
  { to: '/research', icon: BarChart3, label: 'Research' },
  { to: '/news', icon: Newspaper, label: 'News' },
  { to: '/models', icon: Brain, label: 'Models' },
  { to: '/vector-db', icon: Database, label: 'Vector DB' },
  { to: '/monitor', icon: Activity, label: 'Monitor' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore()

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? 68 : 240 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      className={cn(
        'relative flex h-full flex-col border-r border-sidebar-border',
        'bg-sidebar backdrop-blur-[30px]',
        'overflow-hidden'
      )}
    >
      {/* Logo / Brand */}
      <div className="flex h-14 items-center gap-3 px-4">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          AI
        </div>
        {!sidebarCollapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-sm font-semibold text-sidebar-foreground whitespace-nowrap"
          >
            AI Platform
          </motion.span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-200',
                'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                  : 'text-sidebar-foreground/70'
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    'size-5 shrink-0 transition-transform duration-200',
                    isActive && 'scale-110',
                    'group-hover:scale-105'
                  )}
                  strokeWidth={1.8}
                />
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="whitespace-nowrap"
                  >
                    {item.label}
                  </motion.span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Collapse Toggle */}
      <div className="border-t border-sidebar-border p-3">
        <button
          onClick={toggleSidebar}
          className={cn(
            'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm',
            'text-sidebar-foreground/50 transition-colors duration-200',
            'hover:bg-sidebar-accent hover:text-sidebar-foreground'
          )}
        >
          {sidebarCollapsed ? (
            <PanelLeft className="size-5 shrink-0" strokeWidth={1.8} />
          ) : (
            <>
              <PanelLeftClose className="size-5 shrink-0" strokeWidth={1.8} />
              <span className="whitespace-nowrap">收起侧栏</span>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  )
}
