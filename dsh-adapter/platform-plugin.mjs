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
  async resolveModel(provider, model) {
    if (provider !== 'harness-platform' || model !== process.env.HARNESS_DSH_MODEL) throw new Error('MODEL_ROUTE_INVALID');
    return { provider, id: model, name: model, contextWindow: 64000 };
  }
  async *stream(options) {
    const result = await request('/model', {
      model: options.model, messages: options.messages, tools: options.tools || [],
      maxTokens: options.maxTokens, purpose: options.purpose || 'primary',
    }, options.signal);
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
export function apply(ctx) {
  ctx.llm.registerAdapter(['harness-platform'], new PlatformAdapter());
  for (const [name, field, description] of [
    ['search_document', 'query', 'Search the supplied document; returns platform clause IDs and bounded excerpts.'],
    ['read_clause', 'clause_id', 'Read one platform-issued clause ID from the supplied document. No filesystem access.'],
  ]) {
    ctx.tools.register(defineTool({
      name, description,
      parameters: { [field]: { type: 'string', required: true, description: field } },
      output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
      async execute(args, exec) {
        const result = await request('/tool', { name, arguments: args }, exec.signal);
        return result.text;
      },
    }));
  }
}
