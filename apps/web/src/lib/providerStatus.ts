import type { SimulationSnapshot } from './types';

export type ProviderStatus = {
  primaryProvider: string;
  lastCompletedProvider: string | null;
  fallbackProvider: string | null;
  hasFallback: boolean;
  primaryLabel: string;
  lastCompletedLabel: string;
  fallbackLabel: string | null;
  fallbackDetail: string | null;
};

export function formatProviderName(provider?: string | null) {
  if (!provider) return 'none';
  if (provider === 'mock') return 'deterministic/mock';
  if (provider === 'qwen') return 'Qwen';
  return provider;
}

export function providerStatusForSnapshot(snapshot: SimulationSnapshot): ProviderStatus {
  const primaryProvider =
    snapshot.configured_provider ??
    snapshot.active_provider ??
    snapshot.last_completed_provider ??
    snapshot.last_llm_provider ??
    'mock';
  const lastCompletedProvider =
    snapshot.last_completed_provider ?? snapshot.last_llm_provider ?? null;
  const fallbackProvider = snapshot.last_fallback_provider ?? null;
  const hasFallback = Boolean(
    primaryProvider !== 'mock' && (fallbackProvider || snapshot.last_fallback_reason)
  );
  const fallbackTarget = fallbackProvider ?? lastCompletedProvider ?? 'mock';
  const fallbackAgent = snapshot.last_fallback_agent ?? 'Last agent';
  const fallbackReason = snapshot.last_fallback_reason
    ? `: ${snapshot.last_fallback_reason}`
    : '';

  return {
    primaryProvider,
    lastCompletedProvider,
    fallbackProvider,
    hasFallback,
    primaryLabel:
      primaryProvider === 'mock'
        ? formatProviderName(primaryProvider)
        : `${formatProviderName(primaryProvider)} active`,
    lastCompletedLabel: formatProviderName(lastCompletedProvider),
    fallbackLabel: hasFallback ? 'last step fallback' : null,
    fallbackDetail: hasFallback
      ? `${fallbackAgent} fell back to ${formatProviderName(fallbackTarget)}${fallbackReason}`
      : null
  };
}
