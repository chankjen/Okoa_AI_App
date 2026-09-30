import React from 'react';
import EscalationRow from './EscalationRow';

const FILTERS = ['all', 'open', 'claimed', 'resolved'];

export default function EscalationQueue({ escalations, selectedId, filter, onFilterChange, onSelect }) {
  const openCount = escalations.filter(e => e.status === 'open').length;

  const filtered = escalations.filter((item) => {
    if (filter === 'all') return true;
    if (filter === 'open') return item.status === 'open';
    if (filter === 'claimed') return item.status === 'claimed' || item.status === 'handed_over';
    if (filter === 'resolved') return item.status === 'resolved' || item.status === 'muted';
    return true;
  });

  return (
    <div style={{
      width: '360px',
      borderRight: '1px solid #E5E9E7',
      backgroundColor: '#FFFFFF',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
    }}>
      {/* Filter Bar */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid #F3F4F6' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
          <span style={{ fontWeight: '700', fontSize: '0.9rem', color: '#1F2937' }}>Escalation Queue</span>
          <span style={{ fontSize: '0.75rem', fontWeight: '600', color: '#6B7280' }}>
            {openCount} Open
          </span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {FILTERS.map((t) => (
            <button
              key={t}
              onClick={() => onFilterChange(t)}
              style={{
                flex: 1,
                padding: '5px 0',
                fontSize: '0.75rem',
                fontWeight: filter === t ? '700' : '500',
                borderRadius: '6px',
                backgroundColor: filter === t ? '#EBF3EE' : '#F9FAFB',
                color: filter === t ? '#2F6B4F' : '#6B7280',
                textTransform: 'capitalize',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Queue List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: '36px 16px', textAlign: 'center', color: '#9CA3AF', fontSize: '0.85rem' }}>
            No escalations found in this view.
          </div>
        ) : (
          filtered.map((esc) => (
            <EscalationRow
              key={esc.id}
              escalation={esc}
              isSelected={esc.id === selectedId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  );
}
