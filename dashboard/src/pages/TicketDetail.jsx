/**
 * TicketDetail.jsx — Full ticket detail with agent action timeline.
 * Shows: ticket metadata, classification result, KB articles used,
 *        resolution plan, policy decisions, executed actions, audit trail.
 * Full implementation in Phase 6.
 */
import React from 'react'
import { useParams } from 'react-router-dom'

export default function TicketDetail() {
  const { id } = useParams()
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Ticket Detail</h1>
        <p className="page-subtitle mono">{id}</p>
      </div>
      <div className="card placeholder">
        <p>Full ticket detail and agent timeline will appear here in Phase 6.</p>
      </div>
    </div>
  )
}
