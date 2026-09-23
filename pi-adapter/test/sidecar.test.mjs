import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const script = join(root, "src", "sidecar.mjs");

function startProcess() {
  const child = spawn(process.execPath, [script], { stdio: ["pipe", "pipe", "pipe"] });
  let buffer = "";
  const output = [];
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
      if (line.trim()) output.push(JSON.parse(line));
    }
  });
  return { child, output };
}

function send(child, value) { child.stdin.write(`${JSON.stringify(value)}\n`); }

async function waitFor(output, predicate, timeout = 3000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const found = output.find(predicate);
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`timed out; output=${JSON.stringify(output)}`);
}

test("sidecar health/start/stream emits bounded offline contract events", async () => {
  const { child, output } = startProcess();
  send(child, { protocol: "pi-adapter@1", op: "health", request_id: "h1" });
  const health = await waitFor(output, (item) => item.op === "health");
  assert.equal(health.runtime_enabled, false);
  send(child, {
    protocol: "pi-adapter@1", op: "start", request_id: "s1", run_id: "run_sidecar_1",
    model: { provider: "faux", model_id: "offline-contract-review" },
    resource_ref: "contract-fixture-1", capabilities: ["evidence.locate"],
    limits: { max_turns: 4 },
  });
  await waitFor(output, (item) => item.op === "started");
  await waitFor(output, (item) => item.op === "event" && item.platform_type === "run.result.proposed");
  send(child, { protocol: "pi-adapter@1", op: "stream", request_id: "r1", run_id: "run_sidecar_1", after_seq: 0 });
  const streamEnd = await waitFor(output, (item) => item.op === "stream_end");
  assert.equal(streamEnd.done, true);
  const events = output.filter((item) => item.op === "event");
  assert.ok(events.some((item) => item.platform_type === "tool.call.requested"));
  assert.ok(events.some((item) => item.platform_type === "tool.call.completed"));
  child.kill();
  await once(child, "close");
});

test("sidecar rejects non-admitted models before execution", async () => {
  const { child, output } = startProcess();
  send(child, {
    protocol: "pi-adapter@1", op: "start", request_id: "bad1", run_id: "run_bad_1",
    model: { provider: "anthropic", model_id: "real-model" }, capabilities: ["evidence.locate"], limits: { max_turns: 1 },
  });
  const error = await waitFor(output, (item) => item.op === "error");
  assert.equal(error.code, "MODEL_NOT_ADMITTED");
  assert.equal(output.filter((item) => item.op === "event").length, 0);
  child.kill();
  await once(child, "close");
});
