import React, { useState, useEffect } from 'react'
import { fetchEscalations } from '../api/dashboardApi'
import { format } from 'date-fns'
import { Link } from 'react-router-dom'

export default function Escalations() {
  const [escalations, setEscalations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const loadEscalations = async () => {
      try {
        const data = await fetchEscalations()
        setEscalations(data.items || [])
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadEscalations()
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Escalations</h1>
        <p className="page-subtitle">Tickets that required human intervention</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Ticket ID</th>
              <th>Status</th>
              <th>Escalation Reason</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4}>Loading...</td></tr>
            ) : escalations.length === 0 ? (
              <tr><td colSpan={4}>No escalations found.</td></tr>
            ) : (
              escalations.map((esc) => (
                <tr key={esc.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {format(new Date(esc.notified_at), 'MMM dd HH:mm')}
                  </td>
                  <td>
                    <Link to={`/tickets/${esc.ticket_id}`}>View Ticket</Link>
                  </td>
                  <td>
                    <span className="badge badge--error">
                      {esc.tickets?.status || 'escalated'}
                    </span>
                  </td>
                  <td>{esc.reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
