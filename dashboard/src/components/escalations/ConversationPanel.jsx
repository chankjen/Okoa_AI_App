import React, { useRef, useEffect } from 'react';

export default function ConversationPanel({ session, replyText, isSendingReply, onReplyChange, onSendReply, onToggleHandover }) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages?.length]);

  if (!session) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9CA3AF', flexDirection: 'column', gap: '12px' }}>
        <div style={{ fontSize: '2rem' }}>💬</div>
        <div style={{ fontSize: '0.875rem' }}>Select an escalation from the queue to view the live session.</div>
      </div>
    );
  }

  const isCounselorActive = session.handover_mode === 'counselor_active';

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#F9FAFB' }}>
      {/* Session Header */}
      <div style={{
        padding: '12px 20px',
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E5E9E7',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontWeight: '700', fontSize: '1rem', color: '#111827' }}>
              User Session:{' '}
              <span className="mono" style={{ color: '#2F6B4F' }}>{session.user_uuid}</span>
            </span>
            <span className={`badge badge-${session.risk_label}`}>
              {session.risk_label} ({Math.round(session.risk_score)}%)
            </span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#6B7280', marginTop: '2px' }}>
            Anonymous WhatsApp User · Zero PII Mode Active (Kenya DPA 2019 Compliant)
          </div>
        </div>

        {/* Handover Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: '600', color: '#6B7280', textTransform: 'uppercase' }}>
              Agent Mode
            </div>
            <div style={{ fontSize: '0.825rem', fontWeight: '700', color: isCounselorActive ? '#B45309' : '#059669' }}>
              {isCounselorActive ? 'Human Active (Bot Paused)' : 'Automated Bot Active'}
            </div>
          </div>
          <button
            onClick={onToggleHandover}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              fontWeight: '600',
              fontSize: '0.825rem',
              backgroundColor: isCounselorActive ? '#FEF3C7' : '#2F6B4F',
              color: isCounselorActive ? '#92400E' : '#FFFFFF',
              border: isCounselorActive ? '1px solid #FCD34D' : 'none',
              cursor: 'pointer',
            }}
          >
            {isCounselorActive ? '▶ Resume Bot' : '⏸ Pause & Take Over'}
          </button>
        </div>
      </div>

      {/* Handover Active Banner */}
      {isCounselorActive && (
        <div style={{
          padding: '8px 20px',
          backgroundColor: '#FFFBEB',
          borderBottom: '1px solid #FDE68A',
          color: '#92400E',
          fontSize: '0.8rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <span>⚠️</span>
          <span>
            <strong>Handover Active:</strong> Automated AI responses are paused. Your messages below will be dispatched directly to the user via WhatsApp Cloud API.
          </span>
        </div>
      )}

      {/* Chat Transcript */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {session.messages?.map((msg) => {
          const isInbound = msg.direction === 'inbound';
          const isCrisisPrompt = msg.kind === 'crisis_response';
          const time = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

          return (
            <div
              key={msg.id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: isInbound ? 'flex-start' : 'flex-end',
                marginBottom: '16px',
              }}
            >
              <div style={{
                maxWidth: '75%',
                padding: '12px 16px',
                borderRadius: isInbound ? '14px 14px 14px 2px' : '14px 14px 2px 14px',
                backgroundColor: isInbound ? '#FFFFFF' : isCrisisPrompt ? '#FDF2F2' : '#EBF3EE',
                color: isCrisisPrompt ? '#962D22' : '#1F2937',
                border: isCrisisPrompt ? '1px solid #F5B7B1' : '1px solid #E5E7EB',
                boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                  marginBottom: '4px',
                  fontSize: '0.72rem',
                  fontWeight: '700',
                  color: isInbound ? '#6B7280' : isCrisisPrompt ? '#C0392B' : '#2F6B4F',
                }}>
                  <span>{isInbound ? 'WhatsApp User' : isCrisisPrompt ? '🚨 Crisis System Intercept (1199)' : 'OKOA AI / Counselor'}</span>
                  <span style={{ fontWeight: '400', color: '#9CA3AF' }}>{time}</span>
                </div>
                <div style={{ fontSize: '0.9rem', whiteSpace: 'pre-wrap', lineHeight: '1.45' }}>
                  {msg.body}
                </div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Reply Composer */}
      <div style={{ padding: '16px 20px', backgroundColor: '#FFFFFF', borderTop: '1px solid #E5E9E7' }}>
        <form onSubmit={onSendReply} style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            placeholder={
              isCounselorActive
                ? 'Type direct reply to user in WhatsApp...'
                : 'Switch to Handover mode above to reply directly...'
            }
            value={replyText}
            onChange={(e) => onReplyChange(e.target.value)}
            disabled={!isCounselorActive || isSendingReply}
            style={{
              flex: 1,
              padding: '11px 16px',
              borderRadius: '8px',
              border: '1px solid #D1D5DB',
              outline: 'none',
              backgroundColor: isCounselorActive ? '#FFFFFF' : '#F9FAFB',
            }}
          />
          <button
            type="submit"
            disabled={!isCounselorActive || !replyText.trim() || isSendingReply}
            style={{
              padding: '0 20px',
              borderRadius: '8px',
              backgroundColor: isCounselorActive ? '#2F6B4F' : '#9CA3AF',
              color: '#FFFFFF',
              fontWeight: '600',
              fontSize: '0.875rem',
              border: 'none',
              cursor: isCounselorActive ? 'pointer' : 'not-allowed',
            }}
          >
            {isSendingReply ? 'Sending...' : 'Send to WhatsApp'}
          </button>
        </form>
      </div>
    </div>
  );
}
