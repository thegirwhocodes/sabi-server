import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Target, AlertCircle } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export function LearningAnalytics() {
  const { data: analytics } = useQuery({
    queryKey: ['learning-analytics'],
    queryFn: async () => {
      const response = await fetch('/api/operations/learning/analytics')
      if (!response.ok) throw new Error('Failed to fetch analytics')
      return response.json()
    },
  })

  const { data: interventions } = useQuery({
    queryKey: ['interventions-needed'],
    queryFn: async () => {
      const response = await fetch('/api/operations/learning/interventions')
      if (!response.ok) throw new Error('Failed to fetch interventions')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Learning Analytics</h1>
        <p className="text-ink-muted">Track outcomes and identify interventions</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {analytics?.masteryRate || 0}%
          </div>
          <div className="text-sm text-ink-muted">Mastery Rate</div>
          <div className="flex items-center gap-1 text-xs text-green mt-2">
            <TrendingUp className="w-3 h-3" />
            <span>+5% vs last week</span>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {analytics?.avgLessonsPerWeek || 0}
          </div>
          <div className="text-sm text-ink-muted">Avg Lessons/Week</div>
          <div className="flex items-center gap-1 text-xs text-green mt-2">
            <TrendingUp className="w-3 h-3" />
            <span>+0.5 vs last week</span>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-warn mb-1">
            {interventions?.count || 0}
          </div>
          <div className="text-sm text-ink-muted flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Interventions Needed
          </div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {analytics?.completionRate || 0}%
          </div>
          <div className="text-sm text-ink-muted">Lesson Completion</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Progress Over Time</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={analytics?.progressData || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="week" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="mastery" stroke="#1e7b43" strokeWidth={2} />
              <Line type="monotone" dataKey="engagement" stroke="#cba868" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Skill Performance</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={analytics?.skillData || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8dfc9" />
              <XAxis dataKey="skill" stroke="#857a68" />
              <YAxis stroke="#857a68" />
              <Tooltip />
              <Bar dataKey="score" fill="#cba868" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <h2 className="text-lg font-medium">Students Needing Intervention</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Student</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Issue</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Severity</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Recommended Action</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {interventions?.items?.map((item: any) => (
                <tr key={item.id} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div className="font-medium text-ink">{item.studentName}</div>
                    <div className="text-xs text-ink-muted">{item.phone}</div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{item.issue}</td>
                  <td className="py-4 px-6">
                    <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                      item.severity === 'high' ? 'bg-bad-bg text-bad' :
                      item.severity === 'medium' ? 'bg-warn-bg text-warn' :
                      'bg-green-soft text-green'
                    }`}>
                      {item.severity}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{item.recommendation}</td>
                  <td className="py-4 px-6 text-right">
                    <button className="text-sm text-gold-deep hover:text-gold transition-colors">
                      Take Action
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
