import { useQuery } from '@tanstack/react-query'
import { Users, UserPlus, Activity, Clock } from 'lucide-react'
import { useState } from 'react'

export function TeamManagement() {
  const [roleFilter, setRoleFilter] = useState('all')

  const { data: team } = useQuery({
    queryKey: ['team-members', roleFilter],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (roleFilter !== 'all') params.append('role', roleFilter)
      
      const response = await fetch(`/api/operations/team?${params}`)
      if (!response.ok) throw new Error('Failed to fetch team')
      return response.json()
    },
  })

  const { data: capacity } = useQuery({
    queryKey: ['team-capacity'],
    queryFn: async () => {
      const response = await fetch('/api/operations/team/capacity')
      if (!response.ok) throw new Error('Failed to fetch capacity')
      return response.json()
    },
  })

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Team Management</h1>
          <p className="text-ink-muted">Manage roles, permissions, and capacity</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors">
          <UserPlus className="w-5 h-5" />
          <span className="font-medium">Add Team Member</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {team?.stats?.total || 0}
          </div>
          <div className="text-sm text-ink-muted">Total Team Members</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-green mb-1">
            {team?.stats?.active || 0}
          </div>
          <div className="text-sm text-ink-muted">Active Today</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {capacity?.avgUtilization || 0}%
          </div>
          <div className="text-sm text-ink-muted">Avg Utilization</div>
        </div>
        <div className="bg-card rounded-xl border border-line p-5 shadow-sabi-soft">
          <div className="text-2xl font-semibold text-ink mb-1">
            {capacity?.tasksPending || 0}
          </div>
          <div className="text-sm text-ink-muted">Pending Tasks</div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft mb-8">
        <div className="p-6 border-b border-line">
          <h2 className="text-lg font-medium">Team Capacity</h2>
        </div>
        <div className="p-6">
          <div className="space-y-4">
            {capacity?.byRole?.map((role: any) => (
              <div key={role.name}>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-medium text-ink">{role.name}</span>
                    <span className="text-xs text-ink-muted ml-2">({role.count} members)</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-ink-muted">{role.currentLoad}/{role.capacity}</span>
                    <span className="text-sm font-medium text-ink">{role.utilization}%</span>
                  </div>
                </div>
                <div className="w-full bg-paper rounded-full h-3">
                  <div 
                    className={`rounded-full h-3 ${
                      role.utilization >= 90 ? 'bg-bad' :
                      role.utilization >= 75 ? 'bg-warn' : 'bg-green'
                    }`}
                    style={{ width: `${Math.min(role.utilization, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-line shadow-sabi-soft">
        <div className="p-6 border-b border-line">
          <div className="flex items-center gap-4">
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
            >
              <option value="all">All Roles</option>
              <option value="admin">Admin</option>
              <option value="reviewer">Reviewer</option>
              <option value="researcher">Researcher</option>
              <option value="support">Support</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-paper border-b border-line">
              <tr>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Name</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Email</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Role</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Status</th>
                <th className="text-left py-3 px-6 text-xs font-medium text-ink-muted uppercase">Last Active</th>
                <th className="text-right py-3 px-6 text-xs font-medium text-ink-muted uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {team?.items?.map((member: any) => (
                <tr key={member.id} className="hover:bg-paper transition-colors">
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gold-wash flex items-center justify-center text-gold-deep font-medium">
                        {member.name?.charAt(0) || '?'}
                      </div>
                      <span className="font-medium text-ink">{member.name}</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink-muted">{member.email}</td>
                  <td className="py-4 px-6">
                    <span className="inline-flex px-2 py-1 rounded-full text-xs font-medium bg-gold-soft text-gold-deep">
                      {member.role}
                    </span>
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        member.status === 'active' ? 'bg-green' :
                        member.status === 'away' ? 'bg-warn' : 'bg-ink-muted'
                      }`} />
                      <span className="text-sm text-ink capitalize">{member.status}</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-sm text-ink-muted">{member.lastActive}</td>
                  <td className="py-4 px-6 text-right">
                    <button className="text-sm text-gold-deep hover:text-gold transition-colors">
                      Edit
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
