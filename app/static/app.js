const state = {
  status: null,
  view: "llm",
  providers: [],
  selectedProviderId: null,
  providerDetail: null,
  generic: [],
  selectedGenericCategory: null,
  testSettings: null,
  testingProviderId: null,
  refreshingModelsProviderId: null,
  backendOnline: true,
};

const formatLabels = {
  openai_chat_completion: "OpenAI Chat Completions",
  openai_response: "OpenAI Response",
  anthropic_message: "Anthropic Messages",
};

const iconCodes = {
  add: "\uf067",
  copy: "\uf0c5",
  database: "\uf1c0",
  delete: "\uf1f8",
  download: "\uf019",
  edit: "\uf044",
  export: "\uf56e",
  import: "\uf56f",
  info: "\uf05a",
  lock: "\uf023",
  open: "\uf35d",
  refresh: "\uf2f1",
  save: "\uf0c7",
  sort: "\uf0dc",
};

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");
const modalRoot = document.getElementById("modal-root");
let orderDraft = null;
let confirmResolver = null;
let connectionTimer = null;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  await loadStatus().catch((error) => showToast(error.message || "无法连接后端服务", 5000));
  connectionTimer = setInterval(checkBackendConnection, 5000);
  render();
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (error) {
    state.backendOnline = false;
    const message = "无法连接后端服务。请确认程序仍在运行，然后刷新页面或重试操作。";
    const wrapped = new Error(message);
    wrapped.isConnectionError = true;
    throw wrapped;
  }
  state.backendOnline = true;
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error("后端响应不是有效数据，请检查服务状态。");
  }
  if (!payload.ok) throw new Error(payload.error || "请求失败");
  return payload.data;
}

function jsonOptions(method, data) {
  return { method, body: JSON.stringify(data || {}) };
}

async function loadStatus() {
  state.status = await api("/api/status");
}

async function checkBackendConnection() {
  try {
    const response = await fetch("/api/status", { headers: { "Content-Type": "application/json" } });
    const payload = await response.json();
    if (!payload.ok) throw new Error("状态接口异常");
    const wasOffline = !state.backendOnline;
    state.backendOnline = true;
    state.status = payload.data;
    if (wasOffline) {
      showToast("后端连接已恢复");
      render();
    }
  } catch (error) {
    const wasOnline = state.backendOnline;
    state.backendOnline = false;
    if (wasOnline) {
      showToast("无法连接后端服务。请确认程序仍在运行。", 6000);
      render();
    }
  }
}

async function loadProviders() {
  state.providers = await api("/api/providers");
  if (!state.selectedProviderId && state.providers.length) state.selectedProviderId = state.providers[0].id;
  if (state.selectedProviderId && state.providers.some((item) => item.id === state.selectedProviderId)) {
    await loadProviderDetail(state.selectedProviderId);
  } else {
    state.selectedProviderId = state.providers[0] ? state.providers[0].id : null;
    state.providerDetail = state.selectedProviderId ? await api(`/api/providers/${state.selectedProviderId}`) : null;
  }
}

async function loadProviderDetail(providerId) {
  state.selectedProviderId = providerId;
  state.providerDetail = await api(`/api/providers/${providerId}`);
}

async function loadGeneric() {
  state.generic = await api("/api/generic");
  if (!state.selectedGenericCategory && state.generic.length) {
    state.selectedGenericCategory = state.generic[0].category;
  }
  if (state.selectedGenericCategory && !state.generic.some((group) => group.category === state.selectedGenericCategory)) {
    state.selectedGenericCategory = state.generic[0] ? state.generic[0].category : null;
  }
}

async function loadTestSettings() {
  state.testSettings = await api("/api/settings/test");
}

function render() {
  if (!state.status && !state.backendOnline) {
    renderOffline();
    return;
  }
  if (!state.status || !state.status.unlocked) {
    renderAuth();
    return;
  }
  app.innerHTML = `
    <div class="app-shell">
      <header class="titlebar">
        <h1>APIKEY管理器</h1>
        <nav class="nav">
          <button class="${state.view === "llm" ? "active" : ""}" onclick="switchView('llm')">大模型</button>
          <button class="${state.view === "generic" ? "active" : ""}" onclick="switchView('generic')">通用密钥</button>
          <button class="${state.view === "settings" ? "active" : ""}" onclick="switchView('settings')">设置</button>
        </nav>
        <div class="toolbar">
          ${renderConnectionStatus()}
          ${iconButton({ label: "锁定", iconName: "lock", onclick: "lockApp()", text: true })}
        </div>
      </header>
      <div class="main-layout">
        <main class="content">${renderCurrentView()}</main>
      </div>
    </div>
  `;
}

function renderConnectionStatus() {
  return `
    <div class="connection-status ${state.backendOnline ? "online" : "offline"}" title="${state.backendOnline ? "后端连接正常" : "无法连接后端服务"}">
      <span class="connection-dot"></span>
      <span>${state.backendOnline ? "已连接" : "已断开"}</span>
    </div>
  `;
}

function iconMarkup(iconName) {
  return `<span class="app-icon" aria-hidden="true">${escapeHtml(iconCodes[iconName] || "")}</span>`;
}

function iconButton({ label, iconName, onclick, className = "", disabled = false, text = false }) {
  const classes = ["icon-action", text ? "text-action" : "", className].filter(Boolean).join(" ");
  const labelText = text ? `<span class="button-label">${escapeHtml(label)}</span>` : "";
  return `
    <button class="${escapeAttr(classes)}" type="button" title="${escapeAttr(label)}" aria-label="${escapeAttr(label)}" onclick="${onclick}" ${disabled ? "disabled" : ""}>
      ${iconMarkup(iconName)}${labelText}
    </button>
  `;
}

