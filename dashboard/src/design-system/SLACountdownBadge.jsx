import React, { useState, useEffect } from 'react';

export default function SLACountdownBadge({ createdAt, status, slaSeconds = 120 }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!createdAt) return;

    const calculateElapsed = () => {
      const createdTime = new Date(createdAt).getTime();
      const now = Date.now();
      const diffSec = Math.max(0, Math.floor((now - createdTime) / 1000));
      setElapsed(diffSec);
    };

    calculateElapsed();
    const interval = setInterval(calculateElapsed, 1000);
    return () => clearInterval(interval);
  }, [createdAt]);

  if (status === 'resolved' || status === 'muted') {
    return null;
  }

  const remaining = slaSeconds - elapsed;
  const isBreached = remaining <= 0;

  if (isBreached) {
    const overdue = Math.abs(remaining);
    const mins = Math.floor(overdue / 60);
    const secs = overdue % 60;
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '9999px',
          fontSize: '0.72rem',
          fontWeight: 700,
          background: '#FDF2F2',
          color: '#C0392B',
          border: '1px solid #F5B7B1',
        }}
        title="Escalation SLA Breached (> 2 min without response)"
      >
        ⚠️ SLA Breached (+{mins}m {secs}s)
      </span>
    );
  }

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const isUrgent = remaining < 45;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '9999px',
        fontSize: '0.72rem',
        fontWeight: 600,
        background: isUrgent ? '#FEF3C7' : '#EFF6FF',
        color: isUrgent ? '#B45309' : '#1D4ED8',
        border: `1px solid ${isUrgent ? '#FCD34D' : '#BFDBFE'}`,
      }}
      title="SLA Countdown: Target < 2 min response"
    >
      ⏱️ {mins}:{secs < 10 ? `0${secs}` : secs}
    </span>
  );
}
