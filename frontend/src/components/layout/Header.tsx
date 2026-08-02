import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Search } from 'lucide-react'
import { CommandPalette } from './CommandPalette'

const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/chat': 'AI Chat',
  '/agents': 'Agent Center',
  '/knowledge': 'Knowledge Base',
  '/documents': 'Documents',
  '/workflow': 'Workflow',
  '/research': 'Research Center',
  '/news': 'News Intelligence',
  '/models': 'Models',
  '/vector-db': 'Vector Database',
  '/monitor': '服务监控',
  '/settings': 'Settings',
}

export function Header() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || 'AI Platform'
  const [commandOpen, setCommandOpen] = useState(false)

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-[30px]">
      {/* macOS Traffic Lights (decorative) */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="size-3 rounded-full bg-[#ff5f57]" />
          <span className="size-3 rounded-full bg-[#febc2e]" />
          <span className="size-3 rounded-full bg-[#28c840]" />
        </div>
        <h1 className="text-sm font-semibold text-foreground">{title}</h1>
      </div>

      {/* Search / Command Palette */}
      <button
        className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
        title="Command+K"
        onClick={() => setCommandOpen(true)}
      >
        <Search className="size-3.5" />
        <span>搜索...</span>
        <kbd className="ml-2 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-medium">
          ⌘K
        </kbd>
      </button>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </header>
  )
}
