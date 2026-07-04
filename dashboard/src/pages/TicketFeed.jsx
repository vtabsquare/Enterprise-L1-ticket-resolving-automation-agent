/**
 * TicketFeed.jsx — Live ticket feed with status, priority, and category.
 * Polls /api/dashboard/tickets every VITE_POLL_INTERVAL_MS milliseconds.
 * Full implementation in Phase 6.
 */
import React from 'react'

export default function TicketFeed() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Ticket Feed</h1>
        <p className="page-subtitle">All ingested tickets — Jira + ServiceNow (mock)</p>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Summary</th>
              <th>Category</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={7}>
                <div className="placeholder">
                  <p>Ticket data will appear here in Phase 6.</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
