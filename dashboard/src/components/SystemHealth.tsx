import { useQuery } from '@tanstack/react-query'
import { Activity, AlertCircle, CheckCircle, XCircle } from 'lucide-react'

export function SystemHealth() {
  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: async () => {
      const response = await fetch('/api/operations/health/status')
      if (!response.ok) throw new Error('Failed to fetch health')
      return response.json()
    },
    refetchInterval: 15000,
  })

  const services = [
    { name: 'API Server', status: health?.api || 'operational' },
    { name: 'Database', status: health?.database || 'operational' },
    { name: 'STT Service', status: health?.stt || 'operational' },
    { name: 'LLM Service', status: health?.llm || 'operational' },
    { name: 'TTS Service', status: health?.tts || 'operational' },
    { name: 'Telephony', status: health?.telephony || 'operational' },
  ]

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'operational':
        return <CheckCircle className="w-4 h-4 text-green" />
      case 'degraded':
        return <AlertCircle className="w-4 h-4 text-warn" />
      case 'down':
        return <XCircle className="w-4 h-4 text-bad" />
      default:
        return <Activity className="w-4 h-4 text-ink-muted" />
    }
  }

  return (
    <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
      <h2 className="text-lg font-medium mb-4">System Health</h2>
      <div className="space-y-3">
        {services.map((service) => (
          <div key={service.name} className="flex items-center justify-between py-2 border-b border-line last:border-0">
            <span className="text-sm text-ink">{service.name}</span>
            <div className="flex items-center gap-2">
              {getStatusIcon(service.status)}
              <span className="text-xs text-ink-muted capitalize">{service.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
