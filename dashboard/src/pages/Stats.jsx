import React, { useState, useEffect } from 'react'
import { fetchStats } from '../api/dashboardApi'
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export default function Stats() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await fetchStats()
        setStats(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadStats()
  }, [])

  if (loading) return <div>Loading KPI Stats...</div>
  if (error) return <div className="error-banner">{error}</div>
  if (!stats) return null

  const pieData = [
    { name: 'Auto-Resolved', value: stats.auto_resolved, color: '#10b981' },
    { name: 'Escalated', value: stats.escalated, color: '#ef4444' }
  ]

  // Filter out any 0 values so they don't show awkwardly in the pie chart
  const activePieData = pieData.filter(d => d.value > 0)

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Platform KPIs</h1>
        <p className="page-subtitle">Aggregate metrics for the Agentic IT L1 Automation Platform</p>
      </div>
      
      {stats.test_traffic_excluded && (
        <div className="info-banner" style={{ backgroundColor: 'var(--surface-color)', padding: '0.75rem', borderRadius: '4px', marginBottom: '1.5rem', borderLeft: '4px solid var(--primary-color)' }}>
          <strong>Note:</strong> Metrics exclude test automation tickets (e.g. TEST-R* and KAN-2* prefixes) to reflect true production traffic accurately.
        </div>
      )}

      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: '200px', backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px' }}>
          <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Total Tickets</h3>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold' }}>{stats.total_tickets}</div>
        </div>
        
        <div style={{ flex: 1, minWidth: '200px', backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px' }}>
          <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Avg Resolution Time</h3>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold' }}>
            {stats.avg_resolution_minutes > 0 ? `${stats.avg_resolution_minutes}m` : '—'}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: '200px', backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px' }}>
          <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Auto-Resolved</h3>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'var(--success-color)' }}>{stats.auto_resolved}</div>
        </div>

        <div style={{ flex: 1, minWidth: '200px', backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px' }}>
          <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Escalated</h3>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'var(--error-color)' }}>{stats.escalated}</div>
        </div>
      </div>

      <div style={{ backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px', height: '400px' }}>
        <h3>Resolution Breakdown</h3>
        {activePieData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={activePieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={5}
                dataKey="value"
                label
              >
                {activePieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            No resolved or escalated tickets yet.
          </div>
        )}
      </div>
    </div>
  )
}
