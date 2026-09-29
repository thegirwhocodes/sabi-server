import { LucideIcon } from 'lucide-react'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface MetricCardProps {
  title: string
  value: string | number
  change?: number
  icon: LucideIcon
  trend?: 'up' | 'down'
}

export function MetricCard({ title, value, change, icon: Icon, trend }: MetricCardProps) {
  const showChange = change !== undefined && change !== 0
  const isPositive = trend === 'up'

  return (
    <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
      <div className="flex items-start justify-between mb-3">
        <div className="bg-gold-wash rounded-lg p-2">
          <Icon className="w-5 h-5 text-gold-deep" />
        </div>
        {showChange && (
          <div className={`flex items-center gap-1 text-sm ${isPositive ? 'text-green' : 'text-bad'}`}>
            {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <span>{Math.abs(change!)}%</span>
          </div>
        )}
      </div>
      <div className="text-2xl font-semibold text-ink mb-1">{value}</div>
      <div className="text-sm text-ink-muted">{title}</div>
    </div>
  )
}
