import React from 'react';

export default function Header({
  counselor,
  isOnDuty,
  onToggleDuty,
  wsStatus,
  criticalCount = 0,
  onOpenAudit,
  onOpenTrends,
  onOpenMobilePreview,
  onLogout,
}) {
  return (
    <header
      style={{
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E5E7EB',
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #2F6B4F 0%, #1B4332 100%)',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '1rem',
              letterSpacing: '-0.02em',
            }}
          >
            OK
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#111827', lineHeight: 1.2 }}>
              OKOA AI <span style={{ fontWeight: 400, color: '#6B7280', fontSize: '0.85rem' }}>Counselor Station</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#9CA3AF' }}>
              Kenya Youth Crisis Interception & Human-in-the-Loop
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '9999px',
            backgroundColor: wsStatus === 'connected' ? '#ECFDF5' : '#F3F4F6',
            border: `1px solid ${wsStatus === 'connected' ? '#A7F3D0' : '#E5E7EB'}`,
            fontSize: '0.75rem',
            fontWeight: 600,
            color: wsStatus === 'connected' ? '#065F46' : '#6B7280',
          }}
        >
          <span className={`live-indicator-dot ${wsStatus !== 'connected' ? 'offline' : ''}`} />
          {wsStatus === 'connected' ? 'Live Gateway Sync' : 'Reconnecting...'}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        {criticalCount > 0 && (
          <div
            className="pulse-critical"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#FDF2F2',
              color: '#962D22',
              border: '1px solid #F5B7B1',
              padding: '4px 10px',
              borderRadius: '9999px',
              fontSize: '0.78rem',
              fontWeight: 700,
            }}
          >
            <span>🚨</span>
            <span>{criticalCount} Critical Action Required</span>
          </div>
        )}
        <button
          onClick={onOpenMobilePreview}
          style={{
            padding: '6px 12px',
            borderRadius: '8px',
            border: '1px solid #D1D5DB',
            backgroundColor: '#FFFFFF',
            color: '#374151',
            fontSize: '0.825rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
          title="Preview patient WhatsApp experience (Karibu, CBT, 1199 Helpline)"
        >
          📱 Mobile View
        </button>

        <button
          onClick={onOpenTrends}
          style={{
            padding: '6px 12px',
            borderRadius: '8px',
            border: '1px solid #D1D5DB',
            backgroundColor: '#FFFFFF',
            color: '#374151',
            fontSize: '0.825rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
          title="SLA performance metrics and drill history"
        >
          📊 Trends & SLA
        </button>

        <button
          onClick={onOpenAudit}
          style={{
            padding: '6px 12px',
            borderRadius: '8px',
            border: '1px solid #D1D5DB',
            backgroundColor: '#FFFFFF',
            color: '#374151',
            fontSize: '0.825rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
          title="Tamper-evident SHA-256 chain verification"
        >
          🔒 Audit Trail
        </button>

        <div style={{ width: '1px', height: '24px', backgroundColor: '#E5E7EB' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={onToggleDuty}
            style={{
              padding: '5px 10px',
              borderRadius: '6px',
              fontSize: '0.78rem',
              fontWeight: 600,
              border: `1px solid ${isOnDuty ? '#059669' : '#D1D5DB'}`,
              backgroundColor: isOnDuty ? '#ECFDF5' : '#F9FAFB',
              color: isOnDuty ? '#065F46' : '#6B7280',
            }}
            title="Toggle active on-duty status for emergency routing"
          >
            {isOnDuty ? '🟢 On Duty' : '⚪ Off Duty'}
          </button>

          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1F2937' }}>
            {counselor?.displayName || 'Dr. Ochieng'}
          </span>

          <button
            onClick={onLogout}
            style={{
              fontSize: '0.8rem',
              color: '#9CA3AF',
              padding: '4px 6px',
              borderRadius: '4px',
            }}
            title="Log out of station"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
