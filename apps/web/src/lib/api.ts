import type {
  AgentActivityDetail,
  QwenProof,
  RecordedSimulationResponse,
  RecordingManifest,
  ReplayBenchmarkRun,
  Scenario,
  SimulationEstimate,
  SimulationRecordingFrame,
  SimulationRecordingKeyframe,
  SimulationSnapshot
} from './types';

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function json<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string') detail = payload.detail;
    } catch {
      // Keep the status fallback when the server does not return JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function listScenarios() {
  return json<{ scenarios: Scenario[] }>('/api/scenarios');
}

export function createSimulation(scenarioId: string) {
  return json<SimulationSnapshot>('/api/simulations', {
    method: 'POST',
    body: JSON.stringify({ scenario_id: scenarioId })
  });
}

export type MarketDataRequest = {
  market_data_mode?: 'synthetic' | 'yfinance' | 'alpaca';
  real_market_tickers?: string[];
  replay_date?: string | null;
};

export function estimateSimulation(scenarioId: string, durationMinutes: number, marketData?: MarketDataRequest) {
  return json<SimulationEstimate>('/api/simulations/estimate', {
    method: 'POST',
    body: JSON.stringify({ scenario_id: scenarioId, duration_minutes: durationMinutes, ...marketData })
  });
}

export function createRecordedSimulation(
  scenarioId: string,
  durationMinutes: number,
  name?: string,
  marketData?: MarketDataRequest
) {
  return json<RecordedSimulationResponse>('/api/simulations/recorded', {
    method: 'POST',
    body: JSON.stringify({ scenario_id: scenarioId, duration_minutes: durationMinutes, name, ...marketData })
  });
}

export function controlSimulation(simulationId: string, action: 'start' | 'pause' | 'resume' | 'step' | 'reset') {
  return json<SimulationSnapshot>(`/api/simulations/${simulationId}/${action}`, { method: 'POST' });
}

export function setSpeed(simulationId: string, speed: number) {
  return json<SimulationSnapshot>(`/api/simulations/${simulationId}/speed`, {
    method: 'POST',
    body: JSON.stringify({ speed })
  });
}

export function stopAndSaveSimulation(simulationId: string) {
  return json<{ recording: RecordingManifest | null; snapshot: SimulationSnapshot }>(
    `/api/simulations/${simulationId}/stop-and-save`,
    { method: 'POST' }
  );
}

export function listRecordings() {
  return json<{ recordings: RecordingManifest[] }>('/api/recordings');
}

export function getRecordingFrames(recordingId: string, offset = 0, limit = 5000) {
  return json<{ frames: SimulationRecordingFrame[] }>(
    `/api/recordings/${recordingId}/frames?offset=${offset}&limit=${limit}`
  );
}

export function getRecordingKeyframes(recordingId: string) {
  return json<{ keyframes: SimulationRecordingKeyframe[] }>(
    `/api/recordings/${recordingId}/keyframes`
  );
}

export function resumeRecording(recordingId: string) {
  return json<RecordedSimulationResponse>(`/api/recordings/${recordingId}/resume`, { method: 'POST' });
}

export function runBenchmark() {
  return json('/api/benchmarks/run', { method: 'POST' });
}

export function runSimulationBenchmark(simulationId: string) {
  return json<{ snapshot: SimulationSnapshot }>(`/api/simulations/${simulationId}/benchmark`, {
    method: 'POST'
  });
}

export function runRecordingBenchmark(recordingId: string) {
  return json<ReplayBenchmarkRun>(`/api/recordings/${recordingId}/benchmark`, {
    method: 'POST'
  });
}

export function getQwenProof() {
  return json<QwenProof>('/api/proof/qwen');
}

export function getAgentActivityDetail(simulationId: string, activityId: string) {
  return json<AgentActivityDetail>(
    `/api/simulations/${simulationId}/agent-activity/${activityId}`
  );
}

export function getRecordingActivityDetail(recordingId: string, activityId: string) {
  return json<AgentActivityDetail>(
    `/api/recordings/${recordingId}/agent-activity/${activityId}`
  );
}
