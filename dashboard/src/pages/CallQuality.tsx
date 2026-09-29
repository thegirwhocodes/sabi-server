import { useQuery } from '@tanstack/react-query'
import { Phone, AlertTriangle, CheckCircle, Clock, Play } from 'lucide-react'
import { useState } from 'react'

export function CallQuality() {
  const [statusFilter, setStatusFilter] = useState('all')
  const [reviewFilter, setReviewFilter] = useState('unreviewed')

  const { data: calls } = useQuery({
    queryKey: ['calls', statusFilter, reviewFilter],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (reviewFilter !== 'all') params.append('review_status', reviewFilter)
      
      const response = await fetch(`/api/operations/calls?${params}`)
      if (!response.ok) throw new Error('Failed to fetch calls')
      return response.json()
    },
  })

  const { data: safeguarding } = useQuery({
    queryKey: ['safeguarding-alerts'],
    queryFn: async () => {
      const response = await fetch('/api/operations/calls/safeguarding')
      if (!response.ok) throw new Error('Failed to fetch alerts')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Call Quality & Safety</h1>
        <p className="text-ink-muted">Review calls and manage safeguarding</p>
      </div>

      {safeguarding?.items?.length > 0 && (
        <div className="mb-6 bg-bad-bg border border-bad-line rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-bad flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-medium text-bad mb-1">
                Safeguarding Alerts ({safeguarding.items.length})
              </h3>
              <p className="text-sm text-ink-soft">
                {safeguarding.items.length} call(s) flagged for immediate review
              </p>
            </div>
            <button className="px-3 py-1.5 bg-bad text-card rounded-lg text-sm font-medium hover:bg-opacity-90">
              Review Now
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {calls?.stats?.total || 0}
          </div>
          <div className="text-sm text-ink-muted">Total Calls Today</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {calls?.stats?.avgQuality || 0}%
          </div>
          <div className="text-sm text-ink-muted">Avg Quality Score</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-warn mb-1">
            {calls?.stats?.needsReview || 0}
          </div>
          <div className="text-sm text-ink-muted">Pending Review</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {calls?.stats?.avgDuration || 0}m
          </div>
          <div className="text-sm text-ink-muted">Avg Duration</div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <div className="flex gap-4">
            <select
              value={reviewFilter}
              onChange={(e) => setReviewFilter(e.target.value)}
              className="px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
            >
              <option value="all">All Calls</option>
              <option value="unreviewed">Unreviewed</option>
              <option value="reviewed">Reviewed</option>
              <option value="follow_up">Follow Up</option>
              <option value="safety_escalation">Safety Escalation</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Call ID</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Student</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Duration</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Quality</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Flags</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Review Status</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {calls?.items?.map((call: any) => (
                <tr key={call.call_uuid} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div className="font-mono text-xs text-ink-muted">{call.call_id?.slice(0, 8)}...</div>
                    <div className="text-xs text-ink-muted">{call.created_at}</div>
                  </td>
                  <td className="py-4 px-6">
                    <div className="font-medium text-ink">{call.student_name || 'Unknown'}</div>
                    <div className="text-xs text-ink-muted">{call.phone_number}</div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">
                    {Math.floor(call.duration_seconds / 60)}m {call.duration_seconds % 60}s
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-paper rounded-full h-2 max-w-[80px]">
                        <div 
                          className={`rounded-full h-2 ${
                            call.quality_score >= 80 ? 'bg-green' :
                            call.quality_score >= 60 ? 'bg-warn' : 'bg-bad'
                          }`}
                          style={{ width: `${call.quality_score || 0}%` }}
                        />
                      </div>
                      <span className="text-xs text-ink-muted">{call.quality_score || 0}%</span>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex flex-wrap gap-1">
                      {call.quality_flags?.slice(0, 2).map((flag: string) => (
                        <span key={flag} className="inline-flex px-2 py-0.5 rounded text-xs bg-warn-bg text-warn">
                          {flag.replace(/_/g, ' ')}
                        </span>
                      ))}
                      {call.quality_flags?.length > 2 && (
                        <span className="text-xs text-ink-muted">+{call.quality_flags.length - 2}</span>
                      )}
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                      call.review_status === 'reviewed' ? 'bg-green-soft text-green' :
                      call.review_status === 'safety_escalation' ? 'bg-bad-bg text-bad' :
                      call.review_status === 'follow_up' ? 'bg-warn-bg text-warn' :
                      'bg-paper text-ink-muted'
                    }`}>
                      {call.review_status?.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-right">
                    <button className="flex items-center gap-1 text-sm text-gold-deep hover:text-gold transition-colors ml-auto">
                      <Play className="w-4 h-4" />
                      Review
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
