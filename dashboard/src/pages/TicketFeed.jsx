import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { fetchTickets } from '../api/dashboardApi'
import { format } from 'date-fns'

export default function TicketFeed() {
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')

  useEffect(() => {
    const loadTickets = async () => {
      setLoading(true)
      try {
        const data = await fetchTickets({ status: statusFilter, category: categoryFilter })
        setTickets(data.items || [])
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadTickets()
  }, [statusFilter, categoryFilter])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Ticket Feed</h1>
        <p className="page-subtitle">All ingested tickets — Jira + ServiceNow</p>
      </div>
      
      <div style={{ marginBottom: '1rem', display: 'flex', gap: '1rem' }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="new">New</option>
          <option value="resolved">Resolved</option>
          <option value="escalated">Escalated</option>
        </select>
        <input 
          type="text" 
          placeholder="Filter by Category..." 
          value={categoryFilter} 
          onChange={(e) => setCategoryFilter(e.target.value)} 
        />
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Summary</th>
              <th>Category</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6}>Loading...</td></tr>
            ) : tickets.length === 0 ? (
              <tr><td colSpan={6}>No tickets found.</td></tr>
            ) : (
              tickets.map(ticket => (
                <tr key={ticket.id}>
                  <td>
                    <Link to={`/tickets/${ticket.id}`}>{ticket.external_id}</Link>
                  </td>
                  <td>{ticket.source}</td>
                  <td>{ticket.summary}</td>
                  <td>{ticket.category || '—'}</td>
                  <td>
                    <span className={`badge badge--${ticket.status === 'resolved' ? 'success' : ticket.status === 'escalated' ? 'error' : 'default'}`}>
                      {ticket.status}
                    </span>
                  </td>
                  <td>{format(new Date(ticket.created_at), 'MMM dd HH:mm')}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
