import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
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
  Loader2,
} from 'lucide-react'

import {
  Command,
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from '@/components/ui/command'
import { useDebounce } from '@/hooks/useDebounce'
import { fetchNewsArticles } from '@/services/news'
import { fetchEntities } from '@/services/knowledge'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/knowledge', icon: BookOpen, label: 'Knowledge' },
  { to: '/documents', icon: FolderOpen, label: 'Documents' },
  { to: '/workflow', icon: GitBranch, label: 'Workflow' },
  { to: '/research', icon: BarChart3, label: 'Research' },
  { to: '/news', icon: Newspaper, label: 'News' },
  { to: '/models', icon: Brain, label: 'Models' },
  { to: '/vector-db', icon: Database, label: 'Vector DB' },
  { to: '/monitor', icon: Activity, label: 'Monitor' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const debouncedQuery = useDebounce(input, 300)

  // Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [open, onOpenChange])

  // News search
  const { data: newsData, isFetching: newsLoading } = useQuery({
    queryKey: ['cmd-news', debouncedQuery],
    queryFn: () => fetchNewsArticles({ keyword: debouncedQuery, limit: 5, days: 30 }),
    enabled: debouncedQuery.length >= 2,
  })

  // Entity search
  const { data: entityData, isFetching: entityLoading } = useQuery({
    queryKey: ['cmd-entities', debouncedQuery],
    queryFn: () => fetchEntities({ name: debouncedQuery, limit: 5 }),
    enabled: debouncedQuery.length >= 2,
  })

  const runCommand = (fn: () => void) => {
    onOpenChange(false)
    setInput('')
    fn()
  }

  const newsArticles = newsData?.articles ?? []
  const entities = entityData?.entities ?? []
  const showSearch = debouncedQuery.length >= 2

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <Command shouldFilter={false}>
        <CommandInput
          placeholder="搜索页面、新闻、实体..."
          value={input}
          onValueChange={setInput}
        />
        <CommandList>
          <CommandEmpty>无匹配结果</CommandEmpty>

          {/* Page Navigation */}
          <CommandGroup heading="页面">
            {NAV_ITEMS.map((item) => (
              <CommandItem
                key={item.to}
                value={item.label}
                onSelect={() => runCommand(() => navigate(item.to))}
              >
                <item.icon className="size-4 text-muted-foreground" />
                <span>{item.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>

          {/* News Results */}
          {showSearch && (
            <>
              <CommandSeparator />
              <CommandGroup heading="新闻">
                {newsLoading && (
                  <CommandItem disabled>
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    <span className="text-muted-foreground">搜索中...</span>
                  </CommandItem>
                )}
                {!newsLoading &&
                  newsArticles.map((article) => (
                    <CommandItem
                      key={article.id}
                      value={`news-${article.id}`}
                      onSelect={() => runCommand(() => navigate('/news'))}
                    >
                      <Newspaper className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{article.title}</span>
                    </CommandItem>
                  ))}
                {!newsLoading && newsArticles.length === 0 && (
                  <CommandItem disabled>
                    <span className="text-xs text-muted-foreground">无新闻结果</span>
                  </CommandItem>
                )}
              </CommandGroup>
            </>
          )}

          {/* Entity Results */}
          {showSearch && (
            <>
              <CommandSeparator />
              <CommandGroup heading="知识实体">
                {entityLoading && (
                  <CommandItem disabled>
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    <span className="text-muted-foreground">搜索中...</span>
                  </CommandItem>
                )}
                {!entityLoading &&
                  entities.map((entity) => (
                    <CommandItem
                      key={entity.id}
                      value={`entity-${entity.id}`}
                      onSelect={() => runCommand(() => navigate('/knowledge'))}
                    >
                      <BookOpen className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{entity.name}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {entity.entity_type}
                      </span>
                    </CommandItem>
                  ))}
                {!entityLoading && entities.length === 0 && (
                  <CommandItem disabled>
                    <span className="text-xs text-muted-foreground">无实体结果</span>
                  </CommandItem>
                )}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
