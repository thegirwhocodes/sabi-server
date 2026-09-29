import { useQuery } from '@tanstack/react-query'
import { Settings as SettingsIcon, Key, Bell, Globe, Shield } from 'lucide-react'
import { useState } from 'react'

export function Settings() {
  const [activeTab, setActiveTab] = useState('general')

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await fetch('/api/operations/settings')
      if (!response.ok) throw new Error('Failed to fetch settings')
      return response.json()
    },
  })

  const tabs = [
    { id: 'general', name: 'General', icon: SettingsIcon },
    { id: 'auth', name: 'Authentication', icon: Key },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'integrations', name: 'Integrations', icon: Globe },
    { id: 'security', name: 'Security', icon: Shield },
  ]

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-serif font-semibold text-ink mb-2">Settings</h1>
        <p className="text-ink-muted">Configure system preferences</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="bg-card rounded-xl border border-line p-4 shadow-sabi-soft h-fit">
          <nav className="space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-gold text-ink font-medium'
                    : 'text-ink-muted hover:bg-paper hover:text-ink'
                }`}
              >
                <tab.icon className="w-5 h-5" />
                <span className="text-sm">{tab.name}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="lg:col-span-3 bg-card rounded-xl border border-line shadow-sabi-soft">
          {activeTab === 'general' && (
            <div className="p-6">
              <h2 className="text-lg font-medium mb-6">General Settings</h2>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">Organization Name</label>
                  <input
                    type="text"
                    defaultValue={settings?.orgName || 'Education for Equality'}
                    className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">Default Language</label>
                  <select className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold">
                    <option>English</option>
                    <option>Yoruba</option>
                    <option>Igbo</option>
                    <option>Hausa</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">Time Zone</label>
                  <select className="w-full px-4 py-2 border border-line-strong rounded-lg focus:outline-none focus:ring-2 focus:ring-gold">
                    <option>Africa/Lagos (WAT)</option>
                    <option>UTC</option>
                  </select>
                </div>
                <div className="pt-4">
                  <button className="px-6 py-2 bg-gold text-ink rounded-lg hover:bg-gold-deep hover:text-card transition-colors font-medium">
                    Save Changes
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'auth' && (
            <div className="p-6">
              <h2 className="text-lg font-medium mb-6">Authentication</h2>
              <div className="space-y-6">
                <div className="border-b border-line pb-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="font-medium text-ink">Two-Factor Authentication</h3>
                      <p className="text-sm text-ink-muted">Add an extra layer of security</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input type="checkbox" className="sr-only peer" />
                      <div className="w-11 h-6 bg-line-strong peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-gold rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gold"></div>
                    </label>
                  </div>
                </div>
                <div className="border-b border-line pb-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="font-medium text-ink">Session Timeout</h3>
                      <p className="text-sm text-ink-muted">Auto-logout after inactivity</p>
                    </div>
                    <select className="px-4 py-2 border border-line-strong rounded-lg">
                      <option>30 minutes</option>
                      <option>1 hour</option>
                      <option>4 hours</option>
                      <option>Never</option>
                    </select>
                  </div>
                </div>
                <div>
                  <h3 className="font-medium text-ink mb-3">API Keys</h3>
                  <div className="space-y-2">
                    {settings?.apiKeys?.map((key: any) => (
                      <div key={key.id} className="flex items-center justify-between p-3 border border-line rounded-lg">
                        <div>
                          <div className="font-mono text-sm text-ink">{key.name}</div>
                          <div className="text-xs text-ink-muted">Last used: {key.lastUsed}</div>
                        </div>
                        <button className="text-sm text-bad hover:underline">Revoke</button>
                      </div>
                    ))}
                  </div>
                  <button className="mt-3 text-sm text-gold-deep hover:text-gold">+ Generate New Key</button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'notifications' && (
            <div className="p-6">
              <h2 className="text-lg font-medium mb-6">Notification Preferences</h2>
              <div className="space-y-4">
                {[
                  { name: 'Safeguarding Alerts', description: 'Critical safety issues requiring immediate attention' },
                  { name: 'System Health', description: 'Service outages and performance issues' },
                  { name: 'Daily Summary', description: 'End-of-day operational report' },
                  { name: 'Learning Milestones', description: 'Student achievement notifications' },
                  { name: 'Cost Alerts', description: 'Budget thresholds and unusual spending' },
                ].map((notif) => (
                  <div key={notif.name} className="flex items-start justify-between py-3 border-b border-line last:border-0">
                    <div className="flex-1">
                      <div className="font-medium text-ink">{notif.name}</div>
                      <div className="text-sm text-ink-muted">{notif.description}</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4">
                      <input type="checkbox" className="sr-only peer" defaultChecked />
                      <div className="w-11 h-6 bg-line-strong peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-gold rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gold"></div>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'integrations' && (
            <div className="p-6">
              <h2 className="text-lg font-medium mb-6">Integrations</h2>
              <div className="space-y-4">
                {[
                  { name: 'Supabase', description: 'Student database', status: 'connected' },
                  { name: 'Africa\'s Talking', description: 'SMS & Voice', status: 'connected' },
                  { name: 'Twilio', description: 'Backup telephony', status: 'connected' },
                  { name: 'ElevenLabs', description: 'Text-to-speech', status: 'connected' },
                  { name: 'Anthropic', description: 'LLM (Claude)', status: 'connected' },
                  { name: 'Slack', description: 'Team notifications', status: 'disconnected' },
                ].map((integration) => (
                  <div key={integration.name} className="flex items-center justify-between p-4 border border-line rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${
                        integration.status === 'connected' ? 'bg-green' : 'bg-ink-muted'
                      }`} />
                      <div>
                        <div className="font-medium text-ink">{integration.name}</div>
                        <div className="text-sm text-ink-muted">{integration.description}</div>
                      </div>
                    </div>
                    <button className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      integration.status === 'connected'
                        ? 'border border-line-strong hover:border-bad hover:text-bad'
                        : 'bg-gold text-ink hover:bg-gold-deep hover:text-card'
                    }`}>
                      {integration.status === 'connected' ? 'Disconnect' : 'Connect'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="p-6">
              <h2 className="text-lg font-medium mb-6">Security</h2>
              <div className="space-y-6">
                <div>
                  <h3 className="font-medium text-ink mb-3">Activity Log</h3>
                  <div className="space-y-2">
                    {settings?.activityLog?.slice(0, 5).map((log: any) => (
                      <div key={log.id} className="flex items-center justify-between py-2 border-b border-line">
                        <div>
                          <div className="text-sm text-ink">{log.action}</div>
                          <div className="text-xs text-ink-muted">{log.user} • {log.timestamp}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="font-medium text-ink mb-3">Data Export</h3>
                  <p className="text-sm text-ink-muted mb-3">
                    Export all operational data for backup or compliance
                  </p>
                  <button className="px-4 py-2 border border-line-strong rounded-lg hover:border-gold hover:bg-gold-wash transition-colors">
                    Export Data
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
