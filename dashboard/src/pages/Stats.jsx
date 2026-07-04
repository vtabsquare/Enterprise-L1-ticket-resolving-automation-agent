/**
 * Stats.jsx — KPI overview dashboard (home page).
 * Shows: total tickets, auto-resolved %, escalated count, avg resolution time.
 * Full implementation in Phase 6.
 */
import React from 'react'

export default function Stats() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Platform Overview</h1>
        <p className="page-subtitle">Real-time KPIs for the L1 automation pipeline</p>
      </div>
      <div className="card-grid">
        {['Total Tickets', 'Auto-Resolved', 'Escalated', 'Avg Resolution'].map((label) => (
          <div className="stat-card" key={label}>
            <span className="stat-label">{label}</span>
            <span className="stat-value text-muted">—</span>
          </div>
        ))}
      </div>
      <div className="card placeholder">
        <p>Charts and trend data will appear here in Phase 6.</p>
      </div>
    </div>
  )
}
