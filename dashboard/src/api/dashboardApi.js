/**
 * dashboardApi.js — Centralised API client for the L1 Dashboard.
 *
 * All API calls go through this module — no component ever calls fetch() directly.
 * Uses Axios with a base URL from VITE_API_BASE_URL env var.
 *
 * All endpoints are READ-ONLY (GET requests only).
 * The dashboard has no write access to the backend.
 *
 * Full implementation in Phase 6.
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const api = axios.create({
  baseURL: `${BASE_URL}/api/dashboard`,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

import { supabase } from '../lib/supabase'

// ── Request interceptor — attach auth token if present ────────────────────────
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  const token = data?.session?.access_token
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — normalise errors ────────────────────────────────────
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'Unknown error'
    console.error('[DashboardAPI]', message)
    return Promise.reject(new Error(message))
  }
)

// ── Ticket Feed ────────────────────────────────────────────────────────────────

/**
 * Fetch recent tickets for the live feed.
 * @param {Object} params - { page, page_size, status, source }
 */
export const fetchTickets = (params = {}) =>
  api.get('/tickets', { params })

/**
 * Fetch a single ticket with full agent action timeline.
 * @param {string} ticketId - Internal UUID
 */
export const fetchTicketDetail = (ticketId) =>
  api.get(`/tickets/${ticketId}`)

// ── Audit Log ──────────────────────────────────────────────────────────────────

/**
 * Fetch paginated audit log entries.
 * @param {Object} params - { ticket_id, page, page_size }
 */
export const fetchAuditLogs = (params = {}) =>
  api.get('/audit', { params })

// ── Escalations ────────────────────────────────────────────────────────────────

/**
 * Fetch open escalations.
 */
export const fetchEscalations = () =>
  api.get('/escalations')

// ── Stats / KPIs ───────────────────────────────────────────────────────────────

/**
 * Fetch aggregate KPI stats for the stats panel.
 */
export const fetchStats = () =>
  api.get('/stats')

// ── Policy Decisions ───────────────────────────────────────────────────────────

/**
 * Fetch recent policy check results.
 * @param {Object} params - { page, page_size }
 */
export const fetchPolicyDecisions = (params = {}) =>
  api.get('/policy-decisions', { params })

export default api