function sideListScrollTop() {
  const list = document.querySelector(".side-list");
  return list ? list.scrollTop : 0;
}

function restoreSideListScroll(scrollTop) {
  const list = document.querySelector(".side-list");
  if (list) list.scrollTop = scrollTop;
}

function renderWithSideListScroll(scrollTop) {
  render();
  restoreSideListScroll(scrollTop);
}

function renderOffline() {
  app.innerHTML = `
    <div class="auth-shell">
      <div class="auth-box">
        <h1>无法连接后端服务</h1>
        <p class="meta">前端页面已经打开，但本地后端没有响应。请确认程序窗口仍在运行，然后刷新页面。</p>
        <button class="primary" type="button" onclick="location.reload()">刷新页面</button>
      </div>
    </div>
  `;
}

function renderAuth() {
  const exists = state.status && state.status.database_exists;
  const blocked = state.status ? state.status.blocked_seconds : 0;
  app.innerHTML = `
    <div class="auth-shell">
      <form class="auth-box" onsubmit="${exists ? "unlockSubmit" : "createSubmit"}(event)">
        <h1>APIKEY管理器</h1>
        <div class="field">
          <label>主密码</label>
          <input id="password" type="password" autocomplete="current-password" required />
          <div class="hint">忘记主密码后无法找回数据库内容。</div>
        </div>
        ${exists ? "" : `
          <div class="field">
            <label>确认主密码</label>
            <input id="confirm-password" type="password" autocomplete="new-password" required />
          </div>
        `}
        <button class="primary" type="submit" ${blocked > 0 ? "disabled" : ""}>${exists ? "解锁" : "创建数据库"}</button>
        ${blocked > 0 ? `<p class="hint">请等待 ${blocked} 秒后重试。</p>` : ""}
      </form>
    </div>
  `;
}

function renderCurrentView() {
  if (state.view === "generic") return renderGenericView();
  if (state.view === "settings") return renderSettingsView();
  return renderLlmView();
}

function renderLlmView() {
  return `
    <div class="two-pane">
      <aside class="side-list">
        <div class="pane-head">
          <h2>供应商列表</h2>
          <div class="toolbar">
            ${iconButton({ label: "调整供应商顺序", iconName: "sort", onclick: "openOrderModal('providers')", disabled: state.providers.length <= 1 })}
            ${iconButton({ label: "添加供应商", iconName: "add", onclick: "openProviderModal()", className: "primary" })}
          </div>
        </div>
        ${state.providers.length ? state.providers.map(renderProviderListItem).join("") : `<div class="empty">暂无供应商</div>`}
      </aside>
      <section class="detail-pane">
        ${state.providerDetail ? renderProviderDetail(state.providerDetail) : `<div class="empty">请先添加供应商</div>`}
      </section>
    </div>
  `;
}

function renderProviderListItem(item, index) {
  return `
    <div class="list-entry ${item.id === state.selectedProviderId ? "active" : ""}">
      <button class="list-main" onclick="selectProvider(${item.id})">
        <strong>${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(item.base_url)}</span>
      </button>
    </div>
  `;
}

function renderProviderDetail(provider) {
  const websiteActions = provider.website_url ? `
    <a class="button-link icon-action text-action" href="${escapeAttr(provider.website_url)}" target="_blank" rel="noopener noreferrer" title="打开官网" aria-label="打开官网">${iconMarkup("open")}<span class="button-label">打开官网</span></a>
    ${iconButton({ label: "复制官网", iconName: "copy", onclick: `copyText(${jsLiteral(provider.website_url)})`, text: true })}
  ` : "";
  return `
    <div class="pane-head">
      <div>
        <h2>${escapeHtml(provider.name)}</h2>
        <div class="meta">${escapeHtml(provider.base_url)} · ${provider.api_formats.map((item) => formatLabels[item] || item).join("，")}</div>
      </div>
      <div class="toolbar">
        ${websiteActions}
        ${iconButton({ label: "复制端点", iconName: "copy", onclick: `copyText(${jsLiteral(provider.base_url)})`, text: true })}
        ${iconButton({ label: "编辑供应商", iconName: "edit", onclick: `openProviderModal(${provider.id})` })}
        ${iconButton({ label: "删除供应商", iconName: "delete", onclick: `deleteProvider(${provider.id})`, className: "danger" })}
      </div>
    </div>
    <div class="detail-body">
      ${renderKeysSection(provider)}
      ${renderProviderTestConfig(provider)}
      ${renderModelsSection(provider)}
    </div>
  `;
}

function renderKeysSection(provider) {
  const rows = provider.keys || [];
  const testing = state.testingProviderId === provider.id;
  return `
    <section class="section">
      <div class="section-head">
        <h2>API密钥</h2>
        <div class="toolbar">
          <button type="button" onclick="testSelectedKey(${provider.id})" ${provider.test_key_id && !testing ? "" : "disabled"}>${testing ? "正在测试" : "测试指定密钥"}</button>
          ${iconButton({ label: "调整密钥顺序", iconName: "sort", onclick: "openOrderModal('keys')", disabled: (provider.keys || []).length <= 1 })}
          ${iconButton({ label: "添加密钥", iconName: "add", onclick: `openKeyModal(${provider.id})`, className: "primary", text: true })}
        </div>
      </div>
      <div class="hint">选择一条密钥作为测试密钥；模型列表获取和模型测试都会使用它。</div>
      ${rows.length ? `
        <div class="table-wrap">
          <table class="keys-table">
            <thead>
              <tr>
                <th>测试密钥</th>
                <th>名称</th>
                <th>密钥</th>
                <th>测试状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>${rows.map((key, index) => renderKeyRow(key, provider, index, rows.length)).join("")}</tbody>
          </table>
        </div>
      ` : `<div class="empty">暂无密钥</div>`}
    </section>
  `;
}

