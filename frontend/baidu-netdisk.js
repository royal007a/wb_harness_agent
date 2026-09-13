"use strict";
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const labels = { not_configured: "未配置", ready: "可授权", authorizing: "授权中", connected: "已连接", error: "异常" };
function notice(message, failed = false) { const node = $("#notice"); node.textContent = message; node.className = failed ? "error-box" : "authorization-link"; node.hidden = false; }
async function api(path, options = {}) { const response = await fetch(path, options); if (!response.ok) { let payload; try { payload = await response.json(); } catch {} throw new Error(payload?.error?.message || `请求失败 (${response.status})`); } return response.json(); }
const post = (path) => api(path, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: "{}" });
function render(status) {
  $("#state-badge").textContent = labels[status.status] || status.status;
  $("#state-badge").className = `status ${status.status}`;
  $("#connection-details").innerHTML = [
    ["应用 App Key", status.client_id_configured ? "已配置（不显示值）" : "未配置"],
    ["授权回调", status.redirect_uri],
    ["凭证引用", status.credential_ref],
    ["本机 token", status.has_token ? "已保存于 Keychain" : "尚未授权"],
    ["文件数据面", status.data_access_enabled ? "已启用" : "未启用"],
  ].map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join("");
  $("#start-authorization").disabled = status.status !== "ready";
  $("#disconnect").hidden = !status.has_token;
}
async function refresh() { try { render(await api("/api/local/connectors/baidu-netdisk")); } catch (error) { notice(error.message, true); } }
$("#start-authorization").addEventListener("click", async () => { try { const result = await post("/api/local/connectors/baidu-netdisk/authorization"); const box = $("#authorization-link"); box.hidden = false; box.innerHTML = `授权链接十分钟内有效。请在新页面自行登录并确认授权：<br><a href="${esc(result.authorization_url)}" target="_blank" rel="noopener">打开百度官方授权页 ↗</a>`; await refresh(); } catch (error) { notice(error.message, true); } });
$("#disconnect").addEventListener("click", async () => { try { render(await post("/api/local/connectors/baidu-netdisk:disconnect")); $("#authorization-link").hidden = true; notice("本机 OAuth token 已从 Keychain 删除。"); } catch (error) { notice(error.message, true); } });
refresh();
