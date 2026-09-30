import React, { useState } from 'react';

export default function LoginView({ onLoginSuccess }) {
  const [username, setUsername] = useState('dr_ochieng');
  const [password, setPassword] = useState('Password123!');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('http://localhost:8000/counselor/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Invalid username or password');
      }

      const data = await res.json();
      onLoginSuccess(data.access_token, {
        username,
        displayName: data.display_name || 'Dr. Ochieng (Lead Clinical Officer)',
      });
    } catch (err) {
      setError(err.message || 'Cannot reach OKOA backend server at localhost:8000');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#F4F7F5',
        padding: '24px',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '420px',
          backgroundColor: '#FFFFFF',
          borderRadius: '16px',
          border: '1px solid #E5E9E7',
          padding: '36px',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.05)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #2F6B4F 0%, #1B4332 100%)',
              color: '#FFFFFF',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '1.3rem',
              marginBottom: '12px',
            }}
          >
            OK
          </div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#111827', margin: 0 }}>
            OKOA AI Counselor Portal
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#6B7280', marginTop: '6px' }}>
            Clinical crisis escalation queue & WhatsApp live intervention
          </p>
        </div>

        {error && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '8px',
              backgroundColor: '#FDF2F2',
              border: '1px solid #F5B7B1',
              color: '#962D22',
              fontSize: '0.85rem',
              marginBottom: '20px',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: '8px',
                border: '1px solid #D1D5DB',
                outline: 'none',
              }}
              placeholder="e.g. dr_ochieng"
            />
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px 14px',
                borderRadius: '8px',
                border: '1px solid #D1D5DB',
                outline: 'none',
              }}
              placeholder="••••••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '11px',
              borderRadius: '8px',
              backgroundColor: '#2F6B4F',
              color: '#FFFFFF',
              fontWeight: 600,
              fontSize: '0.95rem',
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Authenticating...' : 'Sign in to Counselor Queue'}
          </button>
        </form>

        <div
          style={{
            marginTop: '24px',
            paddingTop: '16px',
            borderTop: '1px solid #F3F4F6',
            fontSize: '0.78rem',
            color: '#6B7280',
            textAlign: 'center',
          }}
        >
          Default seeded account: <code>dr_ochieng</code> / <code>Password123!</code>
        </div>
      </div>
    </div>
  );
}
