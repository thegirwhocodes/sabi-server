import { Outlet, NavLink } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Users, 
  GraduationCap, 
  Phone, 
  DollarSign, 
  UsersRound,
  FlaskConical,
  Server,
  MessageSquare,
  Settings as SettingsIcon
} from 'lucide-react'

const navigation = [
  { name: 'Mission Control', href: '/mission-control', icon: LayoutDashboard },
  { name: 'Students', href: '/students', icon: Users },
  { name: 'Learning Analytics', href: '/learning', icon: GraduationCap },
  { name: 'Call Quality', href: '/calls', icon: Phone },
  { name: 'Finance', href: '/finance', icon: DollarSign },
  { name: 'Team', href: '/team', icon: UsersRound },
  { name: 'Research', href: '/research', icon: FlaskConical },
  { name: 'Infrastructure', href: '/infrastructure', icon: Server },
  { name: 'Communications', href: '/communications', icon: MessageSquare },
  { name: 'Settings', href: '/settings', icon: SettingsIcon },
]

export function Layout() {
  return (
    <div className="flex h-screen bg-paper">
      <aside className="w-64 bg-side border-r border-line-strong flex flex-col">
        <div className="p-6 border-b border-side-soft">
          <h1 className="text-xl font-serif font-semibold text-gold">Sabi Operations</h1>
          <p className="text-xs text-side-text mt-1">Education for Equality</p>
        </div>
        
        <nav className="flex-1 overflow-y-auto py-4 px-3">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 transition-colors ${
                  isActive
                    ? 'bg-gold text-ink font-medium'
                    : 'text-side-text hover:bg-side-soft hover:text-gold'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              <span className="text-sm">{item.name}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-side-soft">
          <div className="text-xs text-side-text">
            <p>System Status: <span className="text-green">Operational</span></p>
            <p className="mt-1">Last Updated: Just now</p>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
