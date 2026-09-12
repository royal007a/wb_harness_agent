"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const state = {
  tasks: [],
  resources: [],
  task: null,
  run: null,
  tab: "overview",
  events: [],
  cursor: 0,
  generation: 0,
  resultKey: null,
  busy: false,
};
const labels = {
  queued: "排队中",
  running: "运行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  expired: "已超时",
};
const live = (r) => r && ["queued", "running"].includes(r.status);
const stamp = (v) =>
  new Date(v).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
let noticeTimer;
function notice(message, error = false) {
  clearTimeout(noticeTimer);
  $("#notice").textContent = message;
  $("#notice").className = error ? "error" : "";
  $("#notice").hidden = false;
  noticeTimer = setTimeout(() => ($("#notice").hidden = true), 6000);
}
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {}
    throw new Error(data?.error?.message || `请求失败 (${response.status})`);
  }
  return response.json();
}
const post = (url, body) =>
  api(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(body),
  });
function badge(status) {
  return `<span class="status ${esc(status)}">${esc(labels[status] || status)}</span>`;
}
function renderTasks() {
  const filter = $("#filter").value;
  const rows = state.tasks.filter(
    (t) =>
      filter === "all" ||
      (filter === "running"
        ? live(t.latest_run)
        : t.latest_run?.status === filter),
  );
  $("#task-count").textContent = state.tasks.length;
  $("#count-total").textContent = state.tasks.length;
  $("#count-running").textContent = state.tasks.filter((t) =>
    live(t.latest_run),
  ).length;
  $("#count-success").textContent = state.tasks.filter(
    (t) => t.latest_run?.status === "succeeded",
  ).length;
  $("#task-list").innerHTML = rows.length
    ? rows
        .map(
          ({ task, latest_run: r }) =>
            `<button class="task-row ${state.task?.id === task.id ? "selected" : ""}" data-task="${esc(task.id)}"><span class="task-icon">${r?.status === "succeeded" ? "✓" : "⌁"}</span><span class="task-info"><strong>${esc(task.objective)}</strong><small>${esc(stamp(task.created_at))} &nbsp;·&nbsp; Local Analytics &nbsp;·&nbsp; #${r?.attempt_number || 1}</small></span>${badge(r?.status || "queued")}</button>`,
        )
        .join("")
    : '<div class="empty"><span>▤</span><h3>从第一份数据开始</h3><p>选择左侧示例数据，创建你的第一个分析。<br>运行记录将在这里持续保存。</p></div>';
}
async function refreshResources() {
  const data = await api("/api/v1/resources");
  state.resources = data.items;
  const previous = $("#resource-select").value;
  $("#resource-select").innerHTML =
    '<option value="">请选择数据资源</option>' +
    data.items
      .map(
        (r) =>
          `<option value="${esc(r.id)}">${esc(r.name)} · ${r.row_count} 行</option>`,
      )
      .join("");
  $("#resource-select").value = previous;
  $("#resource-table").innerHTML = data.items.length
    ? "<table><thead><tr><th>文件</th><th>数据量</th><th>编码</th><th>版本 / SHA-256</th></tr></thead><tbody>" +
      data.items
        .map(
          (r) =>
            `<tr><td>${esc(r.name)}</td><td>${r.row_count} 行 · ${r.columns.length} 列</td><td>${esc(r.encoding)}</td><td><small>${esc(r.sha256)}</small></td></tr>`,
        )
        .join("") +
      "</tbody></table>"
    : '<div class="empty"><h3>暂无数据资源</h3><p>请在分析工作台上传 CSV。</p></div>';
}
async function upload(file) {
  if (file.size > 2 * 1024 * 1024) throw new Error("文件超过 2 MiB 限制。");
  $("#upload-title").textContent = "正在读取并验证…";
  try {
    const r = await api(
      "/api/v1/resources?name=" + encodeURIComponent(file.name),
      { method: "POST", headers: { "Content-Type": "text/csv" }, body: file },
    );
    await refreshResources();
    $("#resource-select").value = r.id;
    $("#upload-title").textContent = r.name;
    $("#upload-subtitle").textContent =
      `${r.row_count} 行 · ${r.columns.length} 列 · 已保存`;
    notice("数据已验证并保存。");
  } catch (e) {
    $("#upload-title").textContent = "选择或拖入 CSV 文件";
    $("#upload-subtitle").textContent = "UTF-8 / GB18030 · 最多 20,000 行";
    throw e;
  }
}
async function chooseTask(id, runId = null) {
  const generation = ++state.generation;
  const data = await api("/api/v1/tasks/" + id);
  if (generation !== state.generation) return;
  state.task = data.task;
  state.run = data.runs.find((r) => r.id === runId) || data.runs[0];
  state.events = [];
  state.cursor = 0;
  state.resultKey = null;
  $("#run-select").innerHTML = data.runs
    .map(
      (r) =>
        `<option value="${esc(r.id)}">第 ${r.attempt_number} 次 · ${esc(labels[r.status])}</option>`,
    )
    .join("");
  $("#run-select").value = state.run.id;
  $("#detail-empty").hidden = true;
  $("#detail").hidden = false;
  renderTasks();
  await refreshRun(generation);
}
async function refreshRun(generation = state.generation) {
  if (!state.run) return;
  const runId = state.run.id;
  const [run, eventData] = await Promise.all([
    api("/api/v1/runs/" + runId),
    api(`/api/v1/runs/${runId}/events?after=${state.cursor}`),
  ]);
  if (generation !== state.generation || runId !== state.run?.id) return;
  state.run = run;
  const known = new Set(state.events.map((e) => e.event_id));
  state.events.push(...eventData.items.filter((e) => !known.has(e.event_id)));
  state.cursor = eventData.next_cursor;
  $("#detail-title").textContent = state.task.objective;
  $("#run-meta").textContent =
    `${run.id} · ${labels[run.status]} · ${stamp(run.created_at)}`;
  $("#cancel").disabled = !live(run);
  $("#run-select").selectedOptions[0].textContent =
    `第 ${run.attempt_number} 次 · ${labels[run.status]}`;
  $("#event-count").textContent = state.events.length;
  $("#tab-events").innerHTML = state.events
    .map(
      (e) =>
        `<div class="event"><small>#${e.sequence}</small><div class="event-type">${esc(e.event_type)}<br><small>${esc(stamp(e.occurred_at))}</small></div><pre>${esc(JSON.stringify(e.data, null, 2))}</pre></div>`,
    )
    .join("");
  $("#tab-policy").innerHTML =
    '<p class="form-hint">本地单用户模式 · 禁止外部模型与任意代码 · 固定统计工具</p><pre class="policy-block">' +
    esc(
      JSON.stringify(
        {
          engine: run.selected_engine,
          models: run.selected_models,
          permissions: run.effective_permissions,
          limits: run.effective_limits,
          trace_id: "trace_" + run.id.slice(4),
        },
        null,
        2,
      ),
    ) +
    "</pre>";
  const key = run.id + ":" + run.status;
  if (state.resultKey === key) return;
  if (run.status === "succeeded") {
    const items = (await api(`/api/v1/runs/${run.id}/artifacts`)).items;
    const manifest = items.find((a) => a.name === "analysis-manifest.json");
    const report = items.find((a) => a.name === "report.md");
    const chart = items.find((a) => a.media_type === "image/svg+xml");
    const [data, reportText] = await Promise.all([
      api(`/api/v1/artifacts/${manifest.id}/content`),
      fetch(`/api/v1/artifacts/${report.id}/content`).then((r) => {
        if (!r.ok) throw new Error("报告读取失败");
        return r.text();
      }),
    ]);
    if (generation !== state.generation || runId !== state.run?.id) return;
    const m = data.metrics;
    $("#tab-overview").innerHTML =
      `<div class="artifact-links">${items.map((a) => `<a class="artifact-link" href="/api/v1/artifacts/${a.id}/content?download=true">↓ ${esc(a.name)}<small>验证通过 · ${(a.size_bytes / 1024).toFixed(1)} KB</small></a>`).join("")}</div><div class="result-grid"><div class="result-stat">数据行<strong>${m.row_count}</strong></div><div class="result-stat">字段数<strong>${m.column_count}</strong></div><div class="result-stat">缺失单元格<strong>${m.missing_cells}</strong></div></div><img class="chart" src="/api/v1/artifacts/${chart.id}/content" alt="各字段的数据完整率柱状图"><details><summary>查看完整 Markdown 报告</summary><pre class="report">${esc(reportText)}</pre></details>`;
  } else if (live(run)) {
    $("#tab-overview").innerHTML =
      '<div class="empty"><span>⌁</span><h3>正在处理数据</h3><p>检查输入 → 计算统计 → 校验并发布产物<br>可切换到执行事件查看进度。</p></div>';
  } else {
    $("#tab-overview").innerHTML =
      `<div class="error-box">${esc(labels[run.status])} · ${esc(run.exit_reason || "UNKNOWN")}<p>该次运行没有发布成功产物。可检查事件，或创建一次新的运行。</p></div>`;
  }
  state.resultKey = key;
}
async function refresh() {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api("/api/v1/tasks");
    state.tasks = data.items;
    renderTasks();
    await refreshRun();
    $("#connection").textContent = "控制面已连接";
  } catch (e) {
    $("#connection").textContent = "连接中断 · 自动重试";
  } finally {
    state.busy = false;
  }
}
function guard(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      notice(e.message, true);
    }
  };
}
$("#csv-file").addEventListener(
  "change",
  guard(async (e) => {
    if (e.target.files[0]) await upload(e.target.files[0]);
  }),
);
$("#dropzone").addEventListener("dragover", (e) => {
  e.preventDefault();
  $("#dropzone").classList.add("drag");
});
$("#dropzone").addEventListener("dragleave", () =>
  $("#dropzone").classList.remove("drag"),
);
$("#dropzone").addEventListener(
  "drop",
  guard(async (e) => {
    e.preventDefault();
    $("#dropzone").classList.remove("drag");
    if (e.dataTransfer.files[0]) await upload(e.dataTransfer.files[0]);
  }),
);
$("#sample").addEventListener(
  "click",
  guard(async () => {
    const r = await fetch("/api/local/sample");
    if (!r.ok) throw new Error("示例加载失败");
    await upload(new File([await r.blob()], "sales.csv", { type: "text/csv" }));
  }),
);
$("#create-form").addEventListener(
  "submit",
  guard(async (e) => {
    e.preventDefault();
    const resource = $("#resource-select").value;
    if (!resource) throw new Error("请先上传或选择一份 CSV。");
    $("#submit").disabled = true;
    try {
      const result = await post("/api/local/tasks", {
        resource_id: resource,
        objective: $("#objective").value.trim(),
      });
      await refresh();
      await chooseTask(result.task.id);
      notice("分析任务已创建。");
    } finally {
      $("#submit").disabled = false;
    }
  }),
);
$("#task-list").addEventListener(
  "click",
  guard(async (e) => {
    const b = e.target.closest("[data-task]");
    if (b) await chooseTask(b.dataset.task);
  }),
);
$("#filter").addEventListener("change", renderTasks);
$("#run-select").addEventListener(
  "change",
  guard(async (e) => chooseTask(state.task.id, e.target.value)),
);
$("#cancel").addEventListener(
  "click",
  guard(async () => {
    if (!state.run) return;
    await api(`/api/v1/runs/${state.run.id}:cancel`, { method: "POST" });
    await refresh();
    notice("取消请求已处理。");
  }),
);
$("#rerun").addEventListener(
  "click",
  guard(async () => {
    if (!state.task) return;
    $("#rerun").disabled = true;
    try {
      const r = await post(`/api/v1/tasks/${state.task.id}/runs`, {
        based_on_run_id: state.run.id,
        reason: "user_retry",
      });
      await chooseTask(state.task.id, r.id);
      await refresh();
      notice("已创建新的 Run，历史记录已保留。");
    } finally {
      $("#rerun").disabled = false;
    }
  }),
);
document.querySelectorAll("[data-tab]").forEach((b) =>
  b.addEventListener("click", () => {
    state.tab = b.dataset.tab;
    document.querySelectorAll("[data-tab]").forEach((t) => {
      t.classList.toggle("selected", t === b);
      t.setAttribute("aria-selected", String(t === b));
    });
    document
      .querySelectorAll(".tab-content")
      .forEach((t) => (t.hidden = t.id !== "tab-" + state.tab));
  }),
);
document.querySelectorAll("[data-page]").forEach((b) =>
  b.addEventListener(
    "click",
    guard(async () => {
      document
        .querySelectorAll("[data-page]")
        .forEach((n) => n.classList.toggle("active", n === b));
      document
        .querySelectorAll(".page")
        .forEach((p) => (p.hidden = p.id !== "page-" + b.dataset.page));
      $("#breadcrumb").textContent = b.querySelector("span").textContent;
      if (b.dataset.page === "resources") await refreshResources();
    }),
  ),
);
guard(async () => {
  await refreshResources();
  const engines = await api("/api/v1/engines");
  $("#engines").innerHTML = engines.items
    .map(
      (e) =>
        `<article class="engine-card"><span class="status ${e.status === "available" ? "succeeded" : ""}">${e.status === "available" ? "可用" : "规划中"}</span><h2>${esc(e.name)}</h2><p>${esc(e.description)}</p><small class="mono">${esc(e.id)}</small></article>`,
    )
    .join("");
  await refresh();
  if (state.tasks.length) await chooseTask(state.tasks[0].task.id);
})();
setInterval(refresh, 1000);
