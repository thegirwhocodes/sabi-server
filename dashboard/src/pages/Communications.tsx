import { useQuery } from '@tanstack/react-query'
import { MessageSquare, Send, Users, Calendar } from 'lucide-react'
import { useState } from 'react'

export function Communications() {
  const [messageType, setMessageType] = useState('sms')

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: async () => {
      const response = await fetch('/api/operations/communications/campaigns')
      if (!response.ok) throw new Error('Failed to fetch campaigns')
      return response.json()
    },
  })

  const { data: stats } = useQuery({
    queryKey: ['communication-stats'],
    queryFn: async () => {
      const response = await fetch('/api/operations/communications/stats')
      if (!response.ok) throw new Error('Failed to fetch stats')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Communications Hub</h1>
          <p className="text-ink-muted">Manage SMS campaigns and parent engagement</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors">
          <Send className="w-5 h-5" />
          <span className="font-medium">New Campaign</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {stats?.messagesSent || 0}
          </div>
          <div className="text-sm text-ink-muted">Messages Sent (30d)</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {stats?.deliveryRate || 0}%
          </div>
          <div className="text-sm text-ink-muted">Delivery Rate</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {stats?.responseRate || 0}%
          </div>
          <div className="text-sm text-ink-muted">Response Rate</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {stats?.activeCampaigns || 0}
          </div>
          <div className="text-sm text-ink-muted">Active Campaigns</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2 bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Create Message</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-2">Message Type</label>
              <select
                value={messageType}
                onChange={(e) => setMessageType(e.target.value)}
                className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
              >
                <option value="sms">SMS to Parents</option>
                <option value="reminder">Lesson Reminder</option>
                <option value="progress">Progress Update</option>
                <option value="announcement">General Announcement</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-2">Recipients</label>
              <select className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold">
                <option>All Active Parents</option>
                <option>Specific Cohort</option>
                <option>At-Risk Students</option>
                <option>High Performers</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-2">Message</label>
              <textarea
                rows={4}
                placeholder="Enter your message..."
                className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
              />
              <div className="flex justify-between items-center mt-2">
                <span className="text-xs text-ink-muted">160 characters remaining</span>
                <span className="text-xs text-ink-muted">Will reach ~{stats?.estimatedRecipients || 0} people</span>
              </div>
            </div>
            <div className="flex gap-3">
              <button className="flex-1 px-4 py-2 border border-line-strong rounded-lg hover:border-gold hover:bg-gold-wash transition-colors">
                Save Draft
              </button>
              <button className="flex-1 px-4 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors font-medium">
                Send Now
              </button>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
          <h2 className="text-lg font-medium mb-4">Quick Templates</h2>
          <div className="space-y-2">
            {[
              'Welcome message',
              'Lesson reminder',
              'Progress celebration',
              'Missed lesson follow-up',
              'Parent feedback request',
            ].map((template) => (
              <button
                key={template}
                className="w-full text-left px-3 py-2 rounded-lg border border-line hover:border-gold hover:bg-gold-wash transition-colors text-sm"
              >
                {template}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <h2 className="text-lg font-medium">Recent Campaigns</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Campaign</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Type</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Sent</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Delivered</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Responses</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Date</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {campaigns?.items?.map((campaign: any) => (
                <tr key={campaign.id} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div className="font-medium text-ink">{campaign.name}</div>
                    <div className="text-xs text-ink-muted">{campaign.message}</div>
                  </td>
                  <td className="py-4 px-6">
                    <span className="inline-flex px-2 py-1 rounded-full text-xs font-medium bg-gold-soft text-gold-deep">
                      {campaign.type}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{campaign.sent}</td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-ink">{campaign.delivered}</span>
                      <span className="text-xs text-green">({campaign.deliveryRate}%)</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink">{campaign.responses || 0}</td>
                  <td className="py-4 px-6 text-sm text-ink-muted">{campaign.date}</td>
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
