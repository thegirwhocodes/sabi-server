import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Users, Search, Filter, Plus, TrendingUp, AlertTriangle } from 'lucide-react'

export function StudentOperations() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: students } = useQuery({
    queryKey: ['students', searchQuery, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (searchQuery) params.append('q', searchQuery)
      if (statusFilter !== 'all') params.append('status', statusFilter)
      
      const response = await fetch(`/api/operations/students?${params}`)
      if (!response.ok) throw new Error('Failed to fetch students')
      return response.json()
    },
  })

  const { data: cohorts } = useQuery({
    queryKey: ['cohorts'],
    queryFn: async () => {
      const response = await fetch('/api/operations/cohorts')
      if (!response.ok) throw new Error('Failed to fetch cohorts')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Student Operations</h1>
          <p className="text-ink-muted">Manage students and cohorts</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors">
          <Plus className="w-5 h-5" />
          <span className="font-medium">Add Student</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {students?.stats?.total || 0}
          </div>
          <div className="text-sm text-ink-muted">Total Students</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {students?.stats?.active || 0}
          </div>
          <div className="text-sm text-ink-muted">Active This Week</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-warn mb-1">
            {students?.stats?.atRisk || 0}
          </div>
          <div className="text-sm text-ink-muted flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Need Attention
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-ink-muted" />
              <input
                type="text"
                placeholder="Search by name, phone, or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="at_risk">At Risk</option>
              <option value="graduated">Graduated</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Student</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Phone</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Cohort</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Progress</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Last Call</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Status</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {students?.items?.map((student: any) => (
                <tr key={student.id} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div>
                      <div className="font-medium text-ink">{student.name || 'Unnamed Student'}</div>
                      <div className="text-xs text-ink-muted">ID: {student.id}</div>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{student.phone}</td>
                  <td className="py-4 px-6 text-sm text-ink">{student.cohort || 'None'}</td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-paper rounded-full h-2">
                        <div 
                          className="bg-green rounded-full h-2" 
                          style={{ width: `${student.progress || 0}%` }}
                        />
                      </div>
                      <span className="text-xs text-ink-muted">{student.progress || 0}%</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink-muted">{student.lastCall || 'Never'}</td>
                  <td className="py-4 px-6">
                    <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                      student.status === 'active' ? 'bg-green-soft text-green' :
                      student.status === 'at_risk' ? 'bg-warn-bg text-warn' :
                      'bg-paper text-ink-muted'
                    }`}>
                      {student.status}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-right">
                    <button className="text-sm text-gold-deep hover:text-gold transition-colors">
                      View Details
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
