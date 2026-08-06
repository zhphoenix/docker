import { useState } from 'react'
import { RefreshCw, Download, Mail, FileText, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/common/EmptyState'
import { useWatchlistReport } from '@/hooks/useWatchlist'
import { exportReport, exportReportPdf, emailReport } from '@/services/watchlist'

interface ParsedSummary {
  key_points: string[]
  focus_stocks: string[]
}

function parseSummary(raw: string | null): ParsedSummary | null {
  if (!raw) return null
  try {
    const obj = JSON.parse(raw)
    if (!obj || typeof obj !== 'object') return null
    return {
      key_points: Array.isArray(obj.key_points)
        ? obj.key_points.filter((k): k is string => typeof k === 'string')
        : [],
      focus_stocks: Array.isArray(obj.focus_stocks)
        ? obj.focus_stocks.filter((s): s is string => typeof s === 'string')
        : [],
    }
  } catch {
    return null
  }
}

export function DailyReport() {
  const { data, isLoading, refetch, isFetching } = useWatchlistReport()
  const [emailOpen, setEmailOpen] = useState(false)
  const [emailTo, setEmailTo] = useState('')
  const [emailing, setEmailing] = useState(false)
  const [emailError, setEmailError] = useState('')
  const [emailOk, setEmailOk] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-24" /></CardHeader>
        <CardContent>
          <Skeleton className="mb-2 h-16 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    )
  }

  const report = data?.report
  const reportId = report?.id
  const parsed = parseSummary(report?.summary)
  const hasKeyPoints = !!parsed && parsed.key_points.length > 0

  const handleExport = async () => {
    if (!reportId) return
    setExporting(true)
    try {
      const blob = await exportReport(reportId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `watchlist-report-${report?.report_date ?? 'unknown'}.md`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  const handleSendEmail = async () => {
    if (!reportId || !emailTo.trim()) return
    setEmailing(true)
    setEmailError('')
    setEmailOk('')
    try {
      await emailReport(reportId, emailTo.trim())
      setEmailOk('已发送')
      setEmailTo('')
      setTimeout(() => setEmailOpen(false), 800)
    } catch (e) {
      setEmailError((e as Error)?.message || '发送失败')
    } finally {
      setEmailing(false)
    }
  }

  const handleExportPdf = async () => {
    if (!reportId) return
    setExportingPdf(true)
    try {
      const blob = await exportReportPdf(reportId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `watchlist-report-${report?.report_date ?? 'unknown'}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExportingPdf(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">
          {report ? report.title || '每日报告' : '每日报告'}
        </CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.open('/research', '_blank')}
          >
            <FileText className="mr-1 size-4" />
            研究报告
          </Button>
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`mr-1 size-4 ${isFetching ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          {reportId && (
            <>
              <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
                {exporting ? (
                  <Loader2 className="mr-1 size-4 animate-spin" />
                ) : (
                  <Download className="mr-1 size-4" />
                )}
                导出 MD
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportPdf}
                disabled={exportingPdf}
              >
                {exportingPdf ? (
                  <Loader2 className="mr-1 size-4 animate-spin" />
                ) : (
                  <FileText className="mr-1 size-4" />
                )}
                下载 PDF
              </Button>
              <Button variant="outline" size="sm" onClick={() => setEmailOpen(true)}>
                <Mail className="mr-1 size-4" />
                发送邮箱
              </Button>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {!report ? (
          <EmptyState title="暂无报告" description="运行监控后自动生成" />
        ) : (
          <>
            {hasKeyPoints && (
              <div className="mb-4 rounded-lg border border-primary/20 bg-primary/5 p-3">
                <h4 className="mb-2 text-xs font-medium text-primary">今日关注要点</h4>
                <ul className="space-y-1.5">
                  {parsed.key_points.map((kp, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                      {kp}
                    </li>
                  ))}
                </ul>
                {parsed.focus_stocks.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-muted-foreground">重点关注</span>
                    {parsed.focus_stocks.map((code) => (
                      <Badge key={code} variant="secondary">
                        {code}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
            <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs leading-relaxed">
              {report.content}
            </pre>
          </>
        )}
      </CardContent>

      {/* Email dialog */}
      <Dialog open={emailOpen} onOpenChange={setEmailOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>通过邮箱发送报告</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <Input
              type="email"
              placeholder="收件人邮箱"
              value={emailTo}
              onChange={(e) => setEmailTo(e.target.value)}
            />
            {emailError && <p className="text-sm text-destructive">{emailError}</p>}
            {emailOk && <p className="text-sm text-emerald-600">{emailOk}</p>}
            <Button onClick={handleSendEmail} disabled={emailing || !emailTo.trim()}>
              {emailing ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <Mail className="mr-1 size-4" />
              )}
              发送
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  )
}