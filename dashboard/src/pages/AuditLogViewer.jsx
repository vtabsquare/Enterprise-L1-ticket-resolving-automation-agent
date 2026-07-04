/**
 * AuditLogViewer.jsx — Immutable audit log browser.
 * Filterable by ticket ID, event type, and date range.
 * Full implementation in Phase 6.
 */
import React from 'react'

export default function AuditLogViewer() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Audit Log</h1>
        <p className="page-subtitle">Immutable record of every automated decision and action</p>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Ticket</th>
              <th>Agent</th>
              <th>Event Type</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={5}>
                <div className="placeholder">
                  <p>Audit log entries will appear here in Phase 6.</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
