"use strict";
const $ = (selector) => document.querySelector(selector);
const state = { providers: [], models: [], agents: [], sessions: [], session: null, controller: null };
const label = { openai_compatible: "OpenAI compatible", anthropic: "Anthropic", ollama: "Ollama" };
let noticeTimer;

function notice(message, error = false) {
  clearTimeout(noticeTimer);
  const target = $("#notice");
  target.textContent = message;
  target.className = error ? "error" : "";
  target.hidden = false;
  noticeTimer = setTimeout(() => (target.hidden = true), 6000);
}
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch {}
    throw new Error(body?.error?.message || `请求失败 (${response.status})`);
  }
  return response.json();
}
function post(url, body, accept = "application/json") {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "Accept": accept, "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
}
function option(select, value, text) {
  const item = document.createElement("option"); item.value = value; item.textContent = text; select.append(item);
}
function profileRow(primary, secondary) {
  const row = document.createElement("article"); row.className = "profile-row";
  const strong = document.createElement("strong"); strong.textContent = primary;
  const small = document.createElement("small"); small.textContent = secondary;
  row.append(strong, small); return row;
}
function renderRuntime(runtime) {
  $("#runtime").textContent = `${runtime.note} 模型、Provider、网络和工具调用均为 0。`;
}
function renderProfiles() {
  const providers = $("#provider-list"); providers.replaceChildren();
  state.providers.forEach((item) => providers.append(profileRow(item.name, `${label[item.type]} · ${item.base_url}`)));
  if (!state.providers.length) providers.append(profileRow("尚无 Provider Profile", "创建后才能添加 Model Profile"));
  const models = $("#model-list"); models.replaceChildren();
  state.models.forEach((item) => models.append(profileRow(item.display_name, `${item.model_id} · ${item.context_window.toLocaleString()} tokens`)));
  if (!state.models.length) models.append(profileRow("尚无 Model Profile", "不会从远端同步模型列表"));
  const agents = $("#agent-list"); agents.replaceChildren();
  state.agents.forEach((item) => agents.append(profileRow(item.name, `${item.max_context_turns} 轮上下文 · 工具绑定 ${item.tool_binding_count}`)));
  if (!state.agents.length) agents.append(profileRow("尚无 Agent Profile", "配置不意味着已启用真实 Agent"));
  for (const [selector, rows, name] of [["#model-provider", state.providers, "name"], ["#agent-model", state.models, "display_name"], ["#session-agent", state.agents, "name"]]) {
    const select = $(selector); const prior = select.value; select.replaceChildren();
    option(select, "", rows.length ? "请选择" : "请先完成上游配置");
    rows.filter((row) => row.enabled).forEach((row) => option(select, row.id, row[name]));
    select.value = prior && [...select.options].some((item) => item.value === prior) ? prior : "";
    select.disabled = !rows.some((row) => row.enabled);
  }
  $("#model-form button").disabled = !state.providers.some((row) => row.enabled);
  $("#agent-form button").disabled = !state.models.some((row) => row.enabled);
  $("#new-session").disabled = !state.agents.some((row) => row.enabled);
}
function renderSessions() {
  const list = $("#session-list"); list.replaceChildren();
  state.sessions.forEach((session) => {
    const button = document.createElement("button"); button.type = "button"; button.className = `session-row ${state.session?.id === session.id ? "selected" : ""}`;
    button.dataset.session = session.id; const title = document.createElement("strong"); title.textContent = session.title;
    const summary = document.createElement("small"); summary.textContent = session.status === "active" ? "本地持久会话" : "已归档";
    button.append(title, summary); list.append(button);
  });
  if (!state.sessions.length) list.append(profileRow("还没有会话", "新建一个会话即可开始"));
}
function scrollIfNearBottom() {
  const box = $("#messages"); const near = box.scrollHeight - box.scrollTop - box.clientHeight < 72;
  if (near) box.scrollTop = box.scrollHeight;
}
function bubble(message) {
  const row = document.createElement("article"); row.className = `bubble ${message.role}`;
  const role = document.createElement("small"); role.textContent = message.role === "user" ? "你" : "LOCAL DEMO";
  const content = document.createElement("div"); content.className = "bubble-content"; content.textContent = message.content;
  row.append(role, content); return row;
}
function renderMessages(messages) {
  const box = $("#messages"); box.replaceChildren(); messages.forEach((message) => box.append(bubble(message))); box.scrollTop = box.scrollHeight;
}
async function chooseSession(id) {
  const detail = await api(`/api/local/agent-lab/sessions/${encodeURIComponent(id)}`); state.session = detail.session; renderSessions();
  renderMessages(detail.messages); $("#chat-empty").hidden = true; $("#messages").hidden = false; $("#chat-form").hidden = false;
}
async function refresh() {
  const [providers, models, agents, sessions] = await Promise.all([api("/api/local/agent-lab/providers"), api("/api/local/agent-lab/models"), api("/api/local/agent-lab/agents"), api("/api/local/agent-lab/sessions")]);
  state.providers = providers.items; state.models = models.items; state.agents = agents.items; state.sessions = sessions.items;
  renderRuntime(providers.runtime); renderProfiles(); renderSessions(); $("#connection").textContent = "控制面已连接";
}
async function submitProfile(event, path) {
  event.preventDefault(); const form = event.currentTarget; const submit = form.querySelector("button[type=submit]"); submit.disabled = true;
  try { const body = Object.fromEntries(new FormData(form)); ["context_window", "max_output_tokens", "max_context_turns"].forEach((key) => { if (body[key]) body[key] = Number(body[key]); }); if (body.temperature) body.temperature = Number(body.temperature);
    const response = await post(path, body); if (!response.ok) { const data = await response.json(); throw new Error(data?.error?.message || "保存失败"); }
    form.reset(); if (form.id === "agent-form") { form.elements.system_prompt.value = "你是本地 Agent Lab 的演示配置。请清楚说明当前没有连接真实模型。"; form.elements.temperature.value = "0.3"; form.elements.max_output_tokens.value = "1024"; form.elements.max_context_turns.value = "8"; }
    if (form.id === "model-form") form.elements.context_window.value = "32768"; if (form.id === "provider-form") form.elements.base_url.value = "https://example.invalid";
    await refresh(); notice("配置已保存；未发起任何外部连接。");
  } finally { submit.disabled = false; }
}
function parseSseChunk(buffer, onEvent) {
  const parts = buffer.split("\n\n"); const rest = parts.pop();
  parts.forEach((part) => { const line = part.split("\n").find((item) => item.startsWith("data: ")); if (line) onEvent(JSON.parse(line.slice(6))); }); return rest;
}
async function sendMessage(event) {
  event.preventDefault(); if (!state.session || state.controller) return;
  const input = $("#chat-input"); const content = input.value.trim(); if (!content) return;
  const send = $("#send"), stop = $("#stop"), box = $("#messages"); input.value = ""; send.disabled = true; stop.hidden = false;
  box.append(bubble({ role: "user", content })); const assistant = bubble({ role: "assistant", content: "正在建立本地 SSE 流…" }); const target = assistant.querySelector(".bubble-content"); box.append(assistant); scrollIfNearBottom();
  state.controller = new AbortController();
  try {
    const response = await fetch(`/api/local/agent-lab/sessions/${encodeURIComponent(state.session.id)}/messages`, { method: "POST", signal: state.controller.signal, headers: { "Content-Type": "application/json", "Accept": "text/event-stream", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ content }) });
    if (!response.ok || !response.body) { let data = {}; try { data = await response.json(); } catch {} throw new Error(data?.error?.message || "流式请求失败"); }
    target.textContent = ""; const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let done = false;
    while (!done) { const result = await reader.read(); if (result.done) break; buffer = parseSseChunk(buffer + decoder.decode(result.value, { stream: true }), (message) => { if (message.type === "delta") { target.textContent += message.content; scrollIfNearBottom(); } else if (message.type === "error") throw new Error("本地流式响应失败。"); else if (message.type === "done") done = true; }); }
    await chooseSession(state.session.id); notice("本地 SSE 流完成；模型调用仍为 0。");
  } catch (error) { target.textContent = error.name === "AbortError" ? "本地显示已停止；持久化演示消息可在刷新后查看。" : `发送失败：${error.message}`; notice(error.message || "流式请求失败", true); }
  finally { state.controller = null; input.disabled = false; send.disabled = false; stop.hidden = true; input.focus(); }
}
function guard(handler) { return async (event) => { try { await handler(event); } catch (error) { notice(error.message || "操作失败", true); } }; }
$("#provider-form").addEventListener("submit", guard((event) => submitProfile(event, "/api/local/agent-lab/providers")));
$("#model-form").addEventListener("submit", guard((event) => submitProfile(event, "/api/local/agent-lab/models")));
$("#agent-form").addEventListener("submit", guard((event) => submitProfile(event, "/api/local/agent-lab/agents")));
$("#new-session").addEventListener("click", guard(async () => { const agent_profile_id = $("#session-agent").value; if (!agent_profile_id) throw new Error("请先选择 Agent Profile。"); const response = await post("/api/local/agent-lab/sessions", { agent_profile_id }); if (!response.ok) { const data = await response.json(); throw new Error(data?.error?.message || "创建会话失败"); } const session = await response.json(); await refresh(); await chooseSession(session.id); notice("已创建本地会话。"); }));
$("#session-list").addEventListener("click", guard(async (event) => { const button = event.target.closest("[data-session]"); if (button) await chooseSession(button.dataset.session); }));
$("#chat-form").addEventListener("submit", guard(sendMessage));
$("#stop").addEventListener("click", () => state.controller?.abort());
refresh().catch((error) => { $("#connection").textContent = "连接中断"; notice(error.message, true); });
