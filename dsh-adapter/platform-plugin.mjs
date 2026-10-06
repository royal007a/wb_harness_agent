import { LlmAdapter } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';

export const name = 'harnessagent-platform';
export const inject = ['llm', 'tools'];
async function request(path, body, signal) {
  const endpoint = new URL(process.env.HARNESS_DSH_GATEWAY);
  if (endpoint.hostname !== '127.0.0.1' || endpoint.protocol !== 'http:') throw new Error('GATEWAY_INVALID');
  const response = await fetch(new URL(path, endpoint), {
    method: 'POST', redirect: 'error', signal,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.HARNESS_DSH_CAPABILITY}` },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error('PLATFORM_REQUEST_REJECTED');
  const value = await response.json();
  return value;
}
class PlatformAdapter extends LlmAdapter {
  nextCrossing = 'm_1';
  async resolveModel(provider, model) {
    if (provider !== 'harness-platform' || model !== process.env.HARNESS_DSH_MODEL) throw new Error('MODEL_ROUTE_INVALID');
    return { provider, id: model, name: model, contextWindow: 64000 };
  }
  async *stream(options) {
    const receipt = await request('/model', { crossing_id: this.nextCrossing, request: {
      model: options.model, messages: options.messages, tools: options.tools || [],
      maxTokens: options.maxTokens, purpose: options.purpose || 'primary',
    } }, options.signal);
    this.nextCrossing = receipt.next_model_crossing;
    const result = receipt.value;
    let index = 0;
    if (result.text) {
      yield { type: 'block-start', index, blockType: 'text' };
      yield { type: 'text-delta', index, text: result.text };
      yield { type: 'block-end', index: index++, block: { type: 'text', text: result.text } };
    }
    for (const call of result.tool_calls) {
      yield { type: 'block-start', index, blockType: 'tool-call' };
      yield { type: 'tool-call-delta', index, id: call.id, name: call.name, argumentsDelta: call.arguments };
      yield { type: 'block-end', index: index++, block: { type: 'tool-call', id: call.id, name: call.name, arguments: call.arguments } };
    }
    yield { type: 'usage', usage: result.usage };
    yield { type: 'finish', reason: { kind: result.tool_calls.length ? 'tool-calls' : 'stop' } };
  }
}
const SLOT = {
  type: 'object', additionalProperties: false, required: true,
  properties: {
    status: { type: 'string', enum: ['supported', 'unknown', 'conflicting'], required: true },
    claim: { type: 'string', required: true, description: 'Short claim; empty when unknown.' },
    quotes: { type: 'array', required: true, description: 'Literal excerpts copied from clauses you read.',
      items: { type: 'object', additionalProperties: false, properties: {
        clause_id: { type: 'string', required: true }, text: { type: 'string', required: true } } } },
  },
};
export const TOOLS = {
  search_document: {
    description: 'Literal substring search over the supplied document (ignores whitespace, case and full/half width). Returns at most 3 platform clause IDs per page '
      + 'with total and next_offset; a page is NOT full coverage. Use offset to read further pages.',
    parameters: { query: { type: 'string', required: true, description: 'literal text, not a regex' },
      offset: { type: 'integer', description: 'page offset from next_offset; default 0' } },
  },
  read_clause: {
    description: 'Read one platform-issued clause ID (evidence block number, not the contract article number). No filesystem access.',
    parameters: { clause_id: { type: 'string', required: true, description: 'e.g. clause-3' } },
  },
  submit_findings: {
    description: 'Submit payment-terms findings for platform verification before your final answer. Each quote must be '
      + 'copied verbatim from a clause you read in this run. Use status unknown when evidence is missing; do not guess.',
    parameters: { term: SLOT, trigger: SLOT, exception: SLOT, conflict: SLOT,
      gaps: { type: 'array', items: { type: 'string' }, description: 'What you could not verify.' } },
  },
};
export function apply(ctx) {
  ctx.llm.registerAdapter(['harness-platform'], new PlatformAdapter());
  const enabled = (process.env.HARNESS_DSH_TOOLS || 'search_document,read_clause').split(',');
  for (const name of enabled) {
    const spec = TOOLS[name];
    if (!spec) throw new Error('TOOL_NOT_DEFINED');
    ctx.tools.register(defineTool({
      name, description: spec.description, parameters: spec.parameters,
      output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
      async execute(args, exec) {
        const result = await request('/tool', {
          crossing_id: exec.callId, request: { name, arguments: args },
        }, exec.signal);
        return result.text;
      },
    }));
  }
}
