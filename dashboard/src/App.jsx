/**
 * OKOA AI Counselor Dashboard – App.jsx
 *
 * Orchestrates the full dashboard by composing modular components.
 * All API calls are delegated to services/api.js.
 * All WebSocket logic lives in services/websocket.js.
 * All UI atoms live in design-system/.
 * All panel/modal components live in components/escalations/ and components/layout/.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';

// Layout
import Header from './components/layout/Header';
import LoginView from './components/layout/LoginView';

// Escalation panels
import EscalationQueue from './components/escalations/EscalationQueue';
import ConversationPanel from './components/escalations/ConversationPanel';
import TriagePanel from './components/escalations/TriagePanel';

// Modals
import ResolveModal from './components/escalations/ResolveModal';
import AuditModal from './components/escalations/AuditModal';
import TrendsModal from './components/escalations/TrendsModal';

// Services
import { api } from './services/api';
import { createWebSocketClient } from './services/websocket';

// ─────────────────────────────────────────────────────────────────────────────
// App
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  // ── Auth ──────────────────────────────────────────────────────────────────
  const [token, setToken] = useState(() => localStorage.getItem('okoa_token') || '');
  const [counselor, setCounselor] = useState(null);
  const [isOnDuty, setIsOnDuty] = useState(false);

  // ── Queue ─────────────────────────────────────────────────────────────────
  const [escalations, setEscalations] = useState([]);
  const [filter, setFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [activeSession, setActiveSession] = useState(null);

  // ── Reply Composer ────────────────────────────────────────────────────────
  const [replyText, setReplyText] = useState('');
  const [isSendingReply, setIsSendingReply] = useState(false);

  // ── Modal state ───────────────────────────────────────────────────────────
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [showTrendsModal, setShowTrendsModal] = useState(false);

  // ── Audit/Trends data ─────────────────────────────────────────────────────
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditVerify, setAuditVerify] = useState(null);
  const [slaMetrics, setSlaMetrics] = useState(null);

  // ── WebSocket ─────────────────────────────────────────────────────────────
  const [wsStatus, setWsStatus] = useState('disconnected');
  const wsRef = useRef(null);

  // ─────────────────────────────────────────────────────────────────────────
  // Data-fetching helpers
  // ─────────────────────────────────────────────────────────────────────────
  const fetchEscalations = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getEscalations(token);
      setEscalations(data);
    } catch (err) {
      if (err.message === 'UNAUTHORIZED') logout();
    }
  }, [token]);

  const fetchEscalationDetail = useCallback(async (id) => {
    if (!token || !id) return;
    try {
      // Find escalation from queue to get user_uuid
      const esc = escalations.find(e => e.id === id);
      if (!esc) return;
      const msgs = await api.getSessionMessages(token, esc.user_uuid);
      setActiveSession({ ...esc, messages: msgs });
    } catch (err) {
      console.error('Failed to load session detail:', err);
    }
  }, [token, escalations]);

  const fetchAuditData = useCallback(async () => {
    if (!token) return;
    try {
      const [logs, verify] = await Promise.all([
        api.getAuditLogs(token, 25),
        api.verifyAuditChain(token),
      ]);
      setAuditLogs(logs);
      setAuditVerify(verify);
    } catch (err) {
      console.error('Failed to load audit data:', err);
    }
  }, [token]);

  const fetchSlaMetrics = useCallback(async () => {
    if (!token) return;
    try {
      const metrics = await api.getSLAMetrics(token);
      setSlaMetrics(metrics);
    } catch (err) {
      console.error('Failed to load SLA metrics:', err);
    }
  }, [token]);

  // ─────────────────────────────────────────────────────────────────────────
  // Auth / session lifecycle
  // ─────────────────────────────────────────────────────────────────────────
  const logout = () => {
    localStorage.removeItem('okoa_token');
    setToken('');
    setCounselor(null);
    setEscalations([]);
    setActiveSession(null);
    setSelectedId(null);
    wsRef.current?.close();
  };

  // Initial load
  useEffect(() => {
    if (!token) return;
    fetchEscalations();
  }, [token, fetchEscalations]);

  // Polling every 30 s
  useEffect(() => {
    if (!token) return;
    const id = setInterval(fetchEscalations, 30_000);
    return () => clearInterval(id);
  }, [token, fetchEscalations]);

  // WebSocket setup
  useEffect(() => {
    if (!token) return;
    const ws = createWebSocketClient(token, {
      onStatusChange: setWsStatus,
      onEscalation: () => fetchEscalations(),
      onMessage: (msg) => {
        setActiveSession(prev => {
          if (!prev || msg.user_uuid !== prev.user_uuid) return prev;
          return { ...prev, messages: [...(prev.messages || []), msg] };
        });
      },
    });
    wsRef.current = ws;
    return () => ws.close();
  }, [token, fetchEscalations]);

  // ─────────────────────────────────────────────────────────────────────────
  // Queue selection
  // ─────────────────────────────────────────────────────────────────────────
  const handleSelectEscalation = useCallback((esc) => {
    setSelectedId(esc.id);
    setActiveSession(esc); // Optimistic — show data we have immediately
    fetchEscalationDetail(esc.id);
  }, [fetchEscalationDetail]);

  // ─────────────────────────────────────────────────────────────────────────
  // Clinical actions
  // ─────────────────────────────────────────────────────────────────────────
  const handleClaim = async () => {
    if (!selectedId) return;
    try {
      await api.claimEscalation(token, selectedId);
      await fetchEscalations();
      await fetchEscalationDetail(selectedId);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleUnclaim = async () => {
    if (!selectedId) return;
    try {
      await api.unclaimEscalation(token, selectedId);
      await fetchEscalations();
      await fetchEscalationDetail(selectedId);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleToggleHandover = async () => {
    if (!activeSession) return;
    const nextMode = activeSession.handover_mode === 'counselor_active' ? 'bot_active' : 'counselor_active';
    try {
      const updated = await api.setHandover(token, selectedId, nextMode);
      setActiveSession(prev => ({ ...prev, ...updated }));
    } catch (err) {
      alert(err.message);
    }
  };

  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !activeSession) return;
    setIsSendingReply(true);
    try {
      await api.sendReply(token, activeSession.user_uuid, replyText);
      setReplyText('');
      await fetchEscalationDetail(selectedId);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSendingReply(false);
    }
  };

  const handleResolve = async (outcome, notes) => {
    if (!selectedId) return;
    try {
      await api.resolveEscalation(token, selectedId, outcome, notes);
      setShowResolveModal(false);
      await fetchEscalations();
      await fetchEscalationDetail(selectedId);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleMute = async () => {
    if (!selectedId || !confirm('Mute this escalation? It will mark it as false-positive/no-action.')) return;
    try {
      await api.muteEscalation(token, selectedId);
      await fetchEscalations();
      await fetchEscalationDetail(selectedId);
    } catch (err) {
      alert(err.message);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Duty toggle
  // ─────────────────────────────────────────────────────────────────────────
  const handleToggleDuty = async () => {
    try {
      const res = await api.setDuty(token, !isOnDuty);
      setIsOnDuty(res.on_duty ?? !isOnDuty);
    } catch {
      setIsOnDuty(prev => !prev); // Optimistic toggle
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Open modals with data fetch
  // ─────────────────────────────────────────────────────────────────────────
  const handleOpenAudit = () => {
    setShowAuditModal(true);
    fetchAuditData();
  };

  const handleOpenTrends = () => {
    setShowTrendsModal(true);
    fetchSlaMetrics();
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Derived stats
  // ─────────────────────────────────────────────────────────────────────────
  const criticalCount = escalations.filter(e => e.risk_label === 'crisis' && e.status === 'open').length;

  // ─────────────────────────────────────────────────────────────────────────
  // Login screen
  // ─────────────────────────────────────────────────────────────────────────
  if (!token) {
    return (
      <LoginView
        onLoginSuccess={(accessToken, counselorObj) => {
          localStorage.setItem('okoa_token', accessToken);
          setToken(accessToken);
          setCounselor(counselorObj);
          setIsOnDuty(counselorObj?.on_duty ?? false);
        }}
      />
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Main dashboard
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden', fontFamily: "'Inter', sans-serif" }}>
      <Header
        counselor={counselor}
        isOnDuty={isOnDuty}
        onToggleDuty={handleToggleDuty}
        wsStatus={wsStatus}
        criticalCount={criticalCount}
        onOpenAudit={handleOpenAudit}
        onOpenTrends={handleOpenTrends}
        onOpenMobilePreview={() => {/* TODO: mobile preview modal */}}
        onLogout={logout}
      />

      {/* Three-panel layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <EscalationQueue
          escalations={escalations}
          selectedId={selectedId}
          filter={filter}
          onFilterChange={setFilter}
          onSelect={handleSelectEscalation}
        />

        <ConversationPanel
          session={activeSession}
          replyText={replyText}
          isSendingReply={isSendingReply}
          onReplyChange={setReplyText}
          onSendReply={handleSendReply}
          onToggleHandover={handleToggleHandover}
        />

        <TriagePanel
          session={activeSession}
          onClaim={handleClaim}
          onUnclaim={handleUnclaim}
          onResolve={() => setShowResolveModal(true)}
          onMute={handleMute}
        />
      </div>

      {/* Modals */}
      <ResolveModal
        isOpen={showResolveModal}
        onClose={() => setShowResolveModal(false)}
        onConfirm={handleResolve}
      />

      <AuditModal
        isOpen={showAuditModal}
        onClose={() => setShowAuditModal(false)}
        auditLogs={auditLogs}
        auditVerify={auditVerify}
      />

      <TrendsModal
        isOpen={showTrendsModal}
        onClose={() => setShowTrendsModal(false)}
        slaMetrics={slaMetrics}
      />
    </div>
  );
}
