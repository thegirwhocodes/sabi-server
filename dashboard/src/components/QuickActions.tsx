import { Phone, Users, FileText, Settings } from 'lucide-react'

export function QuickActions() {
  const actions = [
    { name: 'Review Recent Calls', icon: Phone, href: '/calls' },
    { name: 'View Active Students', icon: Users, href: '/students' },
    { name: 'Generate Report', icon: FileText, href: '/research' },
    { name: 'System Configuration', icon: Settings, href: '/settings' },
  ]

  return (
    <div className="bg-card rounded-xl border border-line p-6 shadow-sabi-soft">
      <h2 className="text-lg font-medium mb-4">Quick Actions</h2>
      <div className="grid grid-cols-2 gap-3">
        {actions.map((action) => (
          <a
            key={action.name}
            href={action.href}
            className="flex flex-col items-center justify-center gap-2 p-4 rounded-lg border border-line-strong hover:border-gold hover:bg-gold-wash transition-colors"
          >
            <action.icon className="w-6 h-6 text-gold-deep" />
            <span className="text-xs text-center text-ink">{action.name}</span>
          </a>
        ))}
      </div>
    </div>
  )
}
