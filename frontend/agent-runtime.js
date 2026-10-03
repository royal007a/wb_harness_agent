"use strict";
const API = "/api/local/agent-runtime";
const $ = (value) => document.querySelector(value);
const state = { providers: [], models: [], agents: [], sessions: [], session: null, controller: null,
  sendingSessionId: null, detailController: null, transportIssues: new Map(),
  selectedSessionId: null, selectionGeneration: 0, pendingSelectionCount: 0 };
let noticeTimer;

function notice(text, error = false) { clearTimeout(noticeTimer); const node = $("#notice"); node.textContent = text; node.className = error ? "error" : ""; node.hidden = false; noticeTimer = setTimeout(() => { node.hidden = true; }, 6500); }
async function api(path, options = {}) { const response = await fetch(HarnessURLs.url(`${API}${path}`), options); if (!response.ok) { let body = {}; try { body = await response.json(); } catch {} throw new Error(body?.error?.message || `请求失败 (${response.status})`); } return response.json(); }
function post(path, body, accept = "application/json") { return fetch(HarnessURLs.url(`${API}${path}`), { method: "POST", headers: { "Content-Type": "application/json", Accept: accept, "Idempotency-Key": HarnessURLs.requestId() }, body: JSON.stringify(body) }); }
function profile(primary, detail, stateText = "") { const item = document.createElement("article"); item.className = "profile"; const strong = document.createElement("strong"); strong.textContent = primary; const small = document.createElement("small"); small.textContent = detail; item.append(strong, small); if (stateText) { const status = document.createElement("span"); status.textContent = stateText; item.append(status); } return item; }
function option(select, value, text) { const node = document.createElement("option"); node.value = value; node.textContent = text; select.append(node); }
function bindSelect(selector, rows, label) { const select = $(selector); const prior = select.value; select.replaceChildren(); option(select, "", rows.length ? "请选择" : "请先完成上游配置"); rows.filter((row) => row.enabled).forEach((row) => option(select, row.id, row[label])); select.value = [...select.options].some((row) => row.value === prior) ? prior : ""; select.disabled = !rows.some((row) => row.enabled); }
function runtimeView(runtime) { const enabled = runtime.runtime_enabled; $("#runtime-badge").textContent = enabled ? "● RUNTIME GATE ENABLED" : "● EXTERNAL MODEL DISABLED"; $("#runtime-badge").className = enabled ? "enabled" : "blocked"; $("#runtime").textContent = `${runtime.note} 当前统计：模型 ${runtime.model_calls}、Provider ${runtime.provider_calls}、网络 ${runtime.network_calls}、工具绑定 ${runtime.tool_binding_count}。`; }
async function renderProfiles() { const providers = $("#provider-list"); providers.replaceChildren(); for (const row of state.providers) { const ready = await api(`/providers/${encodeURIComponent(row.id)}/readiness`); providers.append(profile(row.name, `${row.type} · ${row.base_url}`, ready.state)); } if (!state.providers.length) providers.append(profile("尚无 Provider", "先建立无密连接描述")); const models = $("#model-list"); models.replaceChildren(); state.models.forEach((row) => models.append(profile(row.display_name, `${row.model_id} · ${row.context_window.toLocaleString()} tokens`))); if (!state.models.length) models.append(profile("尚无 Model", "Provider 建立后可配置")); const agents = $("#agent-list"); agents.replaceChildren(); state.agents.forEach((row) => agents.append(profile(row.name, `${row.max_context_turns} 轮上下文 · 工具绑定 ${row.tool_binding_count}`))); if (!state.agents.length) agents.append(profile("尚无 Agent", "模型建立后可配置")); bindSelect("#model-provider", state.providers, "name"); bindSelect("#agent-model", state.models, "display_name"); bindSelect("#session-agent", state.agents, "name"); $("#model-form button").disabled = !state.providers.some((row) => row.enabled); $("#agent-form button").disabled = !state.models.some((row) => row.enabled); $("#new-session").disabled = !state.agents.some((row) => row.enabled); }
function renderSessions() { const target = $("#session-list"); target.replaceChildren(); state.sessions.forEach((row) => { const button = document.createElement("button"); button.type = "button"; button.dataset.session = row.id; button.className = state.selectedSessionId === row.id ? "selected" : ""; const name = document.createElement("strong"); name.textContent = row.title; const detail = document.createElement("small"); detail.textContent = row.status === "active" ? "持久会话" : "已归档"; button.append(name, detail); target.append(button); }); if (!state.sessions.length) target.append(profile("还没有会话", "选择 Agent 后新建会话")); }
function bubble(message) { const node = document.createElement("article"); node.className = `bubble ${message.role}`; const role = document.createElement("small"); role.textContent = message.role === "user" ? "你" : "ASSISTANT"; const content = document.createElement("div"); content.textContent = message.content; node.append(role, content); return node; }
function exchangeStatus(exchange) {
  const labels = { queued: "排队中", streaming: "生成中", succeeded: "已完成", failed: "失败", cancelled: "已取消" };
  const node = document.createElement("article");
  node.className = "exchange-status";
  node.dataset.status = exchange.status;
  node.dataset.exchange = exchange.id;
  node.setAttribute("role", "status");
  const title = document.createElement("strong");
  title.textContent = `请求状态：${labels[exchange.status] || exchange.status}`;
  const detail = document.createElement("small");
  detail.textContent = `Exchange ${exchange.id} · 已记录尝试：模型 ${exchange.model_calls ?? 0} / Provider ${exchange.provider_calls ?? 0}`;
  node.append(title, detail);
  if (exchange.error_code) {
    const error = document.createElement("div");
    error.textContent = `未生成回答：${exchange.error_code}`;
    node.append(error);
  }
  return node;
}
function renderMessages(messages, exchanges) {
  const box = $("#messages"), rendered = new Set();
  box.replaceChildren();
  messages.forEach((item) => {
    box.append(bubble(item));
    exchanges.filter((exchange) => exchange.user_message_id === item.id).forEach((exchange) => {
      box.append(exchangeStatus(exchange));
      rendered.add(exchange.id);
    });
  });
  // Legacy/incomplete history must not silently hide an unassociated Exchange.
  exchanges.filter((exchange) => !rendered.has(exchange.id)).forEach((exchange) => box.append(exchangeStatus(exchange)));
  const issue = state.transportIssues.get(state.selectedSessionId);
  if (issue) box.append(transportStatus(issue));
  box.scrollTop = box.scrollHeight;
}
function updateComposer() {
  $("#send").disabled = !state.session || !!state.controller;
  const ownsStream = state.controller && state.selectedSessionId === state.sendingSessionId;
  $("#stop").hidden = !ownsStream || state.controller.signal.aborted;
  let hint = $("#composer-status");
  if (!hint) {
    hint = document.createElement("small"); hint.id = "composer-status";
    hint.setAttribute("role", "status"); $("#chat-form").prepend(hint);
  }
  hint.textContent = state.controller && !ownsStream
    ? "另一个会话正在发送或核对终态；当前页面一次只发送一条，请返回原会话操作停止。" : "";
}
async function chooseSession(id) {
  const retainHistory = id === state.selectedSessionId;
  state.detailController?.abort();
  const detailController = new AbortController();
  state.detailController = detailController;
  const generation = ++state.selectionGeneration;
  const isCurrent = () => generation === state.selectionGeneration && id === state.selectedSessionId;
  const deadline = performance.now() + 5000;
  const timer = setTimeout(() => detailController.abort(), 5000);
  state.pendingSelectionCount += 1;
  state.selectedSessionId = id;
  state.session = null;
  renderSessions();
  if (!retainHistory) $("#messages").replaceChildren();
  $("#messages").hidden = false;
  $("#empty").hidden = true;
  $("#chat-form").hidden = false;
  $("#messages").setAttribute("aria-busy", "true");
  updateComposer();
  try {
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const detail = await api(`/sessions/${encodeURIComponent(id)}`, { signal: detailController.signal });
      if (!isCurrent()) return;
      state.session = detail.session;
      renderMessages(detail.messages, detail.exchanges);
      const active = detail.exchanges.some((item) => ["queued", "streaming"].includes(item.status));
      if (!active || !state.transportIssues.has(id)) return;
      if (attempt === 5 || performance.now() + 500 >= deadline) {
        state.transportIssues.set(id, "尚未确认终态；保留最后读取的持久状态，请稍后重新选择会话核对。");
        renderMessages(detail.messages, detail.exchanges);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (!isCurrent()) return;
    }
  } catch (error) {
    if (isCurrent()) {
      if (error.name === "AbortError") throw new Error("详情读取超时，尚未确认终态，请重新选择会话核对。");
      throw error;
    }
  } finally {
    clearTimeout(timer);
    if (state.detailController === detailController) state.detailController = null;
    state.pendingSelectionCount -= 1;
    if (generation === state.selectionGeneration) $("#messages").setAttribute("aria-busy", "false");
    updateComposer();
  }
}
async function refresh() { const [providers, models, agents, sessions] = await Promise.all([api("/providers"), api("/models"), api("/agents"), api("/sessions")]); state.providers = providers.items; state.models = models.items; state.agents = agents.items; state.sessions = sessions.items; runtimeView(providers.runtime); await renderProfiles(); renderSessions(); $("#connection").textContent = "本地控制面已连接"; }
async function submitProfile(event, path) { event.preventDefault(); const form = event.currentTarget; const button = form.querySelector("button[type=submit]"); button.disabled = true; try { const body = Object.fromEntries(new FormData(form)); ["context_window", "max_output_tokens", "max_context_turns"].forEach((name) => { if (body[name]) body[name] = Number(body[name]); }); if (body.temperature) body.temperature = Number(body.temperature); if (!body.credential_ref) delete body.credential_ref; const response = await post(path, body); if (!response.ok) { const error = await response.json(); throw new Error(error?.error?.message || "保存失败"); } form.reset(); if (form.id === "provider-form") form.elements.base_url.value = "https://example.invalid"; if (form.id === "model-form") form.elements.context_window.value = "32768"; if (form.id === "agent-form") { form.elements.system_prompt.value = "你是一个审慎的研究助手。只基于可用事实回答，并明确不确定性。"; form.elements.temperature.value = "0.3"; form.elements.max_output_tokens.value = "1024"; form.elements.max_context_turns.value = "8"; } await refresh(); notice("配置已保存；没有发起外部网络连接。"); } finally { button.disabled = false; } }
function parseSse(buffer, callback) { const parts = buffer.split(/\r?\n\r?\n/); const rest = parts.pop(); parts.forEach((part) => { const line = part.split(/\r?\n/).find((value) => value.startsWith("data:")); if (line) callback(JSON.parse(line.replace(/^data:\s*/, ""))); }); return rest; }
function scrollNearBottom() { const box = $("#messages"); if (box.scrollHeight - box.scrollTop - box.clientHeight < 90) box.scrollTop = box.scrollHeight; }
function transportStatus(text) {
  const node = document.createElement("article");
  node.className = "exchange-status transient";
  node.setAttribute("role", "status");
  node.textContent = text;
  return node;
}
async function sendMessage(event) {
  event.preventDefault();
  if (!state.session || state.controller) return;
  const input = $("#chat-input"), content = input.value.trim();
  if (!content) return;
  const sessionId = state.session.id, box = $("#messages");
  const controller = new AbortController();
  state.controller = controller;
  state.sendingSessionId = sessionId;
  state.transportIssues.delete(sessionId);
  box.querySelectorAll(".transient").forEach((node) => node.remove());
  updateComposer();
  input.value = "";
  box.append(bubble({ role: "user", content }));
  const preview = transportStatus("正在检查运行时门禁；尚未生成持久回答。");
  box.append(preview);
  scrollNearBottom();
  let reader, transportIssue = null;
  try {
    const response = await fetch(HarnessURLs.url(`${API}/sessions/${encodeURIComponent(sessionId)}/messages`), {
      method: "POST", signal: controller.signal,
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", "Idempotency-Key": HarnessURLs.requestId() },
      body: JSON.stringify({ content }),
    });
    if (!response.ok || !response.body) {
      let body = {};
      try { body = await response.json(); } catch {}
      throw new Error(body?.error?.message || "流式请求失败");
    }
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", partial = "", terminal = false;
    while (!terminal) {
      const result = await reader.read();
      if (result.done) break;
      buffer = parseSse(buffer + decoder.decode(result.value, { stream: true }), (item) => {
        if (terminal) return;
        if (item.type === "delta") {
          partial += item.content;
          preview.textContent = `流中预览（未持久化）：\n${partial}`;
          if (preview.isConnected) scrollNearBottom();
        } else if (item.type === "error") {
          preview.textContent = `系统未生成回答：${item.error_code}`;
          terminal = true;
        } else if (item.type === "done") {
          preview.textContent = "流已结束；正在核对持久记录。";
          terminal = true;
        }
      });
    }
    if (!terminal) throw new Error("连接提前结束，未收到完成状态；不能确认回答已保存。");
  } catch (error) {
    transportIssue = error.name === "AbortError"
      ? "浏览器已停止显示；不代表服务端已确认取消，正在核对持久状态。"
      : `传输失败：${error.message}`;
    state.transportIssues.set(sessionId, transportIssue);
    preview.textContent = transportIssue;
    notice(transportIssue, true);
  } finally {
    if (reader) {
      try { await reader.cancel(); } catch {}
      reader.releaseLock();
    }
    // The send belongs to its original Session, even if the user changed tabs.
    try {
      if (state.selectedSessionId === sessionId) {
        await chooseSession(sessionId);
      }
    } catch (error) {
      state.transportIssues.set(sessionId, `持久状态读取失败：${error.message}`);
      if (state.selectedSessionId === sessionId) {
        box.querySelectorAll(".transient").forEach((node) => node.remove());
        box.append(transportStatus(state.transportIssues.get(sessionId)));
      }
      notice("无法核对持久记录，请重新选择会话。", true);
    } finally {
      state.controller = null;
      state.sendingSessionId = null;
      updateComposer();
      if (state.selectedSessionId === sessionId) input.focus();
    }
  }
}
function stopSelectedStream() {
  if (state.selectedSessionId !== state.sendingSessionId) return;
  state.controller?.abort();
  updateComposer();
}
function guard(handler) { return async (event) => { try { await handler(event); } catch (error) { notice(error.message || "操作失败", true); } }; }
$("#provider-form").addEventListener("submit", guard((event) => submitProfile(event, "/providers"))); $("#model-form").addEventListener("submit", guard((event) => submitProfile(event, "/models"))); $("#agent-form").addEventListener("submit", guard((event) => submitProfile(event, "/agents"))); $("#new-session").addEventListener("click", guard(async () => { const agent_profile_id = $("#session-agent").value; if (!agent_profile_id) throw new Error("请先选择 Agent。"); const response = await post("/sessions", { agent_profile_id }); if (!response.ok) { const body = await response.json(); throw new Error(body?.error?.message || "创建会话失败"); } const session = await response.json(); await refresh(); await chooseSession(session.id); notice("会话已创建。"); })); $("#session-list").addEventListener("click", guard(async (event) => { const button = event.target.closest("[data-session]"); if (button) await chooseSession(button.dataset.session); })); $("#chat-form").addEventListener("submit", guard(sendMessage)); $("#stop").addEventListener("click", stopSelectedStream); refresh().catch((error) => { $("#connection").textContent = "连接中断"; notice(error.message, true); });
