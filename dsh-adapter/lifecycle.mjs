import { RequestTimeoutError } from '@deepseek-ai/dsh-sdk-client';

export const INITIALIZE_TIMEOUT_MS = 60000;

// Deliberately retain neither the raw SDK exception nor its stderr-bearing message.
export class BridgeFailure extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

export async function runWithPhases(harness, prompt, options) {
  try {
    // The pinned SDK memoizes successful initialization; run() reuses this handshake.
    await harness.start();
  } catch (error) {
    throw new BridgeFailure(error instanceof RequestTimeoutError
      ? 'DSH_INITIALIZATION_TIMEOUT' : 'DSH_INITIALIZATION_FAILED');
  }
  try {
    return await harness.run(prompt, options);
  } catch {
    throw new BridgeFailure('DSH_RUNTIME_FAILED');
  }
}
