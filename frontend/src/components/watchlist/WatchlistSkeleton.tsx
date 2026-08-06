import { Skeleton } from '@/components/ui/skeleton'

export function WatchlistSkeleton() {
  return (
    <div className="space-y-6">
      {/* Overview cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-xl border p-4">
            <Skeleton className="mb-2 h-3 w-12" />
            <Skeleton className="h-7 w-14" />
          </div>
        ))}
      </div>
      {/* Timeline + Alerts row */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border p-4">
          <Skeleton className="mb-3 h-5 w-24" />
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="mb-2 h-16 w-full" />
          ))}
        </div>
        <div className="rounded-xl border p-4">
          <Skeleton className="mb-3 h-5 w-24" />
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="mb-2 h-14 w-full" />
          ))}
        </div>
      </div>
      {/* Watchlist grid */}
      <div className="rounded-xl border p-4">
        <Skeleton className="mb-3 h-5 w-28" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
