"use strict";
const one = (selector) => document.querySelector(selector);
const terminal = new Set(["succeeded", "failed", "cancelled", "expired"]);
const labels = {queued: "排队中", running: "运行中", succeeded: "已完成", failed: "失败", cancelled: "已取消", expired: "已过期"};
const companies = {demo_a: "演示公司 A", demo_b: "演示公司 B", demo_c: "演示公司 C"};
const roles = {financial: "财务专项", industry: "行业专项", risk: "风险专项"};
let selected = "", detail = null, generation = 0, refreshing = false;

async function api(path, body) {
  const init = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify(body)};
  const response = await fetch(path, init);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || "请求失败");
  return value;
}
function notice(text) { one("#agent-message").textContent = text; }
function text(tag, value) { const node = document.createElement(tag); node.textContent = value; return node; }
function clear(node) { node.replaceChildren(); }
function action(callback) { return async (event) => { try { await callback(event); } catch (error) { notice(error.message); } }; }

async function history() {
  const data = await api("/api/local/research-agents");
  if (!selected && data.items.length) selected = data.items[0].id;
  const select = one("#agent-history"); clear(select);
  if (!data.items.length) select.append(text("option", "暂无运行"));
  for (const run of data.items) {
    const option = text("option", `${labels[run.status]} · ${run.created_at} · #${run.attempt_number}`);
    option.value = run.id; select.append(option);
  }
  select.value = selected;
}
function artifactLinks(artifacts) {
  const target = one("#agent-downloads"); clear(target);
  for (const artifact of artifacts) {
    const link = text("a", `↓ ${artifact.name}`);
    link.className = "artifact-link";
    link.href = `/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content?download=true`;
    target.append(link);
  }
}
function childCards(children) {
  const target = one("#agent-children"); clear(target);
  for (const child of children) {
    const run = child.run, assignment = child.assignment, agent = child.agent;
    const card = document.createElement("article"); card.className = "research-child";
    const status = text("span", labels[run.status]); status.className = `status ${run.status}`; card.append(status);
    card.append(text("h3", `${companies[assignment.company]} / ${roles[assignment.role]}`));
    const agentLine = text("p", `Agent: ${agent.id}\nSkill: ${agent.skill.id}@${agent.skill.version}\nTool: ${agent.allowed_tools.join(", ")}\n步骤上限：${agent.max_turns} · 模型/网络：0 / 0`);
    agentLine.style.whiteSpace = "pre-line"; card.append(agentLine);
    card.append(text("p", `Child Run: ${run.id}\n退出：${run.exit_reason || "—"}`));
    for (const artifact of child.artifacts) {
      const link = text("a", "↓ 已验证 Child 证据"); link.href = `/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content?download=true`; card.append(link);
    }
    if (!terminal.has(run.status)) {
      const button = text("button", "取消该 Child"); button.type = "button"; button.dataset.child = run.id; button.className = "child-cancel"; card.append(button);
    }
    target.append(card);
  }
}
async function refreshDetail() {
  if (!selected) return;
  const runId = selected, ticket = ++generation;
  const [current, events] = await Promise.all([api(`/api/local/research-agents/${encodeURIComponent(runId)}`), api(`/api/v1/runs/${encodeURIComponent(runId)}/events`)]);
  if (selected !== runId || ticket !== generation) return;
  detail = current;
  const run = current.run, request = current.task.context.variables.request;
  const displayStatus = run.exit_reason === "COMPLETED_WITH_WARNINGS" ? "完成 · 有证据缺口" : labels[run.status];
  const status = one("#agent-root-status"); status.textContent = displayStatus; status.className = `status ${run.status}`;
  one("#agent-root-id").textContent = `${run.id} · trace_${run.id.slice(4)}`;
  one("#agent-configuration").textContent = `公司：${request.companies.map((id) => companies[id]).join("、")} · 并发 ${request.concurrency} · 父预算 ${request.max_steps} 步 · Agent / Provider / 网络调用：0 / 0 / 0。`;
  one("#agent-cancel").disabled = terminal.has(run.status); one("#agent-rerun").disabled = !terminal.has(run.status);
  const valid = current.children.filter((child) => child.run.status === "succeeded").length;
  const failed = current.children.filter((child) => ["failed", "cancelled", "expired"].includes(child.run.status)).length;
  one("#agent-summary").textContent = `${current.children.length} 个 Child Agent · ${valid} 个已验证结果 · ${failed} 个失败/取消。风险始终是“未评估”；模型、Provider、网络和外部工具调用均为 0。`;
  artifactLinks(current.artifacts); childCards(current.children);
  const eventList = one("#agent-events"); clear(eventList);
  for (const event of events.items) {
    const item = text("li", `${event.event_type} ${event.data.exit_reason || event.data.coverage || event.data.child_run_id || ""}`); eventList.append(item);
  }
}

one("#agent-form").addEventListener("submit", action(async (event) => {
  event.preventDefault();
  const selectedCompanies = Array.from(document.querySelectorAll('input[name="companies"]:checked')).map((input) => input.value);
  if (!selectedCompanies.length) throw new Error("至少选择一家公司。");
  const button = one("#agent-submit"); button.disabled = true;
  try {
    const response = await api("/api/local/research-agents", {companies: selectedCompanies, concurrency: Number(one("#agent-concurrency").value), failure_policy: one("#agent-failure-policy").value, scenario: one("#agent-scenario").value, timeout_seconds: 60, max_steps: selectedCompanies.length * 6 + 1});
    selected = response.initial_run.id; detail = null; generation += 1; await history(); await refreshDetail(); notice("已创建三角色 Agent 模拟；每个 Child 的 Skill 和工具快照已冻结。");
  } finally { button.disabled = false; }
}));
one("#agent-history").addEventListener("change", action(async () => { selected = one("#agent-history").value; detail = null; generation += 1; await refreshDetail(); }));
one("#agent-cancel").addEventListener("click", action(async () => { if (selected) { await api(`/api/v1/runs/${encodeURIComponent(selected)}:cancel`, {}); await refreshDetail(); } }));
one("#agent-rerun").addEventListener("click", action(async () => { if (!detail) return; const response = await api(`/api/v1/tasks/${encodeURIComponent(detail.task.id)}/runs`, {based_on_run_id: detail.run.id}); selected = response.id; detail = null; generation += 1; await history(); await refreshDetail(); notice("已建立新的完整运行树，旧证据未改写。"); }));
one("#agent-children").addEventListener("click", action(async (event) => { const button = event.target.closest("[data-child]"); if (button) { await api(`/api/v1/runs/${encodeURIComponent(button.dataset.child)}:cancel`, {}); await refreshDetail(); } }));
async function refresh() { if (refreshing) return; refreshing = true; try { await history(); await refreshDetail(); } catch (error) { notice(error.message); } finally { refreshing = false; } }
refresh(); setInterval(refresh, 1000);
