import { useQuery } from '@tanstack/react-query'
import { Clock, User, Phone, AlertTriangle } from 'lucide-react'

export function RecentActivity() {
  const { data: activities } = useQuery({
    queryKey: ['recent-activity'],
    queryFn: async () => {
      const response = await fetch('/api/operations/activity/recent?limit=10')
      if (!response.ok) throw new Error('Failed to fetch activity')
      return response.json()
    },
    refetchInterval: 30000,
  })

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'call':
        return Phone
      case 'alert':
        return AlertTriangle
      case 'student':
        return User
      default:
        return Clock
    }
  }

  return (
    <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
      <h2 className="text-lg font-medium mb-4">Recent Activity</h2>
      <div className="space-y-3">
        {activities?.items?.map((activity: any) => {
          const Icon = getActivityIcon(activity.type)
          return (
            <div key={activity.id} className="flex items-start gap-3 pb-3 border-b border-line last:border-0">
              <div className="bg-paper rounded-lg p-2">
                <Icon className="w-4 h-4 text-ink-muted" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-ink">{activity.description}</p>
                <p className="text-xs text-ink-muted mt-0.5">{activity.timestamp}</p>
              </div>
            </div>
          )
        })}
        {!activities?.items?.length && (
          <p className="text-sm text-ink-muted text-center py-8">No recent activity</p>
        )}
      </div>
    </div>
  )
}
