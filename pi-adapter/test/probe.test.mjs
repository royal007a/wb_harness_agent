import assert from "node:assert/strict";
import test from "node:test";
import { Agent } from "@earendil-works/pi-agent-core";
import { createModels, fauxAssistantMessage, fauxProvider, fauxText } from "@earendil-works/pi-ai";
import { BoundedEventBridge, PiProtocolError, mapPiEvent, runProbe } from "../src/probe.mjs";

test("offline Pi faux model probe maps tool loop to platform events", async () => {
  const result = await runProbe();
  assert.equal(result.status, "passed");
  assert.equal(result.mode, "pi_faux_model_offline");
  assert.equal(result.model_calls, 2);
  assert.equal(result.external_calls, 0);
  assert.equal(result.runtime_enabled, false);
  assert.ok(result.platform_events.includes("tool.call.requested"));
  assert.ok(result.platform_events.includes("run.result.proposed"));
});

test("unknown Pi events fail closed", () => {
  assert.throws(() => mapPiEvent({ type: "made_up_event" }), PiProtocolError);
});

test("bounded bridge drops only deltas and rejects terminal overflow", () => {
  const bridge = new BoundedEventBridge(2);
  bridge.push({ type: "agent_start" });
  bridge.push({ type: "model.delta" });
  bridge.push({ type: "model.delta" });
  assert.equal(bridge.drain().dropped_deltas, 1);
  bridge.push({ type: "agent_start" });
  bridge.push({ type: "turn_start" });
  assert.throws(() => bridge.push({ type: "tool_execution_end" }), PiProtocolError);
});

test("Pi abort produces a terminal agent_end without external calls", async () => {
  const faux = fauxProvider({ provider: "harness-abort", tokensPerSecond: 1 });
  faux.setResponses([fauxAssistantMessage(fauxText("x".repeat(1000)))]);
  const models = createModels();
  models.setProvider(faux.provider);
  const agent = new Agent({
    initialState: { model: faux.getModel() },
    streamFn: models.streamSimple.bind(models),
  });
  const events = [];
  agent.subscribe((event) => events.push(event));
  const running = agent.prompt("start");
  setTimeout(() => agent.abort(), 10);
  await running;
  assert.ok(events.some((event) => event.type === "agent_end"));
  assert.equal(faux.state.callCount, 1);
});
