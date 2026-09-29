import { useQuery } from '@tanstack/react-query'
import { Server, Activity, AlertTriangle, CheckCircle, DollarSign } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export function Infrastructure() {
  const { data: infra } = useQuery({
    queryKey: ['infrastructure'],
    queryFn: async () => {
      const response = await fetch('/api/operations/infrastructure/status')
      if (!response.ok) throw new Error('Failed to fetch infrastructure')
      return response.json()
    },
    refetchInterval: 30000,
  })

  const { data: costs } = useQuery({
    queryKey: ['infrastructure-costs'],
    queryFn: async () => {
      const response = await fetch('/api/operations/infrastructure/costs')
      if (!response.ok) throw new Error('Failed to fetch costs')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Infrastructure</h1>
        <p className="text-ink-muted">Monitor systems and service providers</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-5 h-5 text-green" />
            <span className="text-2xl font-semibold text-green">
              {infra?.healthyServices || 0}/{infra?.totalServices || 0}
            </span>
          </div>
          <div className="text-sm text-ink-muted">Services Healthy</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {infra?.uptime || 0}%
          </div>
          <div className="text-sm text-ink-muted">30-Day Uptime</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {infra?.avgLatency || 0}ms
          </div>
          <div className="text-sm text-ink-muted">Avg Response Time</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            ${costs?.dailyInfra?.toFixed(2) || 0}
          </div>
          <div className="text-sm text-ink-muted">Daily Infra Cost</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Service Status</h2>
          <div className="space-y-4">
            {infra?.services?.map((service: any) => (
              <div key={service.name} className="border-b border-line pb-4 last:border-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    {service.status === 'operational' ? (
                      <CheckCircle className="w-5 h-5 text-green" />
                    ) : service.status === 'degraded' ? (
                      <AlertTriangle className="w-5 h-5 text-warn" />
                    ) : (
                      <Activity className="w-5 h-5 text-bad" />
                    )}
                    <div>
                      <div className="font-medium text-ink">{service.name}</div>
                      <div className="text-xs text-ink-muted">{service.provider}</div>
                    </div>
                  </div>
                  <span className={`text-sm ${
                    service.status === 'operational' ? 'text-green' :
                    service.status === 'degraded' ? 'text-warn' : 'text-bad'
                  }`}>
                    {service.latency}ms
                  </span>
                </div>
                <div className="flex justify-between text-xs text-ink-muted">
                  <span>Uptime: {service.uptime}%</span>
                  <span>Requests: {service.requests.toLocaleString()}/day</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Response Time (24h)</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={infra?.latencyData || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="time" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Line type="monotone" dataKey="api" stroke="#cba868" strokeWidth={2} name="API" />
              <Line type="monotone" dataKey="stt" stroke="#1e7b43" strokeWidth={2} name="STT" />
              <Line type="monotone" dataKey="tts" stroke="#9b5b00" strokeWidth={2} name="TTS" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
        <h2 className="text-lg font-medium mb-4">Provider Costs</h2>
        <div className="space-y-4">
          {costs?.byProvider?.map((provider: any) => (
            <div key={provider.name}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-sm font-medium text-ink">{provider.name}</span>
                  <span className="text-xs text-ink-muted ml-2">({provider.service})</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-ink-muted">{provider.usage}</span>
                  <span className="text-sm font-medium text-ink">${provider.cost.toFixed(2)}/day</span>
                </div>
              </div>
              <div className="w-full bg-paper rounded-full h-2">
                <div 
                  className="bg-gold rounded-full h-2"
                  style={{ width: `${(provider.cost / costs.dailyInfra) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
