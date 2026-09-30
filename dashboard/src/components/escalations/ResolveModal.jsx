import React, { useState } from 'react';
import Modal from '../../design-system/Modal';

const OUTCOME_OPTIONS = [
  { value: 'helpline_confirmed', label: 'Helpline Confirmed (1199 routing verified)' },
  { value: 'counselor_contacted', label: 'Counselor Contacted Directly' },
  { value: 'false_positive', label: 'False Positive (De-escalated)' },
  { value: 'unreachable', label: 'Unreachable / User Stopped' },
  { value: 'other', label: 'Other Clinical Resolution' },
];

export default function ResolveModal({ isOpen, onClose, onConfirm }) {
  const [outcome, setOutcome] = useState('helpline_confirmed');
  const [notes, setNotes] = useState('');

  const handleConfirm = () => {
    onConfirm(outcome, notes);
    setNotes('');
    setOutcome('helpline_confirmed');
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Resolve Escalation">
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
          Clinical Outcome
        </label>
        <select
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
          style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #D1D5DB' }}
        >
          {OUTCOME_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
          Resolution Notes
        </label>
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Enter clinical rationale or referral details..."
          style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #D1D5DB', resize: 'vertical', fontFamily: 'inherit' }}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
        <button
          onClick={onClose}
          style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #D1D5DB', color: '#4B5563', fontWeight: '600', cursor: 'pointer', backgroundColor: '#FFFFFF' }}
        >
          Cancel
        </button>
        <button
          onClick={handleConfirm}
          style={{ padding: '8px 16px', borderRadius: '6px', backgroundColor: '#2F6B4F', color: '#FFFFFF', fontWeight: '600', border: 'none', cursor: 'pointer' }}
        >
          Confirm Resolution
        </button>
      </div>
    </Modal>
  );
}
