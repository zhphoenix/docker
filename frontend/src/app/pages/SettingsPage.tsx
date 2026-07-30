import { motion } from 'framer-motion'
import { Sun, Moon, Monitor } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useTheme } from '@/theme/ThemeProvider'

const themeOptions = [
  { value: 'light' as const, label: '浅色', icon: Sun, desc: '明亮的界面主题' },
  { value: 'dark' as const, label: '深色', icon: Moon, desc: '护眼的暗色主题' },
  { value: 'system' as const, label: '跟随系统', icon: Monitor, desc: '自动匹配系统设置' },
]

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理 AI Platform 偏好设置
        </p>
      </div>

      {/* Appearance */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">外观</CardTitle>
            <CardDescription>选择界面主题</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              {themeOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setTheme(option.value)}
                  className={cn(
                    'flex flex-col items-center gap-3 rounded-xl border-2 p-5 transition-all duration-200',
                    theme === option.value
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  )}
                >
                  <option.icon
                    className={cn(
                      'size-6',
                      theme === option.value ? 'text-primary' : 'text-muted-foreground'
                    )}
                    strokeWidth={1.8}
                  />
                  <div className="text-center">
                    <div
                      className={cn(
                        'text-sm font-medium',
                        theme === option.value
                          ? 'text-primary'
                          : 'text-foreground'
                      )}
                    >
                      {option.label}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {option.desc}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* API Configuration */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">API 配置</CardTitle>
            <CardDescription>后端服务连接设置</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                API 端点
              </label>
              <div className="flex items-center rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                {import.meta.env.VITE_API_BASE_URL || 'http://localhost:8100'}
                <span className="ml-auto text-xs text-muted-foreground">
                  通过环境变量配置
                </span>
              </div>
            </div>
            <Separator />
            <p className="text-xs text-muted-foreground">
              API 端点通过 <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">VITE_API_BASE_URL</code> 环境变量配置。
              开发模式下 Vite 代理会自动转发请求到 FastAPI 服务。
            </p>
          </CardContent>
        </Card>
      </motion.div>

      {/* About */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">关于</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>AI Platform v1.0</p>
            <p>本地部署的 AI 投研平台</p>
            <p className="text-xs">
              技术栈: React + TypeScript + TailwindCSS + shadcn/ui + Framer Motion
            </p>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
