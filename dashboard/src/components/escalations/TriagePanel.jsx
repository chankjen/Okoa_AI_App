import React from 'react';

export default function TriagePanel({ session, onClaim, onUnclaim, onResolve, onMute }) {
  if (!session) return null;

  return (
    <div style={{
      width: '320px',
      backgroundColor: '#FFFFFF',
      borderLeft: '1px solid #E5E9E7',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px',
      overflowY: 'auto',
    }}>
      {/* Clinical Triage Summary */}
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
          fontSize: '0.8rem',
        }}>
          <Row label="Risk Classification">
            <span className={`badge badge-${session.risk_label}`}>{session.risk_label}</span>
          </Row>
          <Row label="Risk Score">
            <span style={{ fontWeight: '700', color: '#111827' }}>{session.risk_score} / 100</span>
          </Row>
          {/* Risk progress bar */}
          <div style={{ height: '4px', borderRadius: '2px', backgroundColor: '#E5E7EB', overflow: 'hidden' }}>
            <div style={{
              width: `${Math.min(100, session.risk_score)}%`,
              height: '100%',
              backgroundColor: session.risk_label === 'crisis' ? '#C0392B' : session.risk_score > 45 ? '#D97706' : '#10B981',
              transition: 'width 0.4s ease',
            }} />
          </div>
          <Row label="SLA Target">
            <span style={{ fontWeight: '600', color: '#059669' }}>&lt; 120 seconds</span>
          </Row>
          <Row label="Status">
            <span style={{ fontWeight: '600' }}>{session.status}</span>
          </Row>
          {session.claimed_by && (
            <Row label="Assigned Counselor">
              <span style={{ fontWeight: '600' }}>Dr. Ochieng</span>
            </Row>
          )}
        </div>
      </div>

      {/* Clinical Actions */}
      <div>
        <h3 style={{ fontSize: '0.875rem', fontWeight: '700', color: '#1F2937', marginBottom: '12px' }}>
          Clinical Actions
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {session.status === 'open' ? (
            <ActionButton onClick={onClaim} variant="primary">
              Claim Session Ownership
            </ActionButton>
          ) : (
            <ActionButton onClick={onUnclaim} variant="secondary">
              Release / Unclaim
            </ActionButton>
          )}

          <ActionButton onClick={onResolve} variant="success">
            ✓ Resolve Escalation
          </ActionButton>

          <ActionButton onClick={onMute} variant="ghost">
            Mute / False Positive
          </ActionButton>
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
        color: '#962D22',
      }}>
        <strong>Emergency Routing:</strong> Kenya Red Cross toll-free line <strong>1199</strong> is automatically pushed to all users triggering risk &gt; 85%.
      </div>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: '#6B7280' }}>{label}:</span>
      {children}
    </div>
  );
}

function ActionButton({ onClick, variant = 'primary', children }) {
  const styles = {
    primary: { backgroundColor: '#2F6B4F', color: '#FFFFFF', border: 'none' },
    secondary: { backgroundColor: '#F3F4F6', color: '#4B5563', border: '1px solid #E5E7EB' },
    success: { backgroundColor: '#ECFDF5', color: '#065F46', border: '1px solid #A7F3D0' },
    ghost: { backgroundColor: '#FFFFFF', color: '#6B7280', border: '1px solid #D1D5DB' },
  };

  return (
    <button
      onClick={onClick}
      style={{
        width: '100%',
        padding: '10px',
        borderRadius: '8px',
        fontWeight: '600',
        fontSize: '0.825rem',
        cursor: 'pointer',
        ...styles[variant],
      }}
    >
      {children}
    </button>
  );
}
