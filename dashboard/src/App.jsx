import React, { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000';

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('okoa_token') || '');
  const [counselor, setCounselor] = useState(() => {
    const saved = localStorage.getItem('okoa_counselor');
    return saved ? JSON.parse(saved) : null;
  });

  // Auth Inputs
  const [username, setUsername] = useState('dr_ochieng');
  const [password, setPassword] = useState('Password123!');
  const [loginError, setLoginError] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  // Dashboard Data
  const [escalations, setEscalations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [filter, setFilter] = useState('all');
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [replyText, setReplyText] = useState('');
  const [isSendingReply, setIsSendingReply] = useState(false);

  // Modals
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditVerify, setAuditVerify] = useState(null);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [resolveOutcome, setResolveOutcome] = useState('helpline_confirmed');
  const [resolveNotes, setResolveNotes] = useState('');

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages]);

  // Load escalations
  const fetchEscalations = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.status === 401) {
        logout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        setEscalations(data);
        if (data.length > 0 && !selectedId) {
          setSelectedId(data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch escalations:', err);
    }
  };

  // Load active escalation detail
  const fetchEscalationDetail = async (id) => {
    if (!token || !id) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveSession(data);
      }
    } catch (err) {
      console.error('Failed to fetch escalation detail:', err);
    }
  };

  useEffect(() => {
    if (token) {
      fetchEscalations();
      const interval = setInterval(fetchEscalations, 10000);
      return () => clearInterval(interval);
    }
  }, [token]);

  useEffect(() => {
    if (selectedId && token) {
      fetchEscalationDetail(selectedId);
    }
  }, [selectedId, token]);

  // WebSocket Connection
  useEffect(() => {
    if (!token) return;

    let ws = null;
    let reconnectTimeout = null;

    const connectWs = () => {
      setWsStatus('connecting');
      ws = new WebSocket(`${WS_BASE}/ws/counselor?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus('connected');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'escalation_created' || msg.type === 'escalation_updated') {
            fetchEscalations();
            if (selectedId === msg.payload?.id) {
              fetchEscalationDetail(selectedId);
            }
          }
        } catch (e) {
          // heartbeat ping
        }
      };

      ws.onclose = () => {
        setWsStatus('disconnected');
        reconnectTimeout = setTimeout(connectWs, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connectWs();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [token, selectedId]);

  // Actions
  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoggingIn(true);
    setLoginError('');
    try {
      const res = await fetch(`${API_BASE}/counselor/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        setCounselor({ username, displayName: data.display_name });
        localStorage.setItem('okoa_token', data.access_token);
        localStorage.setItem('okoa_counselor', JSON.stringify({ username, displayName: data.display_name }));
      } else {
        const err = await res.json();
        setLoginError(err.detail || 'Invalid counselor credentials');
      }
    } catch (err) {
      setLoginError('Cannot connect to OKOA backend server at ' + API_BASE);
    } finally {
      setIsLoggingIn(false);
    }
  };

  const logout = () => {
    setToken('');
    setCounselor(null);
    setSelectedId(null);
    setActiveSession(null);
    localStorage.removeItem('okoa_token');
    localStorage.removeItem('okoa_counselor');
  };

  const handleClaim = async () => {
    if (!selectedId) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${selectedId}/claim`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        fetchEscalations();
        fetchEscalationDetail(selectedId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleUnclaim = async () => {
    if (!selectedId) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${selectedId}/unclaim`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        fetchEscalations();
        fetchEscalationDetail(selectedId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleHandover = async () => {
    if (!activeSession) return;
    const currentMode = activeSession.handover_mode;
    const targetMode = currentMode === 'counselor_active' ? 'bot_active' : 'counselor_active';
    try {
      const res = await fetch(`${API_BASE}/counselor/handover/${activeSession.user_uuid}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ mode: targetMode, escalation_id: selectedId })
      });
      if (res.ok) {
        fetchEscalationDetail(selectedId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedId) return;
    setIsSendingReply(true);
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${selectedId}/reply`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ body: replyText.trim() })
      });
      if (res.ok) {
        setReplyText('');
        fetchEscalationDetail(selectedId);
      } else {
        const err = await res.json();
        alert('Reply failed: ' + (err.detail || 'Ensure handover mode is active.'));
      }
    } catch (err) {
      alert('Network error sending message');
    } finally {
      setIsSendingReply(false);
    }
  };

  const handleResolve = async () => {
    if (!selectedId) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${selectedId}/resolve`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ outcome: resolveOutcome, notes: resolveNotes })
      });
      if (res.ok) {
        setShowResolveModal(false);
        setResolveNotes('');
        fetchEscalations();
        fetchEscalationDetail(selectedId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleMute = async () => {
    if (!selectedId) return;
    if (!confirm('Mute this escalation? It will mark it as false-positive/no-action.')) return;
    try {
      const res = await fetch(`${API_BASE}/counselor/escalations/${selectedId}/mute`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        fetchEscalations();
        fetchEscalationDetail(selectedId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const loadAuditLogs = async () => {
    setShowAuditModal(true);
    try {
      const res = await fetch(`${API_BASE}/counselor/audit?limit=25`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setAuditLogs(await res.json());
      }
      const verifyRes = await fetch(`${API_BASE}/counselor/audit/verify`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (verifyRes.ok) {
        setAuditVerify(await verifyRes.json());
      }
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    }
  };

  // Filtered Escalations
  const filteredEscalations = escalations.filter((item) => {
    if (filter === 'all') return true;
    if (filter === 'open') return item.status === 'open';
    if (filter === 'claimed') return item.status === 'claimed' || item.status === 'handed_over';
    if (filter === 'resolved') return item.status === 'resolved' || item.status === 'muted';
    return true;
  });

  const criticalCount = escalations.filter(e => e.risk_label === 'crisis' && e.status === 'open').length;
  const openCount = escalations.filter(e => e.status === 'open').length;

  // -------------------------------------------------------------
  // LOGIN SCREEN
  // -------------------------------------------------------------
  if (!token) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#F4F7F5',
        padding: '20px'
      }}>
        <div style={{
          width: '100%',
          maxWidth: '420px',
          backgroundColor: '#FFFFFF',
          borderRadius: '16px',
          boxShadow: '0 20px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.03)',
          border: '1px solid #E5E9E7',
          padding: '36px 32px'
        }}>
          <div style={{ textAlign: 'center', marginBottom: '28px' }}>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '56px',
              height: '56px',
              borderRadius: '14px',
              backgroundColor: '#EBF3EE',
              color: '#2F6B4F',
              fontSize: '28px',
              marginBottom: '14px'
            }}>🌱</div>
            <h1 style={{ fontSize: '1.45rem', fontWeight: '700', color: '#1B4332' }}>OKOA AI Counselor Portal</h1>
            <p style={{ fontSize: '0.875rem', color: '#6B7280', marginTop: '4px' }}>
              Clinical Triage & Real-Time Escalation Dashboard
            </p>
          </div>

          {loginError && (
            <div style={{
              padding: '10px 14px',
              borderRadius: '8px',
              backgroundColor: '#FDF2F2',
              border: '1px solid #F5B7B1',
              color: '#962D22',
              fontSize: '0.85rem',
              marginBottom: '20px'
            }}>
              {loginError}
            </div>
          )}

          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: '18px' }}>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                Counselor Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  border: '1px solid #D1D5DB',
                  outline: 'none'
                }}
              />
            </div>

            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  border: '1px solid #D1D5DB',
                  outline: 'none'
                }}
              />
            </div>

            <button
              type="submit"
              disabled={isLoggingIn}
              style={{
                width: '100%',
                padding: '11px',
                backgroundColor: '#2F6B4F',
                color: '#FFFFFF',
                borderRadius: '8px',
                fontWeight: '600',
                fontSize: '0.95rem',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
              }}
            >
              {isLoggingIn ? 'Authenticating...' : 'Sign In to Dashboard'}
            </button>
          </form>

          <div style={{
            marginTop: '24px',
            paddingTop: '18px',
            borderTop: '1px solid #F3F4F6',
            textAlign: 'center',
            fontSize: '0.8rem',
            color: '#6B7280'
          }}>
            Default seed credentials:<br />
            <strong className="mono">dr_ochieng</strong> / <strong className="mono">Password123!</strong>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------
  // MAIN DASHBOARD LAYOUT
  // -------------------------------------------------------------
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top Navbar */}
      <header style={{
        height: '60px',
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E5E9E7',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        flexShrink: 0
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <span style={{ fontSize: '22px' }}>🌱</span>
          <div>
            <span style={{ fontWeight: '700', color: '#1B4332', fontSize: '1.05rem' }}>OKOA AI</span>
            <span style={{ marginLeft: '8px', fontSize: '0.8rem', color: '#6B7280', fontWeight: '500' }}>
              Counselor Triage Workspace
            </span>
          </div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            marginLeft: '16px',
            padding: '4px 10px',
            borderRadius: '9999px',
            backgroundColor: wsStatus === 'connected' ? '#ECFDF5' : '#F3F4F6',
            fontSize: '0.75rem',
            color: wsStatus === 'connected' ? '#065F46' : '#6B7280'
          }}>
            <span className={`live-indicator-dot ${wsStatus !== 'connected' ? 'offline' : ''}`} />
            {wsStatus === 'connected' ? 'Live Stream Active' : 'Connecting...'}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {criticalCount > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#FDF2F2',
              color: '#962D22',
              border: '1px solid #F5B7B1',
              padding: '4px 10px',
              borderRadius: '9999px',
              fontSize: '0.78rem',
              fontWeight: '700'
            }} className="pulse-critical">
              <span>🚨</span>
              <span>{criticalCount} Critical Action Required</span>
            </div>
          )}

          <button
            onClick={loadAuditLogs}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: '#F3F4F6',
              color: '#374151',
              fontSize: '0.825rem',
              fontWeight: '600'
            }}
          >
            🛡️ Audit Chain
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderLeft: '1px solid #E5E7EB', paddingLeft: '16px' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              backgroundColor: '#EBF3EE',
              color: '#2F6B4F',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: '700',
              fontSize: '0.85rem'
            }}>
              {counselor?.displayName?.charAt(0) || 'D'}
            </div>
            <div>
              <div style={{ fontSize: '0.825rem', fontWeight: '600', color: '#1F2937' }}>
                {counselor?.displayName || counselor?.username}
              </div>
              <div style={{ fontSize: '0.7rem', color: '#059669', fontWeight: '500' }}>● On Duty</div>
            </div>
            <button
              onClick={logout}
              title="Sign Out"
              style={{
                marginLeft: '8px',
                padding: '4px 8px',
                color: '#6B7280',
                fontSize: '0.8rem'
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: Escalations Queue Panel */}
        <div style={{
          width: '360px',
          borderRight: '1px solid #E5E9E7',
          backgroundColor: '#FFFFFF',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0
        }}>
          {/* Queue Filter Bar */}
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #F3F4F6' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <span style={{ fontWeight: '700', fontSize: '0.9rem', color: '#1F2937' }}>Escalation Queue</span>
              <span style={{ fontSize: '0.75rem', fontWeight: '600', color: '#6B7280' }}>
                {openCount} Open
              </span>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['all', 'open', 'claimed', 'resolved'].map((t) => (
                <button
                  key={t}
                  onClick={() => setFilter(t)}
                  style={{
                    flex: 1,
                    padding: '5px 0',
                    fontSize: '0.75rem',
                    fontWeight: filter === t ? '700' : '500',
                    borderRadius: '6px',
                    backgroundColor: filter === t ? '#EBF3EE' : '#F9FAFB',
                    color: filter === t ? '#2F6B4F' : '#6B7280',
                    textTransform: 'capitalize'
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Queue List */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filteredEscalations.length === 0 ? (
              <div style={{ padding: '36px 16px', textAlign: 'center', color: '#9CA3AF', fontSize: '0.85rem' }}>
                No escalations found in this view.
              </div>
            ) : (
              filteredEscalations.map((esc) => {
                const isSelected = esc.id === selectedId;
                const isCrisis = esc.risk_label === 'crisis';
                const createdTime = new Date(esc.created_at);
                const ageMinutes = Math.floor((Date.now() - createdTime.getTime()) / 60000);

                return (
                  <div
                    key={esc.id}
                    onClick={() => setSelectedId(esc.id)}
                    style={{
                      padding: '14px 16px',
                      borderBottom: '1px solid #F3F4F6',
                      borderLeft: isSelected ? '4px solid #2F6B4F' : '4px solid transparent',
                      backgroundColor: isSelected ? '#F9FBFA' : '#FFFFFF',
                      cursor: 'pointer',
                      transition: 'all 0.1s ease'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span className="mono" style={{ fontSize: '0.78rem', fontWeight: '600', color: '#4B5563' }}>
                        usr_{esc.user_uuid?.slice(0, 8)}
                      </span>
                      <span className={`badge badge-${esc.status}`}>
                        {esc.status}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <span className={`badge badge-${esc.risk_label}`}>
                        {esc.risk_label} {Math.round(esc.risk_score)}%
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#6B7280' }}>
                        {ageMinutes === 0 ? 'just now' : `${ageMinutes}m ago`}
                      </span>
                    </div>

                    {/* Risk progress bar */}
                    <div style={{
                      height: '4px',
                      borderRadius: '2px',
                      backgroundColor: '#E5E7EB',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        width: `${Math.min(100, esc.risk_score)}%`,
                        height: '100%',
                        backgroundColor: isCrisis ? '#C0392B' : esc.risk_score > 45 ? '#D97706' : '#10B981'
                      }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Center: Live Chat & Handover Workspace */}
        {activeSession ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#F9FAFB' }}>
            {/* Session Header */}
            <div style={{
              padding: '12px 20px',
              backgroundColor: '#FFFFFF',
              borderBottom: '1px solid #E5E9E7',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontWeight: '700', fontSize: '1rem', color: '#111827' }}>
                    User Session: <span className="mono" style={{ color: '#2F6B4F' }}>{activeSession.user_uuid}</span>
                  </span>
                  <span className={`badge badge-${activeSession.risk_label}`}>
                    {activeSession.risk_label} ({Math.round(activeSession.risk_score)}%)
                  </span>
                </div>
                <div style={{ fontSize: '0.75rem', color: '#6B7280', marginTop: '2px' }}>
                  Anonymous WhatsApp User · Zero PII Mode Active (Kenya DPA 2019 Compliant)
                </div>
              </div>

              {/* Handover Toggle Button */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: '600', color: '#6B7280', textTransform: 'uppercase' }}>
                    Agent Mode
                  </div>
                  <div style={{ fontSize: '0.825rem', fontWeight: '700', color: activeSession.handover_mode === 'counselor_active' ? '#B45309' : '#059669' }}>
                    {activeSession.handover_mode === 'counselor_active' ? 'Human Active (Bot Paused)' : 'Automated Bot Active'}
                  </div>
                </div>

                <button
                  onClick={handleToggleHandover}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '8px',
                    fontWeight: '600',
                    fontSize: '0.825rem',
                    backgroundColor: activeSession.handover_mode === 'counselor_active' ? '#FEF3C7' : '#2F6B4F',
                    color: activeSession.handover_mode === 'counselor_active' ? '#92400E' : '#FFFFFF',
                    border: activeSession.handover_mode === 'counselor_active' ? '1px solid #FCD34D' : 'none'
                  }}
                >
                  {activeSession.handover_mode === 'counselor_active' ? '▶ Resume Bot' : '⏸ Pause & Take Over'}
                </button>
              </div>
            </div>

            {/* Handover Active Banner */}
            {activeSession.handover_mode === 'counselor_active' && (
              <div style={{
                padding: '8px 20px',
                backgroundColor: '#FFFBEB',
                borderBottom: '1px solid #FDE68A',
                color: '#92400E',
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <span>⚠️</span>
                <span>
                  <strong>Handover Active:</strong> Automated AI responses are paused. Your messages below will be dispatched straight to the user via WhatsApp Cloud API.
                </span>
              </div>
            )}

            {/* Chat Transcript Area */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
              {activeSession.messages?.map((msg) => {
                const isInbound = msg.direction === 'inbound';
                const isCrisisPrompt = msg.kind === 'crisis_response';
                const time = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                return (
                  <div
                    key={msg.id}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: isInbound ? 'flex-start' : 'flex-end',
                      marginBottom: '16px'
                    }}
                  >
                    <div style={{
                      maxWidth: '75%',
                      padding: '12px 16px',
                      borderRadius: isInbound ? '14px 14px 14px 2px' : '14px 14px 2px 14px',
                      backgroundColor: isInbound
                        ? '#FFFFFF'
                        : isCrisisPrompt
                        ? '#FDF2F2'
                        : '#EBF3EE',
                      color: isCrisisPrompt ? '#962D22' : '#1F2937',
                      border: isCrisisPrompt ? '1px solid #F5B7B1' : '1px solid #E5E7EB',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.03)'
                    }}>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '12px',
                        marginBottom: '4px',
                        fontSize: '0.72rem',
                        fontWeight: '700',
                        color: isInbound ? '#6B7280' : isCrisisPrompt ? '#C0392B' : '#2F6B4F'
                      }}>
                        <span>{isInbound ? 'WhatsApp User' : isCrisisPrompt ? '🚨 Crisis System Intercept (1199)' : 'OKOA AI / Counselor'}</span>
                        <span style={{ fontWeight: '400', color: '#9CA3AF' }}>{time}</span>
                      </div>
                      <div style={{ fontSize: '0.9rem', whiteSpace: 'pre-wrap', lineHeight: '1.45' }}>
                        {msg.body}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Direct Reply Composer */}
            <div style={{
              padding: '16px 20px',
              backgroundColor: '#FFFFFF',
              borderTop: '1px solid #E5E9E7'
            }}>
              <form onSubmit={handleSendReply} style={{ display: 'flex', gap: '10px' }}>
                <input
                  type="text"
                  placeholder={
                    activeSession.handover_mode === 'counselor_active'
                      ? 'Type direct reply to user in WhatsApp...'
                      : 'Switch to Handover mode above to reply directly...'
                  }
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  disabled={activeSession.handover_mode !== 'counselor_active' || isSendingReply}
                  style={{
                    flex: 1,
                    padding: '11px 16px',
                    borderRadius: '8px',
                    border: '1px solid #D1D5DB',
                    outline: 'none',
                    backgroundColor: activeSession.handover_mode === 'counselor_active' ? '#FFFFFF' : '#F9FAFB'
                  }}
                />
                <button
                  type="submit"
                  disabled={activeSession.handover_mode !== 'counselor_active' || !replyText.trim() || isSendingReply}
                  style={{
                    padding: '0 20px',
                    borderRadius: '8px',
                    backgroundColor: activeSession.handover_mode === 'counselor_active' ? '#2F6B4F' : '#9CA3AF',
                    color: '#FFFFFF',
                    fontWeight: '600',
                    fontSize: '0.875rem'
                  }}
                >
                  {isSendingReply ? 'Sending...' : 'Send to WhatsApp'}
                </button>
              </form>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9CA3AF' }}>
            Select an escalation from the queue to view session details.
          </div>
        )}

        {/* Right: Clinical Triage & Actions Panel */}
        {activeSession && (
          <div style={{
            width: '320px',
            backgroundColor: '#FFFFFF',
            borderLeft: '1px solid #E5E9E7',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
            overflowY: 'auto'
          }}>
            <div>
              <h3 style={{ fontSize: '0.875rem', fontWeight: '700', color: '#1F2937', marginBottom: '12px' }}>
                Clinical Triage Summary
              </h3>
              <div style={{
                padding: '12px',
                borderRadius: '8px',
                backgroundColor: '#F9FAFB',
                border: '1px solid #E5E7EB',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                fontSize: '0.8rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6B7280' }}>Risk Classification:</span>
                  <span className={`badge badge-${activeSession.risk_label}`}>
                    {activeSession.risk_label}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6B7280' }}>Calculated Risk Score:</span>
                  <span style={{ fontWeight: '700', color: '#111827' }}>{activeSession.risk_score} / 100</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6B7280' }}>SLA Target:</span>
                  <span style={{ fontWeight: '600', color: '#059669' }}>&lt; 120 seconds</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6B7280' }}>Status:</span>
                  <span style={{ fontWeight: '600' }}>{activeSession.status}</span>
                </div>
                {activeSession.claimed_by && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#6B7280' }}>Assigned Counselor:</span>
                    <span style={{ fontWeight: '600' }}>Dr. Ochieng</span>
                  </div>
                )}
              </div>
            </div>

            {/* Clinical Actions */}
            <div>
              <h3 style={{ fontSize: '0.875rem', fontWeight: '700', color: '#1F2937', marginBottom: '12px' }}>
                Clinical Actions
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {activeSession.status === 'open' ? (
                  <button
                    onClick={handleClaim}
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '8px',
                      backgroundColor: '#2F6B4F',
                      color: '#FFFFFF',
                      fontWeight: '600',
                      fontSize: '0.825rem'
                    }}
                  >
                    Claim Session Ownership
                  </button>
                ) : (
                  <button
                    onClick={handleUnclaim}
                    style={{
                      width: '100%',
                      padding: '9px',
                      borderRadius: '8px',
                      backgroundColor: '#F3F4F6',
                      color: '#4B5563',
                      fontWeight: '600',
                      fontSize: '0.825rem'
                    }}
                  >
                    Release / Unclaim
                  </button>
                )}

                <button
                  onClick={() => setShowResolveModal(true)}
                  style={{
                    width: '100%',
                    padding: '9px',
                    borderRadius: '8px',
                    backgroundColor: '#ECFDF5',
                    color: '#065F46',
                    border: '1px solid #A7F3D0',
                    fontWeight: '600',
                    fontSize: '0.825rem'
                  }}
                >
                  ✓ Resolve Escalation
                </button>

                <button
                  onClick={handleMute}
                  style={{
                    width: '100%',
                    padding: '9px',
                    borderRadius: '8px',
                    backgroundColor: '#FFFFFF',
                    color: '#6B7280',
                    border: '1px solid #D1D5DB',
                    fontWeight: '600',
                    fontSize: '0.825rem'
                  }}
                >
                  Mute / False Positive
                </button>
              </div>
            </div>

            {/* Helpline Notice */}
            <div style={{
              marginTop: 'auto',
              padding: '12px',
              borderRadius: '8px',
              backgroundColor: '#FDF2F2',
              border: '1px solid #F5B7B1',
              fontSize: '0.78rem',
              color: '#962D22'
            }}>
              <strong>Emergency Routing:</strong> Kenya Red Cross toll-free line <strong>1199</strong> is automatically pushed to all users triggering risk &gt; 85%.
            </div>
          </div>
        )}
      </div>

      {/* RESOLVE MODAL */}
      {showResolveModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            width: '100%',
            maxWidth: '460px',
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
          }}>
            <h2 style={{ fontSize: '1.15rem', fontWeight: '700', marginBottom: '14px', color: '#1B4332' }}>
              Resolve Escalation
            </h2>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                Clinical Outcome
              </label>
              <select
                value={resolveOutcome}
                onChange={(e) => setResolveOutcome(e.target.value)}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #D1D5DB' }}
              >
                <option value="helpline_confirmed">Helpline Confirmed (1199 routing verified)</option>
                <option value="counselor_contacted">Counselor Contacted Directly</option>
                <option value="false_positive">False Positive (De-escalated)</option>
                <option value="unreachable">Unreachable / User Stopped</option>
                <option value="other">Other Clinical Resolution</option>
              </select>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                Resolution Notes
              </label>
              <textarea
                rows={3}
                value={resolveNotes}
                onChange={(e) => setResolveNotes(e.target.value)}
                placeholder="Enter clinical rationale or referral details..."
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #D1D5DB', resize: 'vertical' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                onClick={() => setShowResolveModal(false)}
                style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #D1D5DB', color: '#4B5563', fontWeight: '600' }}
              >
                Cancel
              </button>
              <button
                onClick={handleResolve}
                style={{ padding: '8px 16px', borderRadius: '6px', backgroundColor: '#2F6B4F', color: '#FFFFFF', fontWeight: '600' }}
              >
                Confirm Resolution
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AUDIT LOG MODAL */}
      {showAuditModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            width: '90%',
            maxWidth: '780px',
            maxHeight: '80vh',
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '1.15rem', fontWeight: '700', color: '#1B4332' }}>
                  Tamper-Evident Audit Trail
                </h2>
                <div style={{ fontSize: '0.8rem', color: '#6B7280' }}>
                  SHA-256 Hash-Chained Verification (TRD §5 / Kenya DPA 2019)
                </div>
              </div>
              <button
                onClick={() => setShowAuditModal(false)}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #D1D5DB', fontWeight: '600' }}
              >
                Close
              </button>
            </div>

            {auditVerify && (
              <div style={{
                padding: '10px 14px',
                borderRadius: '8px',
                marginBottom: '14px',
                backgroundColor: auditVerify.valid ? '#ECFDF5' : '#FDF2F2',
                border: auditVerify.valid ? '1px solid #A7F3D0' : '1px solid #F5B7B1',
                color: auditVerify.valid ? '#065F46' : '#962D22',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <span>{auditVerify.valid ? '✅' : '❌'}</span>
                <span>
                  <strong>Cryptographic Verification:</strong> {auditVerify.valid ? 'All audit chain hashes verified tamper-free.' : 'Tamper detected in audit trail!'} (Verified {auditVerify.verified_entries} entries)
                </span>
              </div>
            )}

            <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #E5E7EB', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#F9FAFB', borderBottom: '1px solid #E5E7EB', textAlign: 'left' }}>
                    <th style={{ padding: '8px 12px' }}>Seq</th>
                    <th style={{ padding: '8px 12px' }}>Timestamp</th>
                    <th style={{ padding: '8px 12px' }}>Action</th>
                    <th style={{ padding: '8px 12px' }}>Actor</th>
                    <th style={{ padding: '8px 12px' }}>Entry Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.seq} style={{ borderBottom: '1px solid #F3F4F6' }}>
                      <td style={{ padding: '8px 12px' }} className="mono">{log.seq}</td>
                      <td style={{ padding: '8px 12px' }}>{new Date(log.timestamp).toLocaleString()}</td>
                      <td style={{ padding: '8px 12px', fontWeight: '600' }}>{log.action}</td>
                      <td style={{ padding: '8px 12px' }}>{log.actor_type}</td>
                      <td style={{ padding: '8px 12px' }} className="mono">{log.entry_hash?.slice(0, 12)}...</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
