/**
 * Counselor API Service
 * Maps to backend/app/api/counselor.py
 */

const API_BASE = 'http://localhost:8000';

function getAuthHeaders(token) {
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const api = {
  async login(username, password) {
    const res = await fetch(`${API_BASE}/counselor/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  },

  async setDuty(token, onDuty) {
    const res = await fetch(`${API_BASE}/counselor/me/duty`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ on_duty: onDuty }),
    });
    if (!res.ok) throw new Error('Failed to update duty status');
    return res.json();
  },

  async getEscalations(token, includeClosed = false) {
    const res = await fetch(`${API_BASE}/counselor/escalations?include_closed=${includeClosed}`, {
      headers: getAuthHeaders(token),
    });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    if (!res.ok) throw new Error('Failed to fetch escalations');
    const data = await res.json();
    return Array.isArray(data) ? data : (data.queue || []);
  },

  async getSessionMessages(token, userUuid) {
    const res = await fetch(`${API_BASE}/counselor/sessions/${userUuid}/messages`, {
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch conversation history');
    return res.json();
  },

  async claimEscalation(token, escalationId) {
    const res = await fetch(`${API_BASE}/counselor/escalations/${escalationId}/claim`, {
      method: 'POST',
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to claim escalation');
    return res.json();
  },

  async unclaimEscalation(token, escalationId) {
    const res = await fetch(`${API_BASE}/counselor/escalations/${escalationId}/unclaim`, {
      method: 'POST',
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to unclaim escalation');
    return res.json();
  },

  async setHandover(token, escalationId, mode) {
    const res = await fetch(`${API_BASE}/counselor/escalations/${escalationId}/handover`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) throw new Error('Failed to update handover mode');
    return res.json();
  },

  async sendReply(token, userUuid, text) {
    const res = await fetch(`${API_BASE}/counselor/sessions/${userUuid}/reply`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to send WhatsApp message');
    }
    return res.json();
  },

  async resolveEscalation(token, escalationId, outcome, notes) {
    const res = await fetch(`${API_BASE}/counselor/escalations/${escalationId}/resolve`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ outcome, notes }),
    });
    if (!res.ok) throw new Error('Failed to resolve escalation');
    return res.json();
  },

  async muteEscalation(token, escalationId, outcome, notes) {
    const res = await fetch(`${API_BASE}/counselor/escalations/${escalationId}/mute`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ outcome, notes }),
    });
    if (!res.ok) throw new Error('Failed to mute escalation');
    return res.json();
  },

  async getAuditLogs(token, limit = 100) {
    const res = await fetch(`${API_BASE}/counselor/audit?limit=${limit}`, {
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to load audit logs');
    return res.json();
  },

  async verifyAuditChain(token) {
    const res = await fetch(`${API_BASE}/counselor/audit/verify`, {
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Audit verification failed');
    return res.json();
  },

  async getSLAMetrics(token) {
    const res = await fetch(`${API_BASE}/counselor/metrics/sla`, {
      headers: getAuthHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch SLA metrics');
    return res.json();
  },
};
