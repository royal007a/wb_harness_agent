'use strict';
const $ = id => document.getElementById(id);
let selected = null, generation = 0, timer = null;
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'expired']);
async function api(path, options = {}) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(10000)});
  if (!response.ok) { const value = await response.json(); throw new Error(`${value.error?.code || response.status}：${value.error?.message || '请求失败'}`); }
  return response.json();
}
function label(status) {return ({queued:'排队中',running:'执行中',succeeded:'已完成',failed:'失败',cancelled:'已取消',expired:'已超时'})[status] || status;}
async function history() {
  const data = await api('/api/local/dsh/runs');
  $('history').replaceChildren();
  for (const run of data.items) {
    const button = document.createElement('button'); button.type = 'button';
    button.textContent = `${label(run.status)} · ${run.id.slice(-10)} · ${new Date(run.created_at).toLocaleTimeString()}`;
    if (selected === run.id) button.classList.add('selected');
    button.onclick = () => select(run.id); $('history').append(button);
  }
}
async function select(ident) {
  clearTimeout(timer); selected = ident; const current = ++generation;
  $('result').textContent = ''; $('downloads').replaceChildren(); $('events').replaceChildren();
  $('run-summary').textContent = '读取持久状态…'; $('cancel').hidden = true;
  await refresh(current); void history().catch(showError);
}
function showError(error) {$('form-message').textContent = error.message;}
async function refresh(current) {
  const ident = selected;
  try {
    const [detail, page] = await Promise.all([api(`/api/local/dsh/runs/${ident}`), api(`/api/local/dsh/runs/${ident}/events`)]);
    if (current !== generation || ident !== selected) return;
    const run = detail.run;
    $('run-summary').textContent = `${label(run.status)} · ${detail.mode === 'integration_probe' ? '合成 Provider 联调' : '真实 Provider'}\n${run.id}${run.exit_reason ? ' · ' + run.exit_reason : ''}`;
    $('cancel').hidden = terminal.has(run.status);
    $('metrics').replaceChildren();
    for (const text of [`Token 已用 ${detail.budget?.spent ?? 0}`, `预留 ${detail.budget?.reserved ?? 0}`, `模型调用 ${detail.budget?.calls ?? 0}`, `截止 ${run.effective_limits.timeout_seconds}s`]) {
      const span = document.createElement('span'); span.className = 'metric'; span.textContent = text; $('metrics').append(span);
    }
    $('events').replaceChildren();
    for (const event of page.items.filter(e => e.event_type !== 'dsh.observation')) {
      const li = document.createElement('li'); li.textContent = `${event.sequence} · ${event.event_type}  ${JSON.stringify(event.data)}`; $('events').append(li);
    }
    $('result-note').textContent = detail.mode === 'integration_probe'
      ? '这是合成 Provider 的联调产物，只证明真实 DSH 调用了平台工具，不证明模型分析质量。'
      : '模型分析草稿，请核对原文与引用；系统完成不等于人工审查通过。';
    if (detail.artifacts.length) {
      const artifact = detail.artifacts.find(a => a.name === 'dsh-analysis.txt');
      if (artifact) {
        const response = await fetch(`/api/v1/artifacts/${artifact.id}/content`, {signal: AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error('产物读取失败');
        const text = await response.text();
        if (current !== generation || ident !== selected) return;
        $('result').textContent = text; $('downloads').replaceChildren();
        const a = document.createElement('a'); a.href = `/api/v1/artifacts/${artifact.id}/content?download=true`; a.textContent = '下载分析产物'; $('downloads').append(a);
      }
    }
    const findingsArtifact = detail.artifacts.find(a => a.name === 'dsh-findings.json');
    $('findings').hidden = !findingsArtifact;
    if (findingsArtifact) {
      const response = await fetch(`/api/v1/artifacts/${findingsArtifact.id}/content`, {signal: AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error('核对结果读取失败');
      const record = await response.json();
      if (current !== generation || ident !== selected) return;
      const statusText = {mechanically_checked: '机械校验通过（仍需人工复核）', partial: '部分结果：有未知项或缺口', conflicting: '存在冲突'};
      $('findings-status').textContent = statusText[record.business_status] || record.business_status;
      const slotName = {term: '付款期限', trigger: '触发条件', exception: '例外', conflict: '冲突'};
      const stateName = {supported: '有证据', unknown: '未知', conflicting: '冲突'};
      const table = $('findings-table'); table.replaceChildren();
      for (const [slot, item] of Object.entries(record.findings)) {
        const tr = document.createElement('tr');
        for (const text of [slotName[slot] || slot, stateName[item.status] || item.status, item.claim || '—',
                            item.quotes.map(q => `${q.clause_id}：「${q.text}」`).join('\n') || '—']) {
          const td = document.createElement('td'); td.textContent = text; tr.append(td);
        }
        table.append(tr);
      }
      const gaps = $('findings-gaps'); gaps.replaceChildren();
      const gapName = {EXCEPTION_CANDIDATES_UNREAD: '有付款例外候选未读取', PAYMENT_CLAUSES_UNREAD: '有付款相关证据块未读取',
                       EXCEPTION_CANDIDATE_NOT_REPORTED: '读到了例外候选但未报告例外'};
      for (const gap of record.platform_gaps) {
        const li = document.createElement('li'); li.textContent = `平台：${gapName[gap.code] || gap.code}（${gap.clause_ids.join('、')}）`; gaps.append(li);
      }
      for (const gap of record.model_gaps) {
        const li = document.createElement('li'); li.textContent = `模型自述：${gap}`; gaps.append(li);
      }
    }
    if (!terminal.has(run.status)) timer = setTimeout(() => refresh(current), 800);
    else void history().catch(showError);
  } catch (error) { if (current === generation) {showError(error); $('run-summary').textContent = '读取失败，未确认终态。请重新选择该 Run。';} }
}
$('run-form').onsubmit = async event => {
  event.preventDefault(); $('start').disabled = true; $('form-message').textContent = '';
  try {
    const value = await api('/api/local/dsh/runs', {method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},
      body:JSON.stringify({template:$('template').value,objective:$('objective').value,document:$('document').value,mode:$('mode').value,
        public_data_confirmed:$('public-confirm').checked,token_limit:Number($('tokens').value),timeout_seconds:Number($('timeout').value)})});
    await select(value.initial_run.id);
  } catch (error) {showError(error);} finally {$('start').disabled = false;}
};
$('mode').onchange = () => {$('tokens').value = $('mode').value === 'real_provider' ? '20000000' : '200000';};
$('cancel').onclick = async () => {
  const ident = selected, current = generation; $('cancel').disabled = true;
  try {await api(`/api/local/dsh/runs/${ident}/cancel`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); if (current === generation) await refresh(current);}
  catch (error) {showError(error);} finally {$('cancel').disabled = false;}
};
async function init() {
  const status = await api('/api/local/dsh/runtime');
  $('runtime-state').textContent = status.installed ? '官方 DSH 运行时已安装 · 独立本地实例' : 'DSH 依赖未就绪';
  $('runtime-info').textContent = `${status.runtime} | 真实 Provider：${status.real_provider_enabled ? '已配置开关，仍需调用验证' : '未准入'} | 工具：${status.tools.join(' / ')}`;
  $('version').textContent = `分支 dsh/local-runtime-20261005 · 提交 ${status.release} · 与原 8765 / 132 隔离`;
  // Spending real-provider quota always requires an explicit user selection.
  $('mode').value = 'integration_probe'; $('tokens').value = '200000';
  await history();
}
void init().catch(showError);
