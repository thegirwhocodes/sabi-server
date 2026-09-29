import { useQuery } from '@tantml/react-query'
import { DollarSign, TrendingDown, TrendingUp, AlertCircle } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const COLORS = ['#1e7b43', '#cba868', '#9b5b00', '#b42318']

export function FinancialOperations() {
  const { data: financial } = useQuery({
    queryKey: ['financial-metrics'],
    queryFn: async () => {
      const response = await fetch('/api/operations/finance/metrics')
      if (!response.ok) throw new Error('Failed to fetch financial data')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Financial Operations</h1>
        <p className="text-ink-muted">Track costs, burn rate, and ROI</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            ${financial?.monthlyBurn?.toFixed(0) || 0}
          </div>
          <div className="text-sm text-ink-muted">Monthly Burn</div>
          <div className="flex items-center gap-1 text-xs text-bad mt-2">
            <TrendingUp className="w-3 h-3" />
            <span>+12% vs last month</span>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            ${financial?.costPerStudent?.toFixed(2) || 0}
          </div>
          <div className="text-sm text-ink-muted">Cost per Student</div>
          <div className="flex items-center gap-1 text-xs text-green mt-2">
            <TrendingDown className="w-3 h-3" />
            <span>-8% vs last month</span>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            ${financial?.costPerLesson?.toFixed(2) || 0}
          </div>
          <div className="text-sm text-ink-muted">Cost per Lesson</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {financial?.runwayMonths || 0}
          </div>
          <div className="text-sm text-ink-muted">Months Runway</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Monthly Cost Breakdown</h2>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={financial?.costBreakdown || []}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={(entry) => `${entry.name}: $${entry.value}`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {financial?.costBreakdown?.map((_: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Cost Trend (Last 6 Months)</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={financial?.costTrend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="month" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="total" stroke="#cba868" strokeWidth={2} name="Total Cost" />
              <Line type="monotone" dataKey="perStudent" stroke="#1e7b43" strokeWidth={2} name="Per Student" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Cost by Service</h2>
          <div className="space-y-4">
            {financial?.servicecosts?.map((service: any) => (
              <div key={service.name}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-ink">{service.name}</span>
                  <span className="text-sm font-medium text-ink">${service.cost.toFixed(2)}</span>
                </div>
                <div className="w-full bg-paper rounded-full h-2">
                  <div 
                    className="bg-gold rounded-full h-2"
                    style={{ width: `${(service.cost / financial.monthlyBurn) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Funding & Runway</h2>
          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-ink-muted">Current Balance</span>
                <span className="text-lg font-semibold text-ink">
                  ${financial?.currentBalance?.toFixed(0) || 0}
                </span>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-ink-muted">Monthly Burn Rate</span>
                <span className="text-lg font-semibold text-bad">
                  ${financial?.monthlyBurn?.toFixed(0) || 0}
                </span>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-ink-muted">Projected Runway</span>
                <span className="text-lg font-semibold text-green">
                  {financial?.runwayMonths || 0} months
                </span>
              </div>
              <div className="w-full bg-paper rounded-full h-3 mt-3">
                <div 
                  className={`rounded-full h-3 ${
                    financial?.runwayMonths >= 12 ? 'bg-green' :
                    financial?.runwayMonths >= 6 ? 'bg-warn' : 'bg-bad'
                  }`}
                  style={{ width: `${Math.min((financial?.runwayMonths || 0) / 24 * 100, 100)}%` }}
                />
              </div>
            </div>
            {financial?.runwayMonths < 6 && (
              <div className="flex items-start gap-2 p-3 bg-warn-bg border border-warn-line rounded-lg">
                <AlertCircle className="w-4 h-4 text-warn flex-shrink-0 mt-0.5" />
                <p className="text-sm text-warn">Runway below 6 months - consider fundraising</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
