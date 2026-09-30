import React from 'react';

const STATUS_CONFIGS = {
  open: { label: 'Open', className: 'badge-open' },
  claimed: { label: 'Claimed', className: 'badge-claimed' },
  handed_over: { label: 'Handed Over', className: 'badge-handed-over' },
  'handed-over': { label: 'Handed Over', className: 'badge-handed-over' },
  resolved: { label: 'Resolved', className: 'badge-resolved' },
  muted: { label: 'Muted', className: 'badge-resolved' },
};

export default function StatusChip({ status }) {
  const normalized = (status || 'open').toLowerCase().replace(' ', '_');
  const cfg = STATUS_CONFIGS[normalized] || { label: status, className: 'badge-resolved' };

  return (
    <span className={`badge ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}
