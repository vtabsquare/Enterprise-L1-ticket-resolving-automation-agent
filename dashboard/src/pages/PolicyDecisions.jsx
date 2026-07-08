import React, { useState, useEffect } from 'react'
import { fetchPolicyDecisions } from '../api/dashboardApi'
import { format } from 'date-fns'
import { Link } from 'react-router-dom'

export default function PolicyDecisions() {
  const [decisions, setDecisions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const loadDecisions = async () => {
      try {
        const data = await fetchPolicyDecisions()
        setDecisions(data.items || [])
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadDecisions()
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Policy Decisions</h1>
        <p className="page-subtitle">Recent automated approvals and blocks</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Ticket ID</th>
              <th>Outcome</th>
              <th>Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4}>Loading...</td></tr>
            ) : decisions.length === 0 ? (
              <tr><td colSpan={4}>No policy decisions found.</td></tr>
            ) : (
              decisions.map((decision) => {
                const outcome = decision.details?.outcome || 'unknown'
                return (
                  <tr key={decision.id}>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {format(new Date(decision.timestamp), 'MMM dd HH:mm')}
                    </td>
                    <td>
                      <Link to={`/tickets/${decision.ticket_id}`}>View Ticket</Link>
                    </td>
                    <td>
                      <span className={`badge badge--${outcome === 'approved' ? 'success' : outcome === 'escalated' ? 'error' : 'default'}`}>
                        {outcome}
                      </span>
                    </td>
                    <td style={{ maxWidth: '400px' }}>
                      {decision.details?.reason || '—'}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
