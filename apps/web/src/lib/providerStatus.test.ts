import { expect, test } from 'vitest';
import { providerStatusForSnapshot } from './providerStatus';
import type { SimulationSnapshot } from './types';

function snapshot(overrides: Partial<SimulationSnapshot>): SimulationSnapshot {
  return overrides as SimulationSnapshot;
}

test('labels qwen primary with mock fallback as last step fallback', () => {
  const status = providerStatusForSnapshot(
    snapshot({
      configured_provider: 'qwen',
      active_provider: 'qwen',
      last_completed_provider: 'mock',
      last_llm_provider: 'mock',
      last_fallback_provider: 'mock',
      last_fallback_agent: 'PortfolioManagerAgent',
      last_fallback_reason: 'Connection error.'
    })
  );

  expect(status.primaryLabel).toBe('Qwen active');
  expect(status.lastCompletedLabel).toBe('deterministic/mock');
  expect(status.fallbackLabel).toBe('last step fallback');
  expect(status.fallbackDetail).toContain('PortfolioManagerAgent fell back to deterministic/mock');
});

test('labels pure mock mode as deterministic mock without fallback warning', () => {
  const status = providerStatusForSnapshot(
    snapshot({
      configured_provider: 'mock',
      active_provider: 'mock',
      last_completed_provider: 'mock',
      last_llm_provider: 'mock'
    })
  );

  expect(status.primaryLabel).toBe('deterministic/mock');
  expect(status.hasFallback).toBe(false);
  expect(status.fallbackLabel).toBeNull();
});

test('labels qwen success without fallback warning', () => {
  const status = providerStatusForSnapshot(
    snapshot({
      configured_provider: 'qwen',
      active_provider: 'qwen',
      last_completed_provider: 'qwen',
      last_llm_provider: 'qwen'
    })
  );

  expect(status.primaryLabel).toBe('Qwen active');
  expect(status.lastCompletedLabel).toBe('Qwen');
  expect(status.hasFallback).toBe(false);
});