function renderKeyRow(key, provider, index, total) {
  const status = key.test_status || "untested";
  const statusText = status === "success" ? "成功" : status === "failed" ? "失败" : status === "testing" ? "正在测试" : "未测试";
  const hasTestDetail = Boolean(key.test_message || key.test_reasoning || key.last_tested);
  return `
    <tr>
      <td><input type="radio" name="test-key" ${provider.test_key_id === key.id ? "checked" : ""} onchange="setTestKey(${provider.id}, ${key.id})" /></td>
      <td>${escapeHtml(key.key_name)}</td>
      <td class="secret">${escapeHtml(key.masked_key)}</td>
      <td>
        <div class="status-cell">
          <span class="status ${status}">${statusText}</span>
          ${hasTestDetail ? iconButton({ label: "查看测试详情", iconName: "info", onclick: `openTestDetailModal(${key.id})` }) : ""}
        </div>
      </td>
      <td>
        <div class="toolbar">
          ${iconButton({ label: "复制密钥", iconName: "copy", onclick: `copyText(${jsLiteral(key.api_key)})` })}
          ${iconButton({ label: "编辑密钥", iconName: "edit", onclick: `openKeyModal(${key.provider_id}, ${key.id})` })}
          ${iconButton({ label: "删除密钥", iconName: "delete", onclick: `deleteKey(${key.id})`, className: "danger" })}
        </div>
      </td>
    </tr>
  `;
}

function openTestDetailModal(keyId) {
  let key = null;
  if (state.providerDetail && state.providerDetail.keys) {
    key = state.providerDetail.keys.find((item) => item.id === keyId);
  }
  if (!key) return;
  const testedAt = formatUtc8Time(key.last_tested);
  openModal(`
    <div class="modal">
      <h2>测试详情</h2>
      <div class="test-detail-list">
        <div class="test-detail-item">
          <strong>测试状态</strong>
          <span class="status ${escapeAttr(key.test_status || "untested")}">${escapeHtml(testStatusText(key.test_status || "untested"))}</span>
        </div>
        ${testedAt ? `
          <div class="test-detail-item">
            <strong>测试时间</strong>
            <div class="meta">${escapeHtml(testedAt)}</div>
          </div>
        ` : ""}
        ${key.test_message ? `
          <div class="test-detail-item">
            <strong>测试输出</strong>
            <pre class="test-detail-text">${escapeHtml(key.test_message)}</pre>
          </div>
        ` : ""}
        ${key.test_reasoning ? `
          <div class="test-detail-item">
            <strong>模型推理内容</strong>
            <pre class="test-detail-text">${escapeHtml(key.test_reasoning)}</pre>
          </div>
        ` : ""}
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">关闭</button>
      </div>
    </div>
  `);
}

function testStatusText(status) {
  if (status === "success") return "成功";
  if (status === "failed") return "失败";
  if (status === "testing") return "正在测试";
  return "未测试";
}

function renderProviderTestConfig(provider) {
  const config = provider.test_config || { test_model: "" };
  const models = (provider.model_cache && provider.model_cache.model_ids) || [];
  return `
    <section class="section">
      <div class="section-head">
        <h2>测试模型</h2>
        ${iconButton({ label: "保存模型", iconName: "save", onclick: `saveProviderTestConfig(${provider.id})`, className: "primary", text: true })}
      </div>
      <div class="grid-2">
        <div class="field">
          <label>当前供应商测试模型</label>
          <input id="provider-test-model" list="provider-model-options" value="${escapeAttr(config.test_model || "")}" placeholder="例如 gpt-4.1-mini" />
          <datalist id="provider-model-options">
            ${models.map((model) => `<option value="${escapeAttr(model)}"></option>`).join("")}
          </datalist>
        </div>
        <div class="field">
          <label>配置状态</label>
          <input value="${config.test_model ? "可执行模型测试" : "测试模型为空时只能刷新模型列表"}" disabled />
        </div>
      </div>
    </section>
  `;
}

