import { useQuery } from '@tanstack/react-query'
import { 
  TrendingUp, 
  TrendingDown, 
  Phone, 
  Users, 
  AlertTriangle,
  CheckCircle,
  Clock,
  DollarSign,
  Activity
} from 'lucide-react'
import { MetricCard } from '../components/MetricCard'
import { RecentActivity } from '../components/RecentActivity'
import { SystemHealth } from '../components/SystemHealth'
import { QuickActions } from '../components/QuickActions'

export function MissionControl() {
  const { data: metrics } = useQuery({
    queryKey: ['mission-metrics'],
    queryFn: async () => {
      const response = await fetch('/api/operations/metrics/mission-control')
      if (!response.ok) throw new Error('Failed to fetch metrics')
      return response.json()
    },
    refetchInterval: 30000,
  })

  const { data: alerts } = useQuery({
    queryKey: ['active-alerts'],
    queryFn: async () => {
      const response = await fetch('/api/operations/alerts/active')
      if (!response.ok) throw new Error('Failed to fetch alerts')
      return response.json()
    },
    refetchInterval: 15000,
  })

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Mission Control</h1>
        <p className="text-ink-muted">Real-time operational overview</p>
      </div>

      {alerts && alerts.length > 0 && (
        <div className="mb-6">
          <div className="bg-warn-bg border border-warn-line rounded-xl p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-warn flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-medium text-warn mb-1">Active Alerts ({alerts.length})</h3>
                <ul className="space-y-1">
                  {alerts.slice(0, 3).map((alert: any) => (
                    <li key={alert.id} className="text-sm text-ink-soft">
                      {alert.message}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Active Students Today"
          value={metrics?.activeStudentsToday || 0}
          change={metrics?.activeStudentsChange || 0}
          icon={Users}
          trend={metrics?.activeStudentsChange >= 0 ? 'up' : 'down'}
        />
        <MetricCard
          title="Calls Today"
          value={metrics?.callsToday || 0}
          change={metrics?.callsChange || 0}
          icon={Phone}
          trend={metrics?.callsChange >= 0 ? 'up' : 'down'}
        />
        <MetricCard
          title="Avg Call Quality"
          value={`${metrics?.avgCallQuality || 0}%`}
          change={metrics?.qualityChange || 0}
          icon={CheckCircle}
          trend={metrics?.qualityChange >= 0 ? 'up' : 'down'}
        />
        <MetricCard
          title="Daily Cost"
          value={`$${metrics?.dailyCost?.toFixed(2) || '0.00'}`}
          change={metrics?.costChange || 0}
          icon={DollarSign}
          trend={metrics?.costChange <= 0 ? 'up' : 'down'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2">
          <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
            <h2 className="text-lg font-medium mb-4">Learning Outcomes (Last 7 Days)</h2>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-green-soft rounded-lg p-4 border border-green-line">
                <div className="text-2xl font-semibold text-green mb-1">
                  {metrics?.learningOutcomes?.onTrack || 0}
                </div>
                <div className="text-sm text-ink-muted">On Track</div>
              </div>
              <div className="bg-warn-bg rounded-lg p-4 border border-warn-line">
                <div className="text-2xl font-semibold text-warn mb-1">
                  {metrics?.learningOutcomes?.needsSupport || 0}
                </div>
                <div className="text-sm text-ink-muted">Needs Support</div>
              </div>
              <div className="bg-bad-bg rounded-lg p-4 border border-bad-line">
                <div className="text-2xl font-semibold text-bad mb-1">
                  {metrics?.learningOutcomes?.atRisk || 0}
                </div>
                <div className="text-sm text-ink-muted">At Risk</div>
              </div>
            </div>
          </div>
        </div>

        <SystemHealth />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RecentActivity />
        <QuickActions />
      </div>
    </div>
  )
}
