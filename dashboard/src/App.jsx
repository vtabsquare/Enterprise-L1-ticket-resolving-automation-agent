import React from 'react'
import { HashRouter, Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom'
import { LayoutDashboard, Ticket, ShieldCheck, ScrollText, AlertTriangle, BarChart3, LogOut } from 'lucide-react'

import { AuthProvider, useAuth } from './contexts/AuthContext'
import { NotificationProvider } from './contexts/NotificationContext'
import Login from './pages/Login'

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

const ProtectedLayout = () => {
  const { user, signOut } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
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
          <button onClick={signOut} className="nav-item" style={{ width: '100%', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', color: '#fca5a5' }}>
             <LogOut size={18} style={{ marginRight: '8px' }} />
             <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <NotificationProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            {/* Protected Routes wrapped in Layout */}
            <Route element={<ProtectedLayout />}>
              <Route path="/"                 element={<Stats />}           />
              <Route path="/tickets"          element={<TicketFeed />}      />
              <Route path="/tickets/:id"      element={<TicketDetail />}    />
              <Route path="/policy-decisions" element={<PolicyDecisions />} />
              <Route path="/audit"            element={<AuditLogViewer />}  />
              <Route path="/escalations"      element={<Escalations />}     />
            </Route>
          </Routes>
        </NotificationProvider>
      </HashRouter>
    </AuthProvider>
  )
}