function renderModelsSection(provider) {
  const cache = provider.model_cache || { model_ids: [], last_fetched: null };
  const refreshing = state.refreshingModelsProviderId === provider.id;
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <h2>模型列表</h2>
          <div class="meta">上次获取：${escapeHtml(formatUtc8Time(cache.last_fetched) || "尚未获取")}</div>
        </div>
        ${iconButton({ label: refreshing ? "正在刷新" : "刷新模型列表", iconName: "refresh", onclick: `refreshModels(${provider.id})`, className: "primary", text: true, disabled: !provider.test_key_id || refreshing })}
      </div>
      <div class="hint">刷新模型列表不依赖测试模型配置，只使用当前指定的测试密钥请求模型端点。</div>
      ${cache.model_ids.length ? `
        <div class="model-search">
          <input type="search" placeholder="搜索模型" oninput="filterModelList(this)" />
        </div>
        <div class="model-list">
          ${cache.model_ids.map((model) => `
            <div class="model-row">
              <span class="secret">${escapeHtml(model)}</span>
              ${iconButton({ label: "复制模型 ID", iconName: "copy", onclick: `copyText(${jsLiteral(model)})` })}
            </div>
          `).join("")}
          <div class="model-empty filtered-out">没有匹配的模型</div>
        </div>
      ` : `<div class="empty">暂无模型缓存</div>`}
    </section>
  `;
}

function renderGenericView() {
  return `
    <div class="two-pane">
      <aside class="side-list">
        <div class="pane-head">
          <h2>类别列表</h2>
          <div class="toolbar">
            ${iconButton({ label: "调整类别顺序", iconName: "sort", onclick: "openOrderModal('categories')", disabled: state.generic.length <= 1 })}
            ${iconButton({ label: "添加类别", iconName: "add", onclick: "openGenericCategoryModal()", className: "primary" })}
          </div>
        </div>
        ${state.generic.length ? state.generic.map(renderGenericListItem).join("") : `<div class="empty">暂无类别</div>`}
      </aside>
      <section class="detail-pane">
        <div class="detail-body">
          ${renderSelectedGenericGroup()}
        </div>
      </section>
    </div>
  `;
}

function renderGenericListItem(group, index) {
  return `
    <div class="list-entry ${group.category === state.selectedGenericCategory ? "active" : ""}">
      <button class="list-main" onclick="selectGenericCategory(${jsLiteral(group.category)})">
        <strong>${escapeHtml(group.category)}</strong>
        <span>${group.items.length} 个键值</span>
      </button>
    </div>
  `;
}

function renderSelectedGenericGroup() {
  if (!state.generic.length) return `<div class="empty">请先添加类别</div>`;
  const group = state.generic.find((item) => item.category === state.selectedGenericCategory) || state.generic[0];
  return renderGenericGroup(group);
}

function renderGenericGroup(group) {
  return `
    <section class="section" id="cat-${cssSafe(group.category)}">
      <div class="section-head">
        <div>
          <h2>${escapeHtml(group.category)}</h2>
          ${group.description ? `<div class="meta">${escapeHtml(group.description)}</div>` : ""}
        </div>
        <div class="toolbar">
          ${iconButton({ label: "调整键值顺序", iconName: "sort", onclick: `openOrderModal('genericKeys', ${jsLiteral(group.category)})`, disabled: group.items.length <= 1 })}
          ${iconButton({ label: "编辑类别", iconName: "edit", onclick: `openGenericCategoryModal(${jsLiteral(group.category)})` })}
          ${iconButton({ label: "添加键值对", iconName: "add", onclick: `openGenericKeyModal(${jsLiteral(group.category)})`, className: "primary", text: true })}
          ${iconButton({ label: "删除类别", iconName: "delete", onclick: `deleteGenericCategory(${jsLiteral(group.category)})`, className: "danger" })}
        </div>
      </div>
      ${group.items.length ? `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>键名</th>
              <th>键值</th>
              <th>描述</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${group.items.map((item, index) => `
              <tr>
                <td>${escapeHtml(item.key_name)}</td>
                <td class="secret">${escapeHtml(item.masked_value)}</td>
                <td>${escapeHtml(item.description || "-")}</td>
                <td>
                  <div class="toolbar">
                    ${iconButton({ label: "复制键值", iconName: "copy", onclick: `copyText(${jsLiteral(item.key_value)})` })}
                    ${iconButton({ label: "编辑键值对", iconName: "edit", onclick: `openGenericKeyModal(${jsLiteral(group.category)}, ${item.id})` })}
                    ${iconButton({ label: "删除键值对", iconName: "delete", onclick: `deleteGenericKey(${item.id})`, className: "danger" })}
                  </div>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      ` : `<div class="empty">该类别下暂无键值对</div>`}
    </section>
  `;
}

function renderSettingsView() {
  const settings = state.testSettings || { system_prompt: "", user_prompt: "" };
  return `
    <div class="settings-list">
      <form class="settings-item" onsubmit="saveGlobalTestSettings(event)">
        <strong>测试 Prompt 设置</strong>
        <div class="grid-2">
          <div class="field">
            <label>System Prompt</label>
            <textarea id="global-system-prompt">${escapeHtml(settings.system_prompt || "")}</textarea>
          </div>
          <div class="field">
            <label>User Prompt</label>
            <textarea id="global-user-prompt">${escapeHtml(settings.user_prompt || "")}</textarea>
          </div>
        </div>
        <button class="primary" type="submit">保存测试设置</button>
      </form>
      <div class="settings-item">
        <strong>数据库文件位置</strong>
        <div class="toolbar">
          <span class="secret">${escapeHtml(state.status.database_path)}</span>
          ${iconButton({ label: "复制数据库路径", iconName: "copy", onclick: `copyText(${jsLiteral(state.status.database_path)})` })}
        </div>
      </div>
      <div class="settings-item">
        <strong>数据导入导出</strong>
        <div class="meta">导出的 JSON、Markdown 和数据库文件都包含真实密钥值，请只保存到可信位置。导入仅支持本应用导出的 JSON，并会替换当前数据库内容。</div>
        <div class="toolbar settings-actions">
          ${iconButton({ label: "导出数据", iconName: "export", onclick: "openExportModal()", text: true })}
          ${iconButton({ label: "下载数据库", iconName: "database", onclick: "downloadDatabase()", text: true })}
          ${iconButton({ label: "导入 JSON", iconName: "import", onclick: "openImportModal()", className: "primary", text: true })}
        </div>
      </div>
      <div class="settings-item">
        <strong>安全说明</strong>
        <div class="meta">主密码不会明文保存。数据库文件使用 SQLCipher 打开，忘记主密码后无法恢复数据。</div>
      </div>
    </div>
  `;
}

async function createSubmit(event) {
  event.preventDefault();
  await run(async () => {
    state.status = await api("/api/create", jsonOptions("POST", {
      password: document.getElementById("password").value,
      confirm_password: document.getElementById("confirm-password").value,
    }));
    await afterUnlock();
    showToast("数据库已创建");
  });
}

async function unlockSubmit(event) {
  event.preventDefault();
  await run(async () => {
    state.status = await api("/api/unlock", jsonOptions("POST", { password: document.getElementById("password").value }));
    await afterUnlock();
    showToast("已解锁");
  });
}

async function afterUnlock() {
  await loadProviders();
  await loadGeneric();
  await loadTestSettings();
  render();
}

async function lockApp() {
  await run(async () => {
    state.status = await api("/api/lock", jsonOptions("POST"));
    state.providers = [];
    state.providerDetail = null;
    state.generic = [];
    state.selectedGenericCategory = null;
    state.testSettings = null;
    state.testingProviderId = null;
    state.refreshingModelsProviderId = null;
    render();
  });
}

async function switchView(view) {
  state.view = view;
  if (view === "llm") await loadProviders();
  if (view === "generic") await loadGeneric();
  if (view === "settings") await loadTestSettings();
  render();
}

async function selectProvider(providerId) {
  await run(async () => {
    const scrollTop = sideListScrollTop();
    await loadProviderDetail(providerId);
    renderWithSideListScroll(scrollTop);
  });
}

function openProviderModal(providerId) {
  const provider = providerId ? state.providerDetail : null;
  const selected = new Set(provider ? provider.api_formats : ["openai_chat_completion"]);
  openModal(`
    <form class="modal" onsubmit="submitProvider(event, ${providerId || "null"})">
      <h2>${provider ? "编辑供应商" : "添加供应商"}</h2>
      <div class="field">
        <label>供应商名称</label>
        <input name="name" value="${escapeAttr(provider ? provider.name : "")}" required />
      </div>
      <div class="field">
        <label>API端点</label>
        <input name="base_url" value="${escapeAttr(provider ? provider.base_url : "")}" placeholder="https://api.openai.com/v1" required />
      </div>
      <div class="field">
        <label>官网地址</label>
        <input name="website_url" value="${escapeAttr(provider ? provider.website_url || "" : "")}" placeholder="https://example.com" />
      </div>
      <div class="checks">
        ${Object.entries(formatLabels).map(([value, label]) => `
          <label class="check">
            <input type="checkbox" name="api_formats" value="${value}" ${selected.has(value) ? "checked" : ""} />
            ${label}
          </label>
        `).join("")}
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="submit">保存</button>
      </div>
    </form>
  `);
}

async function submitProvider(event, providerId) {
  event.preventDefault();
  await run(async () => {
    const form = new FormData(event.target);
    const data = {
      name: form.get("name"),
      base_url: form.get("base_url"),
      website_url: form.get("website_url"),
      api_formats: form.getAll("api_formats"),
    };
    if (providerId) {
      await api(`/api/providers/${providerId}`, jsonOptions("PUT", data));
    } else {
      const created = await api("/api/providers", jsonOptions("POST", data));
      state.selectedProviderId = created.id;
    }
    closeModal();
    await loadProviders();
    render();
  });
}

async function deleteProvider(providerId) {
  const confirmed = await confirmAction({
    title: "删除供应商",
    message: "该供应商下的密钥、测试配置和模型缓存都会一起删除。",
    confirmText: "删除",
  });
  if (!confirmed) return;
  await run(async () => {
    await api(`/api/providers/${providerId}`, { method: "DELETE" });
    state.selectedProviderId = null;
    await loadProviders();
    render();
  });
}

function openKeyModal(providerId, keyId) {
  const key = keyId ? state.providerDetail.keys.find((item) => item.id === keyId) : null;
  openModal(`
    <form class="modal" onsubmit="submitKey(event, ${providerId}, ${keyId || "null"})">
      <h2>${key ? "编辑密钥" : "添加密钥"}</h2>
      <div class="field">
        <label>密钥别名</label>
        <input name="key_name" value="${escapeAttr(key ? key.key_name : "")}" required />
      </div>
      <div class="field">
        <label>API密钥</label>
        <textarea name="api_key" required>${escapeHtml(key ? key.api_key : "")}</textarea>
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="submit">保存</button>
      </div>
    </form>
  `);
}

async function submitKey(event, providerId, keyId) {
  event.preventDefault();
  await run(async () => {
    const form = new FormData(event.target);
    const data = {
      key_name: form.get("key_name"),
      api_key: form.get("api_key"),
    };
    if (keyId) {
      await api(`/api/keys/${keyId}`, jsonOptions("PUT", data));
    } else {
      await api(`/api/providers/${providerId}/keys`, jsonOptions("POST", data));
    }
    closeModal();
    await loadProviderDetail(providerId);
    render();
  });
}

async function setTestKey(providerId, keyId) {
  await run(async () => {
    await api(`/api/providers/${providerId}/test-key`, jsonOptions("PATCH", { key_id: keyId }));
    await loadProviderDetail(providerId);
    render();
    showToast("测试密钥已设置");
  });
}

async function deleteKey(keyId) {
  const confirmed = await confirmAction({
    title: "删除密钥",
    message: "删除后无法从应用内恢复该密钥。",
    confirmText: "删除",
  });
  if (!confirmed) return;
  await run(async () => {
    await api(`/api/keys/${keyId}`, { method: "DELETE" });
    await loadProviderDetail(state.selectedProviderId);
    render();
  });
}

async function testSelectedKey(providerId) {
  await run(async () => {
    showToast("正在测试指定密钥");
    state.testingProviderId = providerId;
    markSelectedKeyTesting(providerId);
    render();
    try {
      await api(`/api/providers/${providerId}/test-selected-key`, jsonOptions("POST"));
    } finally {
      if (state.testingProviderId === providerId) state.testingProviderId = null;
      await loadProviderDetail(providerId).catch(() => {});
      render();
    }
  });
}

function markSelectedKeyTesting(providerId) {
  const provider = state.providerDetail;
  if (!provider || provider.id !== providerId || !provider.test_key_id) return;
  const key = (provider.keys || []).find((item) => item.id === provider.test_key_id);
  if (!key) return;
  key.test_status = "testing";
  key.test_message = "";
  key.test_reasoning = "";
  key.last_tested = null;
}

async function refreshModels(providerId) {
  await run(async () => {
    showToast("正在刷新模型列表");
    state.refreshingModelsProviderId = providerId;
    render();
    try {
      await api(`/api/providers/${providerId}/models/refresh`, jsonOptions("POST"));
    } finally {
      if (state.refreshingModelsProviderId === providerId) state.refreshingModelsProviderId = null;
      await loadProviderDetail(providerId).catch(() => {});
      render();
    }
  });
}

async function saveProviderTestConfig(providerId) {
  await run(async () => {
    await api(`/api/providers/${providerId}/test-config`, jsonOptions("PUT", {
      test_model: document.getElementById("provider-test-model").value,
    }));
    await loadProviderDetail(providerId);
    render();
    showToast("测试模型已保存");
  });
}

function filterModelList(input) {
  const section = input.closest(".section");
  if (!section) return;
  const keyword = input.value.trim().toLowerCase();
  const rows = Array.from(section.querySelectorAll(".model-row"));
  const list = section.querySelector(".model-list");
  let visibleCount = 0;
  for (const row of rows) {
    const modelName = row.querySelector(".secret")?.textContent.toLowerCase() || "";
    const matched = !keyword || modelName.includes(keyword);
    row.classList.toggle("filtered-out", !matched);
    if (matched) visibleCount += 1;
  }
  const empty = section.querySelector(".model-empty");
  if (empty) empty.classList.toggle("filtered-out", visibleCount > 0);
  if (list) list.scrollTop = 0;
}

async function saveGlobalTestSettings(event) {
  event.preventDefault();
  await run(async () => {
    state.testSettings = await api("/api/settings/test", jsonOptions("PUT", {
      system_prompt: document.getElementById("global-system-prompt").value,
      user_prompt: document.getElementById("global-user-prompt").value,
    }));
    render();
    showToast("测试设置已保存");
  });
}

function openExportModal() {
  openModal(`
    <div class="modal">
      <h2>导出数据</h2>
      <div class="export-options">
        <label class="check">
          <input id="export-include-tests" type="checkbox" />
          导出测试相关数据
        </label>
        <div class="hint">默认精简导出，只保存供应商、密钥和通用密钥等必要数据；勾选后会包含测试设置、测试模型、模型缓存和测试记录。</div>
      </div>
      <p class="meta">选择导出格式和保存方式。JSON 适合备份恢复，Markdown 适合人工查看；两种格式都会包含完整密钥。</p>
      <div class="export-grid">
        <button type="button" onclick="exportData('json', 'copy')">
          <strong>复制 JSON</strong>
          <span>复制到剪贴板，用于临时备份或转存。</span>
        </button>
        <button type="button" onclick="exportData('json', 'file')">
          <strong>保存 JSON 文件</strong>
          <span>下载可再次导入的备份文件。</span>
        </button>
        <button type="button" onclick="exportData('markdown', 'copy')">
          <strong>复制 Markdown</strong>
          <span>复制便于粘贴到笔记或文档。</span>
        </button>
        <button type="button" onclick="exportData('markdown', 'file')">
          <strong>保存 Markdown 文件</strong>
          <span>下载便于阅读的清单文件。</span>
        </button>
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">关闭</button>
      </div>
    </div>
  `);
}

async function exportData(format, target) {
  await run(async () => {
    const includeTests = document.getElementById("export-include-tests")?.checked ? "1" : "0";
    const data = await api(`/api/data/export/${format}?include_tests=${includeTests}`);
    if (target === "copy") {
      await navigator.clipboard.writeText(data.content);
      showToast(`已复制${format === "json" ? "JSON" : "Markdown"}导出内容`);
      return;
    }
    saveTextFile(data.filename, data.content, data.mime_type);
    showToast("已开始保存导出文件");
  });
}

function downloadDatabase() {
  const link = document.createElement("a");
  link.href = "/api/data/export/database";
  link.download = "apikeys.db";
  document.body.appendChild(link);
  link.click();
  link.remove();
  showToast("已开始下载数据库文件");
}

function openImportModal() {
  openModal(`
    <form class="modal" onsubmit="submitImportJson(event)">
      <h2>导入 JSON</h2>
      <p class="meta">导入会替换当前数据库中的供应商、密钥、通用密钥、测试配置和模型缓存。请先导出一份 JSON 备份。</p>
      <div class="toolbar import-actions">
        <button type="button" onclick="document.getElementById('import-json-file').click()">选择 JSON 文件</button>
        <button type="button" onclick="readImportClipboard()">从剪贴板读取</button>
      </div>
      <input id="import-json-file" class="file-input" type="file" accept="application/json,.json" onchange="handleImportFile(event)" />
      <div class="field">
        <label>JSON 内容</label>
        <textarea id="import-json-text" class="import-textarea" placeholder="选择文件，或从剪贴板读取 JSON 内容。"></textarea>
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="submit">导入并替换</button>
      </div>
    </form>
  `);
}

async function handleImportFile(event) {
  await run(async () => {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".json")) throw new Error("请选择 JSON 文件");
    document.getElementById("import-json-text").value = await file.text();
    showToast("已读取 JSON 文件");
  });
}

