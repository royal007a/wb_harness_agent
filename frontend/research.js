"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const terminal = new Set(["succeeded", "failed", "cancelled", "expired"]);
const labels = {queued:"排队中",running:"运行中",succeeded:"已完成",failed:"失败",cancelled:"已取消",expired:"已过期"};
const companies = {demo_a:"演示公司 A",demo_b:"演示公司 B",demo_c:"演示公司 C"};
const roles = {financial:"财务指标",industry:"行业资料",risk:"风险资料覆盖"};
let selected = "", current = null, generation = 0, refreshing = false;
async function api(path, body) {
  const options = body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || "请求失败");
  return value;
}
function notice(text) { $("#research-message").textContent = text; }
function action(fn) { return async (event) => { try { await fn(event); } catch(error) { notice(error.message); } }; }
async function loadHistory() {
  const data = await api("/api/local/research");
  if (!selected && data.items.length) selected = data.items[0].id;
  $("#research-history").innerHTML = data.items.length ? data.items.map((run) => `<option value="${esc(run.id)}">${esc(labels[run.status])} · ${esc(run.created_at)} · #${run.attempt_number}</option>`).join("") : '<option value="">暂无研究运行</option>';
  $("#research-history").value = selected;
}
async function refreshDetail() {
  if (!selected) return;
  const runId = selected, ticket = ++generation;
  const [detail, events] = await Promise.all([api("/api/local/research/"+runId),api("/api/v1/runs/"+runId+"/events")]);
  if (selected !== runId || ticket !== generation) return;
  current = detail;
  const run = detail.run;
  $("#root-status").textContent = run.exit_reason === "COMPLETED_WITH_WARNINGS" ? "完成 · 有资料缺口" : labels[run.status];
  $("#root-status").className = "status " + run.status;
  $("#root-id").textContent = run.id + " · trace_" + run.id.slice(4);
  const request = detail.task.context.variables.request;
  $("#research-configuration").textContent = `本次配置：${request.companies.map(c=>companies[c]).join("、")} · 并发上限 ${request.concurrency} · 总步骤上限 ${request.max_steps} · ${request.failure_policy === "fail_parent" ? "子失败则父失败" : "允许带缺口汇总"}。`;
  $("#research-cancel").disabled = terminal.has(run.status);
  $("#research-rerun").disabled = !terminal.has(run.status);
  const success = detail.children.filter(c=>c.run.status==="succeeded").length;
  const failures = detail.children.filter(c=>["failed","cancelled","expired"].includes(c.run.status)).length;
  $("#research-summary").textContent = `${detail.children.length} 个子任务 · ${success} 个有效结果 · ${failures} 个失败/取消。模型调用 0 次。风险状态始终为“未评估”，不能将缺失资料解释为无风险。`;
  $("#research-downloads").innerHTML = detail.artifacts.map(a=>`<a class="artifact-link" href="/api/v1/artifacts/${esc(a.id)}/content?download=true">↓ ${esc(a.name)}</a>`).join("");
  $("#research-children").innerHTML = detail.children.map(child=>{
    const c = child.run, a = child.assignment;
    return `<article class="research-child"><span class="status ${esc(c.status)}">${esc(labels[c.status])}</span><h3>${esc(companies[a.company])} / ${esc(roles[a.role])}</h3><p class="mono">${esc(c.id)}</p><p>独立资源：${esc(a.resource_id.slice(0,20))}…<br>步骤上限 ${esc(c.effective_limits.max_turns)} · 仅资源读取<br>退出原因：${esc(c.exit_reason || "—")}</p>${child.artifacts.map(file=>`<a href="/api/v1/artifacts/${esc(file.id)}/content?download=true">↓ 结构化结果与来源</a>`).join("")}${!terminal.has(c.status)?`<button class="child-cancel" data-child="${esc(c.id)}" type="button">取消该子任务</button>`:""}</article>`;
  }).join("");
  $("#research-events").innerHTML = events.items.map(e=>`<li><span class="mono">${esc(e.event_type)}</span> ${esc(e.data.exit_reason || e.data.coverage || e.data.child_run_id || "")}</li>`).join("");
}
$("#research-form").addEventListener("submit",action(async(event)=>{
  event.preventDefault();
  const checked = name => Array.from(document.querySelectorAll(`input[name=${name}]:checked`)).map(e=>e.value);
  const companyIds=checked("companies"), roleIds=checked("roles");
  if (!companyIds.length || !roleIds.length) throw new Error("至少选择一家公司和一个专项。");
  $("#research-submit").disabled=true;
  try {
    const response=await api("/api/local/research",{companies:companyIds,roles:roleIds,concurrency:Number($("#concurrency").value),failure_policy:$("#failure-policy").value,scenario:$("#scenario").value,timeout_seconds:60,max_steps:companyIds.length*roleIds.length+1});
    selected=response.initial_run.id; generation++; current=null;
    await loadHistory(); await refreshDetail(); notice("已创建离线演示任务；每个专项拥有独立输入与结果。");
  } finally { $("#research-submit").disabled=false; }
}));
$("#research-history").addEventListener("change",action(async()=>{selected=$("#research-history").value;generation++;current=null;await refreshDetail();}));
$("#research-cancel").addEventListener("click",action(async()=>{if(selected){await api("/api/v1/runs/"+selected+":cancel",{});await refreshDetail();}}));
$("#research-rerun").addEventListener("click",action(async()=>{
  if(!current)return;
  const task=current.task.id, previous=current.run.id;
  $("#research-rerun").disabled=true;
  const run=await api("/api/v1/tasks/"+task+"/runs",{based_on_run_id:previous});
  selected=run.id;generation++;await loadHistory();await refreshDetail();notice("已创建新的完整运行树，原有证据保留。");
}));
$("#research-children").addEventListener("click",action(async(event)=>{
  const button=event.target.closest("[data-child]");
  if(button){await api("/api/v1/runs/"+button.dataset.child+":cancel",{});await refreshDetail();}
}));
async function refresh(){if(refreshing)return;refreshing=true;try{await loadHistory();await refreshDetail();}catch(error){notice(error.message);}finally{refreshing=false;}}
refresh();setInterval(refresh,1000);
