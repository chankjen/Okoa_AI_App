/**
 * OKOA Design System (DS — Okoa) Tokens
 * Reference: docs/FIGMA_WORKFLOW.md §3.1 & §3.2
 */

export const COLOR_TOKENS = {
  // Brand & Calm Colors
  primary: '#2F6B4F',        // Calm green (primary brand)
  primaryHover: '#24563E',
  primaryDark: '#1B4332',
  primaryLight: '#EBF3EE',
  primaryTint: '#D8E8DE',

  // Accent
  accent: '#E8A33D',         // Warm amber/gold accent

  // Crisis (reserved ONLY for safety surfaces)
  crisisRed: '#C0392B',
  crisisDark: '#962D22',
  crisisBg: '#FDF2F2',
  crisisBorder: '#F5B7B1',

  // Distress
  distressAmber: '#D97706',
  distressBg: '#FEF3C7',
  distressBorder: '#FCD34D',

  // Safe
  safeGreen: '#059669',
  safeBg: '#ECFDF5',
  safeBorder: '#A7F3D0',

  // Neutral scale
  neutral50: '#F9FAFB',
  neutral100: '#F3F4F6',
  neutral200: '#E5E7EB',
  neutral300: '#D1D5DB',
  neutral400: '#9CA3AF',
  neutral500: '#6B7280',
  neutral600: '#4B5563',
  neutral700: '#374151',
  neutral800: '#1F2937',
  neutral900: '#111827',
};

export const SPACING_TOKENS = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  xxl: '32px',
  xxxl: '48px',
};

export const SLA_THRESHOLDS = {
  crisisTargetSeconds: 120, // 2 minutes PRD KPI
  warningThresholdSeconds: 90,
};