async function readImportClipboard() {
  await run(async () => {
    const text = await navigator.clipboard.readText();
    if (!text.trim()) throw new Error("剪贴板没有可导入内容");
    document.getElementById("import-json-text").value = text;
    showToast("已读取剪贴板内容");
  });
}

async function submitImportJson(event) {
  event.preventDefault();
  await run(async () => {
    const text = document.getElementById("import-json-text").value.trim();
    if (!text) throw new Error("请先提供 JSON 内容");
    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      throw new Error("JSON 解析失败，请检查导入内容");
    }
    const confirmed = await confirmAction({
      title: "确认导入",
      message: "导入后当前数据库内容会被 JSON 文件内容替换。该操作无法撤销。",
      confirmText: "导入并替换",
    });
    if (!confirmed) return;
    const result = await api("/api/data/import/json", jsonOptions("POST", { data }));
    state.selectedProviderId = null;
    state.selectedGenericCategory = null;
    await afterUnlock();
    showToast(`导入完成：${result.providers} 个供应商，${result.generic_categories} 个类别`, 4000);
  });
}

function selectGenericCategory(category) {
  const scrollTop = sideListScrollTop();
  state.selectedGenericCategory = category;
  renderWithSideListScroll(scrollTop);
}

function openGenericCategoryModal(category) {
  const group = category ? state.generic.find((item) => item.category === category) : null;
  openModal(`
    <form class="modal" onsubmit="submitGenericCategory(event, ${jsLiteral(category || "")})">
      <h2>${group ? "编辑类别" : "添加类别"}</h2>
      <div class="field">
        <label>类别名称</label>
        <input name="category" value="${escapeAttr(group ? group.category : "")}" required />
      </div>
      <div class="field">
        <label>描述</label>
        <input name="description" value="${escapeAttr(group ? group.description || "" : "")}" />
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="submit">保存</button>
      </div>
    </form>
  `);
}

