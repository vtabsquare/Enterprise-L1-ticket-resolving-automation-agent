import React from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Ticket, ShieldCheck, ScrollText, AlertTriangle, BarChart3 } from 'lucide-react'

import TicketFeed       from './pages/TicketFeed.jsx'
import TicketDetail     from './pages/TicketDetail.jsx'
import PolicyDecisions  from './pages/PolicyDecisions.jsx'
import AuditLogViewer   from './pages/AuditLogViewer.jsx'
import Escalations      from './pages/Escalations.jsx'
import Stats            from './pages/Stats.jsx'

const NAV_ITEMS = [
  { to: '/',                  label: 'Stats',            Icon: BarChart3       },
  { to: '/tickets',           label: 'Ticket Feed',      Icon: Ticket          },
  { to: '/policy-decisions',  label: 'Policy Decisions', Icon: ShieldCheck     },
  { to: '/audit',             label: 'Audit Log',        Icon: ScrollText      },
  { to: '/escalations',       label: 'Escalations',      Icon: AlertTriangle   },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        {/* ── Sidebar ─────────────────────────────────────────────────── */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <LayoutDashboard size={22} />
            <span>L1 Platform</span>
          </div>
          <nav className="sidebar-nav">
            {NAV_ITEMS.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'nav-item--active' : ''}`
                }
              >
                <Icon size={18} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-footer">
            <span className="badge badge--mock">ServiceNow: MOCK</span>
          </div>
        </aside>

        {/* ── Main content ─────────────────────────────────────────────── */}
        <main className="main-content">
          <Routes>
            <Route path="/"                 element={<Stats />}           />
            <Route path="/tickets"          element={<TicketFeed />}      />
            <Route path="/tickets/:id"      element={<TicketDetail />}    />
            <Route path="/policy-decisions" element={<PolicyDecisions />} />
            <Route path="/audit"            element={<AuditLogViewer />}  />
            <Route path="/escalations"      element={<Escalations />}     />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
