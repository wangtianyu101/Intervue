import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// Mock Next.js router (避免引入 next/router 真实模块)
vi.mock('next/router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
  }),
}));

// Mock API token (避免 localStorage 在 happy-dom 里报错)
vi.mock('@/lib/api', () => ({
  getToken: vi.fn(() => 'mock-token'),
  clearToken: vi.fn(),
  setToken: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadResume: vi.fn(),
  deleteResume: vi.fn(),
  startInterview: vi.fn(),
  getNextQuestion: vi.fn(),
  submitAnswer: vi.fn(),
  getReport: vi.fn(),
  generateReport: vi.fn(),
}));