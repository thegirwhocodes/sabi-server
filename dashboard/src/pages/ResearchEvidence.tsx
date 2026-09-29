import { useQuery } from '@tanstack/react-query'
import { FlaskConical, FileText, Download, TrendingUp } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export function ResearchEvidence() {
  const { data: research } = useQuery({
    queryKey: ['research-data'],
    queryFn: async () => {
      const response = await fetch('/api/operations/research/summary')
      if (!response.ok) throw new Error('Failed to fetch research')
      return response.json()
    },
  })

  const { data: pilots } = useQuery({
    queryKey: ['pilot-programs'],
    queryFn: async () => {
      const response = await fetch('/api/operations/research/pilots')
      if (!response.ok) throw new Error('Failed to fetch pilots')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Research & Evidence</h1>
          <p className="text-ink-muted">Track impact and generate reports</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors">
          <Download className="w-5 h-5" />
          <span className="font-medium">Export Report</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            +{research?.learningGains || 0}%
          </div>
          <div className="text-sm text-ink-muted">Avg Learning Gains</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {research?.studentsImpacted || 0}
          </div>
          <div className="text-sm text-ink-muted">Students Impacted</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {research?.totalLessons || 0}
          </div>
          <div className="text-sm text-ink-muted">Total Lessons</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {research?.completionRate || 0}%
          </div>
          <div className="text-sm text-ink-muted">Completion Rate</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Learning Gains by Cohort</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={research?.gainsByCohort || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="cohort" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Bar dataKey="preTest" fill="#d9cdaf" name="Pre-Test" />
              <Bar dataKey="postTest" fill="#1e7b43" name="Post-Test" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Engagement Over Time</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={research?.engagementTrend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="week" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="activeLearners" stroke="#cba868" strokeWidth={2} />
              <Line type="monotone" dataKey="avgMinutes" stroke="#1e7b43" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <h2 className="text-lg font-medium">Active Pilot Programs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Program</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Participants</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Duration</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Status</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Metrics</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {pilots?.items?.map((pilot: any) => (
                <tr key={pilot.id} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div className="font-medium text-ink">{pilot.name}</div>
                    <div className="text-xs text-ink-muted">{pilot.description}</div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{pilot.participants}</td>
                  <td className="py-4 px-6 text-sm text-ink">{pilot.duration}</td>
                  <td className="py-4 px-6">
                    <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                      pilot.status === 'active' ? 'bg-green-soft text-green' :
                      pilot.status === 'planning' ? 'bg-warn-bg text-warn' :
                      'bg-paper text-ink-muted'
                    }`}>
                      {pilot.status}
                    </span>
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex flex-wrap gap-2 text-xs text-ink-muted">
                      <span>Engagement: {pilot.engagement}%</span>
                      <span>Gains: +{pilot.gains}%</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-right">
                    <button className="flex items-center gap-1 text-sm text-gold-deep hover:text-gold transition-colors ml-auto">
                      <FileText className="w-4 h-4" />
                      Report
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
