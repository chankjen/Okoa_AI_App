import React from 'react';
import Modal from '../../design-system/Modal';

export default function TrendsModal({ isOpen, onClose, slaMetrics }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Trends & SLA Performance" maxWidth="680px">
      {!slaMetrics ? (
        <div style={{ textAlign: 'center', padding: '32px', color: '#9CA3AF' }}>Loading SLA metrics...</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Key Metrics Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
            <MetricCard
              label="Avg Response Time"
              value={`${slaMetrics.avg_response_secs ?? '--'}s`}
              sub="SLA Target < 120s"
              ok={(slaMetrics.avg_response_secs ?? 999) < 120}
            />
            <MetricCard
              label="SLA Breaches"
              value={slaMetrics.sla_breaches ?? '--'}
              sub="Open escalations"
              ok={(slaMetrics.sla_breaches ?? 1) === 0}
              danger={(slaMetrics.sla_breaches ?? 0) > 0}
            />
            <MetricCard
              label="Resolution Rate"
              value={`${slaMetrics.resolution_rate_pct ?? '--'}%`}
              sub="Last 30 days"
              ok={(slaMetrics.resolution_rate_pct ?? 0) >= 80}
            />
          </div>

          {/* By Risk Label */}
          {slaMetrics.by_risk_label && (
            <div>
              <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#1F2937', marginBottom: '10px' }}>
                Escalations by Risk Classification
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {Object.entries(slaMetrics.by_risk_label).map(([label, count]) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span className={`badge badge-${label}`} style={{ minWidth: '72px', textAlign: 'center' }}>{label}</span>
                    <div style={{ flex: 1, height: '8px', borderRadius: '4px', backgroundColor: '#F3F4F6', overflow: 'hidden' }}>
                      <div style={{
                        height: '100%',
                        width: `${Math.min(100, (count / (slaMetrics.total ?? 1)) * 100)}%`,
                        backgroundColor: label === 'crisis' ? '#C0392B' : label === 'high' ? '#D97706' : '#10B981',
                        transition: 'width 0.5s ease',
                      }} />
                    </div>
                    <span style={{ fontSize: '0.78rem', color: '#6B7280', minWidth: '28px', textAlign: 'right' }}>{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ fontSize: '0.75rem', color: '#9CA3AF', textAlign: 'center' }}>
            Metrics refreshed on escalation queue load. Drill-down historical analytics coming in v2.
          </div>
        </div>
      )}
    </Modal>
  );
}

function MetricCard({ label, value, sub, ok, danger }) {
  const color = danger ? '#C0392B' : ok ? '#059669' : '#D97706';
  const bg = danger ? '#FDF2F2' : ok ? '#ECFDF5' : '#FFFBEB';
  return (
    <div style={{ padding: '14px', borderRadius: '10px', backgroundColor: bg, textAlign: 'center' }}>
      <div style={{ fontSize: '1.6rem', fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#1F2937', marginTop: '4px' }}>{label}</div>
      <div style={{ fontSize: '0.72rem', color: '#6B7280', marginTop: '2px' }}>{sub}</div>
    </div>
  );
}