async function submitGenericCategory(event, oldCategory) {
  event.preventDefault();
  await run(async () => {
    const form = new FormData(event.target);
    const data = {
      category: form.get("category"),
      description: form.get("description"),
    };
    if (oldCategory) {
      const updated = await api(`/api/generic/category/${encodeURIComponent(oldCategory)}`, jsonOptions("PUT", data));
      state.selectedGenericCategory = updated.category;
    } else {
      const created = await api("/api/generic/categories", jsonOptions("POST", data));
      state.selectedGenericCategory = created.category;
    }
    closeModal();
    await loadGeneric();
    render();
  });
}

function openGenericKeyModal(category, itemId) {
  let item = null;
  if (itemId) {
    for (const group of state.generic) {
      item = group.items.find((entry) => entry.id === itemId);
      if (item) break;
    }
  }
  openModal(`
    <form class="modal" onsubmit="submitGenericKey(event, ${itemId || "null"})">
      <h2>${item ? "编辑键值对" : "添加键值对"}</h2>
      <div class="field">
        <label>类别名称</label>
        <select name="category" required>
          ${state.generic.map((group) => {
            const selected = (item ? item.category : category) === group.category ? "selected" : "";
            return `<option value="${escapeAttr(group.category)}" ${selected}>${escapeHtml(group.category)}</option>`;
          }).join("")}
        </select>
      </div>
      <div class="field">
        <label>键名</label>
        <input name="key_name" value="${escapeAttr(item ? item.key_name : "")}" required />
      </div>
      <div class="field">
        <label>键值</label>
        <textarea name="key_value" required>${escapeHtml(item ? item.key_value : "")}</textarea>
      </div>
      <div class="field">
        <label>描述</label>
        <input name="description" value="${escapeAttr(item ? item.description || "" : "")}" />
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="submit">保存</button>
      </div>
    </form>
  `);
}

