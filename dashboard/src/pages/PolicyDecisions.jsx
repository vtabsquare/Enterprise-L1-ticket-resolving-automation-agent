/**
 * PolicyDecisions.jsx — Shows recent policy engine decisions.
 * Columns: ticket, action type, risk level, decision (approved/blocked), reason.
 * Full implementation in Phase 6.
 */
import React from 'react'

export default function PolicyDecisions() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Policy Decisions</h1>
        <p className="page-subtitle">Every policy check result — approved and blocked actions</p>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Action Type</th>
              <th>Risk Level</th>
              <th>Decision</th>
              <th>Reason</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={6}>
                <div className="placeholder">
                  <p>Policy decisions will appear here in Phase 6.</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
