import readline from "node:readline";
import { randomUUID } from "node:crypto";
import { Agent } from "@earendil-works/pi-agent-core";
import {
  createModels,
  fauxAssistantMessage,
  fauxProvider,
  fauxText,
  fauxToolCall,
} from "@earendil-works/pi-ai";
import { Type } from "typebox";

const PROTOCOL = "pi-adapter@1";
const VERSION = { agent_core: "0.87.1", ai: "0.87.1" };
const sessions = new Map();

function jsonLine(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function errorResponse(request, code, message) {
  jsonLine({ protocol: PROTOCOL, op: "error", request_id: request?.request_id ?? null, code, message });
}

function validateStart(request) {
  if (request.protocol !== PROTOCOL) throw new Error("PROTOCOL_MISMATCH");
  if (typeof request.run_id !== "string" || !request.run_id) throw new Error("RUN_ID_REQUIRED");
  if (sessions.has(request.run_id)) throw new Error("RUN_ALREADY_ACTIVE");
  if (request.model?.provider !== "faux" || request.model?.model_id !== "offline-contract-review") {
    throw new Error("MODEL_NOT_ADMITTED");
  }
  const limits = request.limits ?? {};
  if (!Number.isInteger(limits.max_turns) || limits.max_turns < 1) throw new Error("INVALID_LIMITS");
  if (!Array.isArray(request.capabilities) || !request.capabilities.includes("evidence.locate")) {
    throw new Error("TOOL_NOT_ADMITTED");
  }
}

function evidenceTool(request) {
  return {
    name: "evidence_locate",
    label: "Locate contract evidence",
    description: "Return a bounded fixture evidence reference.",
    parameters: Type.Object({ clause_id: Type.String() }),
    execute: async (_toolCallId, args) => {
      if (args.clause_id !== "clause-12.3") throw new Error("EVIDENCE_NOT_FOUND");
      return {
        content: [{ type: "text", text: `evidence://${request.resource_ref}/clause-12.3/page-8` }],
        details: { source_id: request.resource_ref, page: 8, clause_id: args.clause_id },
      };
    },
  };
}

function makeSession(request) {
  const faux = fauxProvider({ provider: `harness-faux-${request.run_id}`, tokensPerSecond: 1000 });
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("evidence_locate", { clause_id: "clause-12.3" })], { stopReason: "toolUse" }),
    fauxAssistantMessage([fauxText(JSON.stringify({
      status: "needs_human",
      risk_level: "high",
      evidence_refs: [`evidence://${request.resource_ref}/clause-12.3/page-8`],
      recommendation: "补充价格调整上限与通知期",
    }))]),
  ]);
  const models = createModels();
  models.setProvider(faux.provider);
  const agent = new Agent({
    initialState: {
      systemPrompt: "You are an offline contract review probe. Use only the admitted evidence tool.",
      model: faux.getModel(),
      tools: [evidenceTool(request)],
    },
    streamFn: models.streamSimple.bind(models),
    toolExecution: "sequential",
    beforeToolCall: async ({ toolCall, args }) => {
      if (toolCall.name !== "evidence_locate" || args?.clause_id !== "clause-12.3") {
        return { block: true, terminate: true, reason: "TOOL_NOT_ADMITTED" };
      }
      return undefined;
    },
  });
  const session = {
    request,
    agent,
    faux,
    events: [],
    seq: 0,
    done: false,
    started: Date.now(),
  };
  agent.subscribe((event) => {
    const mapped = {
      agent_start: ["run.started", "run.started"],
      turn_start: ["model.call.started", "model.call.started"],
      message_start: ["model.message", "model.message"],
      message_update: ["model.delta", "model.delta"],
      message_end: ["model.message", "model.message"],
      tool_execution_start: ["tool.call.requested", "tool.call.requested"],
      tool_execution_update: ["tool.call.progress", "tool.call.progress"],
      tool_execution_end: ["tool.call.completed", "tool.call.completed"],
      turn_end: ["step.completed", "step.completed"],
      agent_end: ["run.result.proposed", "run.result.proposed"],
    }[event.type];
    if (!mapped) {
      session.done = true;
      jsonLine({ protocol: PROTOCOL, op: "error", run_id: request.run_id, code: "UNKNOWN_PI_EVENT", message: event.type });
      return;
    }
    const payload = { ...event };
    delete payload.type;
    const record = {
      protocol: PROTOCOL,
      op: "event",
      run_id: request.run_id,
      seq: ++session.seq,
      event: mapped[0],
      platform_type: mapped[1],
      payload,
    };
    session.events.push(record);
    jsonLine(record);
    if (event.type === "agent_end") session.done = true;
  });
  return session;
}

async function start(request) {
  validateStart(request);
  const session = makeSession(request);
  sessions.set(request.run_id, session);
  jsonLine({ protocol: PROTOCOL, op: "started", request_id: request.request_id ?? null,
    run_id: request.run_id, execution_id: `pi-exec-${randomUUID()}`, mode: "faux_offline" });
  session.agent.prompt("Review the admitted contract resource and return cited findings.")
    .catch((error) => {
      session.done = true;
      jsonLine({ protocol: PROTOCOL, op: "error", run_id: request.run_id, code: "AGENT_FAILED", message: String(error.message || error) });
    });
}

function stream(request) {
  const session = sessions.get(request.run_id);
  if (!session) throw new Error("RUN_NOT_FOUND");
  const after = Number.isInteger(request.after_seq) ? request.after_seq : 0;
  for (const event of session.events) if (event.seq > after) jsonLine(event);
  jsonLine({ protocol: PROTOCOL, op: "stream_end", request_id: request.request_id ?? null,
    run_id: request.run_id, next_seq: session.seq, done: session.done });
}

function cancel(request) {
  const session = sessions.get(request.run_id);
  if (!session) throw new Error("RUN_NOT_FOUND");
  session.agent.abort();
  jsonLine({ protocol: PROTOCOL, op: "cancelled", request_id: request.request_id ?? null,
    run_id: request.run_id, mode: "requested", external_calls: 0 });
}

async function handle(request) {
  try {
    switch (request.op) {
      case "health":
        jsonLine({ protocol: PROTOCOL, op: "health", status: "ok", runtime_enabled: false,
          versions: VERSION, active_runs: sessions.size, external_calls: 0 });
        break;
      case "start": await start(request); break;
      case "stream": stream(request); break;
      case "cancel": cancel(request); break;
      default: errorResponse(request, "OP_NOT_SUPPORTED", String(request.op));
    }
  } catch (error) {
    errorResponse(request, error.message || "SIDECAR_ERROR", error.message || String(error));
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    if (!line.trim()) continue;
    try { await handle(JSON.parse(line)); }
    catch (error) { errorResponse({}, "INVALID_JSON", error.message || String(error)); }
  }
}

export { handle, sessions, PROTOCOL };
