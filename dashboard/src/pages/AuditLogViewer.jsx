import React, { useState, useEffect } from 'react'
import { fetchAuditLogs } from '../api/dashboardApi'
import { format } from 'date-fns'
import { Link } from 'react-router-dom'

export default function AuditLogViewer() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const loadLogs = async () => {
      try {
        const data = await fetchAuditLogs()
        setLogs(data.items || [])
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadLogs()
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Audit Log</h1>
        <p className="page-subtitle">Raw, append-only security and compliance trail</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Event</th>
              <th>Agent</th>
              <th>Ticket ID</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5}>Loading...</td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={5}>No audit logs found.</td></tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {format(new Date(log.timestamp), 'MMM dd HH:mm:ss')}
                  </td>
                  <td>
                    <span className="badge badge--default">{log.event_type}</span>
                  </td>
                  <td>{log.agent_name}</td>
                  <td>
                    {log.ticket_id ? (
                      <Link to={`/tickets/${log.ticket_id}`}>View</Link>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <pre style={{ fontSize: '0.85em', margin: 0, maxWidth: '300px', overflowX: 'auto' }}>
                      {JSON.stringify(log.details, null, 2)}
                    </pre>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
