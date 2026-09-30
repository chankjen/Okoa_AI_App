import React from 'react';

export default function RiskBadge({ label, score }) {
  const norm = (label || 'safe').toLowerCase();

  let badgeClass = 'badge-safe';
  let displayLabel = 'Safe';

  if (norm === 'crisis') {
    badgeClass = 'badge-crisis pulse-critical';
    displayLabel = 'Crisis';
  } else if (norm === 'distressed' || norm === 'distress') {
    badgeClass = 'badge-distressed';
    displayLabel = 'Distressed';
  }

  return (
    <span className={`badge ${badgeClass}`}>
      {displayLabel} {score !== undefined && `(${Math.round(score)})`}
    </span>
  );
}
