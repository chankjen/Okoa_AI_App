import React from 'react';
import StatusChip from '../../design-system/StatusChip';
import RiskBadge from '../../design-system/RiskBadge';
import SLACountdownBadge from '../../design-system/SLACountdownBadge';

export default function EscalationRow({ escalation, isSelected, onSelect }) {
  const isCrisis = escalation.risk_label === 'crisis';

  return (
    <div
      onClick={() => onSelect(escalation)}
      style={{
        padding: '14px 16px',
        borderRadius: '10px',
        backgroundColor: isSelected ? '#F0FDF4' : '#FFFFFF',
        border: `1.5px solid ${isSelected ? '#2F6B4F' : '#E5E7EB'}`,
        marginBottom: '10px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        boxShadow: isSelected ? '0 4px 6px -1px rgba(47, 107, 79, 0.08)' : '0 1px 2px rgba(0, 0, 0, 0.03)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <RiskBadge label={escalation.risk_label} score={escalation.risk_score} />
          <StatusChip status={escalation.status} />
        </div>
        <SLACountdownBadge createdAt={escalation.created_at} status={escalation.status} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '6px' }}>
        <span
          className="mono"
          style={{
            fontSize: '0.78rem',
            color: '#4B5563',
            background: '#F3F4F6',
            padding: '2px 6px',
            borderRadius: '4px',
          }}
          title={escalation.user_uuid}
        >
          {escalation.user_uuid?.slice(0, 16)}...
        </span>

        <span style={{ fontSize: '0.72rem', color: '#9CA3AF' }}>
          {escalation.created_at ? new Date(escalation.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
        </span>
      </div>

      {escalation.claimed_by && (
        <div style={{ fontSize: '0.74rem', color: '#6D28D9', marginTop: '6px', fontWeight: 500 }}>
          👤 Claimed
        </div>
      )}
    </div>
  );
}
