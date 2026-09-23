import { Agent } from "@earendil-works/pi-agent-core";
import {
  createModels,
  fauxAssistantMessage,
  fauxProvider,
  fauxText,
  fauxToolCall,
} from "@earendil-works/pi-ai";
import { Type } from "typebox";

const TERMINAL_EVENTS = new Set(["run.result.proposed", "run.failed", "run.cancelled"]);
const DROPPABLE_EVENTS = new Set(["model.delta"]);

export class PiProtocolError extends Error {
  constructor(message) {
    super(message);
    this.name = "PiProtocolError";
  }
}

export class BoundedEventBridge {
  constructor(capacity = 64) {
    if (!Number.isInteger(capacity) || capacity < 2) throw new Error("capacity must be >= 2");
    this.capacity = capacity;
    this.events = [];
    this.droppedDeltas = 0;
  }

  push(event) {
    if (!event || typeof event.type !== "string") throw new PiProtocolError("event type is required");
    if (this.events.length >= this.capacity) {
      if (DROPPABLE_EVENTS.has(event.type)) {
        this.droppedDeltas += 1;
        return;
      }
      throw new PiProtocolError(`adapter.backpressure: cannot drop ${event.type}`);
    }
    this.events.push(event);
  }

  drain() {
    const result = this.events.splice(0, this.events.length);
    return { events: result, dropped_deltas: this.droppedDeltas };
  }
}

function mapPiEvent(event) {
  const type = event?.type;
  const payload = event && typeof event === "object" ? { ...event } : {};
  delete payload.type;
  switch (type) {
    case "agent_start": return { type, platform_type: "run.started", payload };
    case "turn_start": return { type, platform_type: "model.call.started", payload };
    case "message_start":
    case "message_end": return { type, platform_type: "model.message", payload };
    case "message_update": return { type, platform_type: "model.delta", payload };
    case "tool_execution_start": return { type, platform_type: "tool.call.requested", payload };
    case "tool_execution_update": return { type, platform_type: "tool.call.progress", payload };
    case "tool_execution_end": return { type, platform_type: "tool.call.completed", payload };
    case "turn_end": return { type, platform_type: "step.completed", payload };
    case "agent_end": return { type, platform_type: "run.result.proposed", payload };
    default: throw new PiProtocolError(`unknown Pi event: ${String(type)}`);
  }
}

function reviewTool() {
  return {
    name: "evidence_locate",
    label: "Locate contract evidence",
    description: "Return a bounded clause evidence reference from the authorized contract resource.",
    parameters: Type.Object({ clause_id: Type.String() }),
    execute: async (_toolCallId, params) => ({
      content: [{ type: "text", text: `evidence://${params.clause_id}/page-8` }],
      details: { evidence_ref: `evidence://${params.clause_id}/page-8`, source: "fixture" },
    }),
  };
}

export async function runProbe({ capacity = 64 } = {}) {
  const faux = fauxProvider({ provider: "harness-faux", tokensPerSecond: 1000 });
  faux.setResponses([
    fauxAssistantMessage([
      fauxToolCall("evidence_locate", { clause_id: "clause-12.3" }),
    ], { stopReason: "toolUse" }),
    fauxAssistantMessage([
      fauxText(JSON.stringify({
        risk_level: "high",
        evidence_refs: ["evidence://clause-12.3/page-8"],
        needs_human: true,
      })),
    ]),
  ]);
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const bridge = new BoundedEventBridge(capacity);
  const agent = new Agent({
    initialState: {
      systemPrompt: "You are a contract review probe. Cite evidence and never invent a source.",
      model,
      tools: [reviewTool()],
    },
    streamFn: models.streamSimple.bind(models),
    toolExecution: "sequential",
    beforeToolCall: async ({ toolCall, args }) => {
      if (toolCall.name !== "evidence_locate" || typeof args?.clause_id !== "string") {
        return { block: true, terminate: true, reason: "TOOL_NOT_ADMITTED" };
      }
      return undefined;
    },
  });
  agent.subscribe((event) => bridge.push(mapPiEvent(event)));
  await agent.prompt("Review the price-adjustment clause and return a cited finding.");
  const { events, dropped_deltas } = bridge.drain();
  const platformTypes = events.map((event) => event.platform_type);
  const required = ["run.started", "model.call.started", "tool.call.requested", "tool.call.completed", "step.completed", "run.result.proposed"];
  for (const type of required) {
    if (!platformTypes.includes(type)) throw new Error(`missing mapped event: ${type}`);
  }
  if (faux.state.callCount !== 2) throw new Error(`expected two faux model calls, got ${faux.state.callCount}`);
  return {
    status: "passed",
    mode: "pi_faux_model_offline",
    pi_versions: { agent_core: "0.87.1", ai: "0.87.1" },
    event_count: events.length,
    platform_events: platformTypes,
    model_calls: faux.state.callCount,
    external_calls: 0,
    dropped_deltas,
    runtime_enabled: false,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  runProbe().then((result) => {
    process.stdout.write(`${JSON.stringify(result)}\n`);
  }).catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  });
}

export { mapPiEvent };
