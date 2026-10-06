import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import readline from 'node:readline';
import { BridgeFailure, INITIALIZE_TIMEOUT_MS, runWithPhases } from './lifecycle.mjs';

const write = value => process.stdout.write(`${JSON.stringify(value)}\n`);
const hash = value => createHash('sha256').update(value).digest('hex');
const lines = readline.createInterface({ input: process.stdin });
const input = await new Promise(resolve => lines.once('line', resolve));
lines.close();
const job = JSON.parse(input);
const env = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'HARNESS_DSH_GATEWAY',
  'HARNESS_DSH_CAPABILITY', 'HARNESS_DSH_MODEL', 'HARNESS_DSH_TOOLS'].filter(k => process.env[k]).map(k => [k, process.env[k]]));
env.HARNESS_DSH_PLUGIN = fileURLToPath(new URL('./platform-plugin.mjs', import.meta.url));
const harness = new DeepSeekHarness({
  profile: 'sdk-minimal', patches: [fileURLToPath(new URL('./controlled.patch.yml', import.meta.url))],
  dshHome: job.home, cwd: job.cwd, processCwd: job.cwd, env,
  provider: 'harness-platform', model: env.HARNESS_DSH_MODEL, maxTokens: job.max_output_tokens,
  initializeTimeoutMs: INITIALIZE_TIMEOUT_MS, requestTimeoutMs: 20000,
  shutdownTimeoutMs: 500, disposeEofGraceMs: 1000, disposeGraceMs: 1000,
});
let interrupted = false;
process.on('SIGTERM', () => { interrupted = true; void harness.close().catch(() => {}); });
try {
  const result = await runWithPhases(harness, job.prompt, { onNotification(n) {
    if (n.method !== 'session.event') return;
    const encoded = JSON.stringify(n.params);
    // No producer-controlled text, event name, ID or error leaves this projection.
    write({ type: 'observation', sha256: hash(encoded), bytes: Buffer.byteLength(encoded) });
  } });
  const ends = result.events.filter(e => e.type === 'turn/end');
  if (interrupted || !ends.length || ends.at(-1).data?.reason?.kind !== 'completed' || !result.finalResponse.trim()) {
    throw new Error('DSH_TURN_NOT_COMPLETED');
  }
  await harness.close();
  write({ type: 'result', text: result.finalResponse, session_sha256: hash(result.sessionId),
    turn_count: ends.length, runtime: 'deepseek-harness@0.2.1-alpha.1' });
} catch (error) {
  // Raw SDK errors include stderr/session content; never forward them.
  await harness.close().catch(() => {});
  write({ type: 'error', code: interrupted ? 'DSH_CANCELLED'
    : error instanceof BridgeFailure ? error.code : 'DSH_RUNTIME_FAILED' });
  process.exitCode = 1;
}