async function submitGenericKey(event, itemId) {
  event.preventDefault();
  await run(async () => {
    const form = new FormData(event.target);
    const data = {
      category: form.get("category"),
      key_name: form.get("key_name"),
      key_value: form.get("key_value"),
      description: form.get("description"),
    };
    if (itemId) {
      await api(`/api/generic/${itemId}`, jsonOptions("PUT", data));
    } else {
      await api("/api/generic", jsonOptions("POST", data));
    }
    state.selectedGenericCategory = data.category;
    closeModal();
    await loadGeneric();
    render();
  });
}

async function deleteGenericKey(itemId) {
  const confirmed = await confirmAction({
    title: "删除键值对",
    message: "删除后无法从应用内恢复该键值对。",
    confirmText: "删除",
  });
  if (!confirmed) return;
  await run(async () => {
    await api(`/api/generic/${itemId}`, { method: "DELETE" });
    await loadGeneric();
    render();
  });
}

async function deleteGenericCategory(category) {
  const confirmed = await confirmAction({
    title: "删除类别",
    message: `将删除“${category}”类别及其下所有键值对。`,
    confirmText: "删除",
  });
  if (!confirmed) return;
  await run(async () => {
    await api(`/api/generic/category/${encodeURIComponent(category)}`, { method: "DELETE" });
    if (state.selectedGenericCategory === category) state.selectedGenericCategory = null;
    await loadGeneric();
    render();
  });
}

