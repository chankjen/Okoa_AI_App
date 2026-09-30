import React from 'react';
import Modal from '../../design-system/Modal';

export default function AuditModal({ isOpen, onClose, auditLogs, auditVerify }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Tamper-Evident Audit Trail" maxWidth="780px">
      <div style={{ fontSize: '0.8rem', color: '#6B7280', marginTop: '-8px', marginBottom: '16px' }}>
        SHA-256 Hash-Chained Verification (TRD §5 / Kenya DPA 2019)
      </div>

      {auditVerify && (
        <div style={{
          padding: '10px 14px',
          borderRadius: '8px',
          marginBottom: '14px',
          backgroundColor: auditVerify.valid ? '#ECFDF5' : '#FDF2F2',
          border: `1px solid ${auditVerify.valid ? '#A7F3D0' : '#F5B7B1'}`,
          color: auditVerify.valid ? '#065F46' : '#962D22',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <span>{auditVerify.valid ? '✅' : '❌'}</span>
          <span>
            <strong>Cryptographic Verification:</strong>{' '}
            {auditVerify.valid
              ? 'All audit chain hashes verified tamper-free.'
              : 'Tamper detected in audit trail!'}{' '}
            (Verified {auditVerify.verified_entries} entries)
          </span>
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #E5E7EB', borderRadius: '8px', maxHeight: '55vh' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
          <thead>
            <tr style={{ backgroundColor: '#F9FAFB', borderBottom: '1px solid #E5E7EB', textAlign: 'left' }}>
              {['Seq', 'Timestamp', 'Action', 'Actor', 'Entry Hash'].map(h => (
                <th key={h} style={{ padding: '8px 12px', fontWeight: '600', color: '#374151' }}>{h}</th>
              ))}
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
    </Modal>
  );
}
