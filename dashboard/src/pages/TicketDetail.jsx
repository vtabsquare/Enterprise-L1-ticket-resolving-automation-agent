import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchTicketDetail } from '../api/dashboardApi'
import { format } from 'date-fns'
import { ArrowLeft } from 'lucide-react'

export default function TicketDetail() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const loadDetail = async () => {
      try {
        const result = await fetchTicketDetail(id)
        setData(result)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadDetail()
  }, [id])

  if (loading) return <div>Loading ticket...</div>
  if (error) return <div className="error-banner">{error}</div>
  if (!data) return <div>Ticket not found</div>

  const { ticket, timeline } = data

  return (
    <div>
      <div className="page-header">
        <Link to="/tickets" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', textDecoration: 'none', color: 'var(--text-secondary)' }}>
          <ArrowLeft size={16} /> Back to Feed
        </Link>
        <h1 className="page-title">{ticket.external_id}: {ticket.summary}</h1>
        <p className="page-subtitle">Source: {ticket.source} | Status: <span className="badge">{ticket.status}</span></p>
      </div>

      <div style={{ backgroundColor: 'var(--surface-color)', padding: '1.5rem', borderRadius: '8px', marginBottom: '2rem' }}>
        <h3>Description</h3>
        <p style={{ whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>{ticket.description}</p>
      </div>

      <h2>Agent Action Timeline</h2>
      <div className="table-wrapper" style={{ marginTop: '1rem' }}>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Type</th>
              <th>Agent / Event</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {timeline.length === 0 ? (
              <tr><td colSpan={4}>No timeline events found.</td></tr>
            ) : (
              timeline.map((item, idx) => (
                <tr key={idx}>
                  <td style={{ whiteSpace: 'nowrap' }}>{format(new Date(item.timestamp), 'MMM dd HH:mm:ss')}</td>
                  <td>
                    <span className={`badge ${item.type === 'agent_action' ? 'badge--mock' : 'badge--default'}`}>
                      {item.type === 'agent_action' ? 'Action' : 'Audit'}
                    </span>
                  </td>
                  <td>
                    <strong>{item.agent_name}</strong><br/>
                    <span style={{ fontSize: '0.85em', color: 'var(--text-secondary)' }}>
                      {item.action_type || item.event_type}
                    </span>
                  </td>
                  <td>
                    <pre style={{ fontSize: '0.85em', background: 'var(--bg-color)', padding: '0.5rem', borderRadius: '4px', overflowX: 'auto', maxWidth: '400px' }}>
                      {JSON.stringify(item.result || item.details, null, 2)}
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