function openOrderModal(type, category) {
  if (type === "providers") {
    orderDraft = {
      type,
      title: "调整供应商顺序",
      items: state.providers.map((item) => ({ value: item.id, label: item.name, meta: item.base_url })),
    };
  } else if (type === "keys") {
    const provider = state.providerDetail;
    orderDraft = {
      type,
      providerId: provider.id,
      title: `调整 ${provider.name} 的密钥顺序`,
      items: provider.keys.map((item) => ({ value: item.id, label: item.key_name, meta: item.masked_key })),
    };
  } else if (type === "categories") {
    orderDraft = {
      type,
      title: "调整通用密钥类别顺序",
      items: state.generic.map((group) => ({ value: group.category, label: group.category, meta: `${group.items.length} 个键值` })),
    };
  } else if (type === "genericKeys") {
    const group = state.generic.find((item) => item.category === category);
    if (!group) return;
    orderDraft = {
      type,
      category,
      title: `调整 ${category} 的键值顺序`,
      items: group.items.map((item) => ({ value: item.id, label: item.key_name, meta: item.masked_value })),
    };
  }
  renderOrderModal();
}

function renderOrderModal() {
  if (!orderDraft) return;
  openModal(`
    <div class="modal">
      <h2>${escapeHtml(orderDraft.title)}</h2>
      <div class="order-list">
        ${orderDraft.items.map((item, index) => `
          <div class="order-row">
            <div class="order-row-text">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${escapeHtml(item.meta || "")}</span>
            </div>
            <div class="order-buttons">
              <button type="button" title="上移" onclick="moveOrderDraft(${index}, -1)" ${index === 0 ? "disabled" : ""}>↑</button>
              <button type="button" title="下移" onclick="moveOrderDraft(${index}, 1)" ${index === orderDraft.items.length - 1 ? "disabled" : ""}>↓</button>
            </div>
          </div>
        `).join("")}
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">取消</button>
        <button class="primary" type="button" onclick="saveOrderDraft()">保存顺序</button>
      </div>
    </div>
  `);
}

function moveOrderDraft(index, direction) {
  if (!orderDraft) return;
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= orderDraft.items.length) return;
  const [item] = orderDraft.items.splice(index, 1);
  orderDraft.items.splice(nextIndex, 0, item);
  renderOrderModal();
}

async function saveOrderDraft() {
  if (!orderDraft) return;
  await run(async () => {
    if (orderDraft.type === "providers") {
      state.providers = await api("/api/providers/order", jsonOptions("PUT", { ids: orderDraft.items.map((item) => item.value) }));
      if (state.selectedProviderId) await loadProviderDetail(state.selectedProviderId);
    } else if (orderDraft.type === "keys") {
      await api(`/api/providers/${orderDraft.providerId}/keys/order`, jsonOptions("PUT", { ids: orderDraft.items.map((item) => item.value) }));
      await loadProviderDetail(orderDraft.providerId);
    } else if (orderDraft.type === "categories") {
      state.generic = await api("/api/generic/categories/order", jsonOptions("PUT", { categories: orderDraft.items.map((item) => item.value) }));
    } else if (orderDraft.type === "genericKeys") {
      state.generic = await api(`/api/generic/category/${encodeURIComponent(orderDraft.category)}/order`, jsonOptions("PUT", { ids: orderDraft.items.map((item) => item.value) }));
    }
    orderDraft = null;
    closeModal();
    render();
    showToast("顺序已保存");
  });
}

async function copyText(text) {
  await run(async () => {
    await navigator.clipboard.writeText(text);
    showToast("已复制");
  });
}

function saveTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: `${mimeType || "text/plain"};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function openModal(html) {
  modalRoot.innerHTML = `<div class="modal-backdrop">${html}</div>`;
}

function closeModal() {
  if (confirmResolver) {
    confirmResolver(false);
    confirmResolver = null;
  }
  orderDraft = null;
  modalRoot.innerHTML = "";
}

function confirmAction({ title, message, confirmText = "确认" }) {
  return new Promise((resolve) => {
    confirmResolver = resolve;
    openModal(`
      <div class="modal confirm-modal">
        <h2>${escapeHtml(title)}</h2>
        <p class="meta">${escapeHtml(message)}</p>
        <div class="modal-actions">
          <button type="button" onclick="resolveConfirm(false)">取消</button>
          <button class="danger solid-danger" type="button" onclick="resolveConfirm(true)">${escapeHtml(confirmText)}</button>
        </div>
      </div>
    `);
  });
}

function resolveConfirm(value) {
  if (confirmResolver) {
    confirmResolver(value);
    confirmResolver = null;
  }
  orderDraft = null;
  modalRoot.innerHTML = "";
}

async function run(task) {
  try {
    await task();
  } catch (error) {
    showToast(error.message || "操作失败", error.isConnectionError ? 6000 : 2000);
    await loadStatus().catch(() => {});
    render();
  }
}

let toastTimer = null;
function showToast(message, duration = 2000) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, duration);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", "&#10;");
}

function jsLiteral(value) {
  return escapeAttr(JSON.stringify(String(value ?? "")));
}

function cssSafe(value) {
  return encodeURIComponent(value).replaceAll("%", "_");
}

function formatUtc8Time(value) {
  if (!value) return "";
  const normalized = String(value).includes("T") ? String(value) : String(value).replace(" ", "T") + "Z";
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);
  const utc8 = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  const pad = (number) => String(number).padStart(2, "0");
  return `${utc8.getUTCFullYear()}-${pad(utc8.getUTCMonth() + 1)}-${pad(utc8.getUTCDate())} ${pad(utc8.getUTCHours())}:${pad(utc8.getUTCMinutes())}:${pad(utc8.getUTCSeconds())}`;
}
