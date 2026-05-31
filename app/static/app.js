const state = {
  status: null,
  view: "llm",
  providers: [],
  selectedProviderId: null,
  providerDetail: null,
  generic: [],
  testSettings: null,
};

const formatLabels = {
  openai_completion: "OpenAI Completions",
  openai_response: "OpenAI Response",
  anthropic_message: "Anthropic Messages",
};

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");
const modalRoot = document.getElementById("modal-root");
let orderDraft = null;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  await loadStatus();
  render();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "请求失败");
  return payload.data;
}

function jsonOptions(method, data) {
  return { method, body: JSON.stringify(data || {}) };
}

async function loadStatus() {
  state.status = await api("/api/status");
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
}

async function loadTestSettings() {
  state.testSettings = await api("/api/settings/test");
}

function render() {
  if (!state.status || !state.status.unlocked) {
    renderAuth();
    return;
  }
  app.innerHTML = `
    <div class="app-shell">
      <header class="titlebar">
        <h1>APIKEY管理器</h1>
        <div class="toolbar"><button type="button" onclick="lockApp()">锁定</button></div>
      </header>
      <div class="main-layout">
        <nav class="nav">
          <button class="${state.view === "llm" ? "active" : ""}" onclick="switchView('llm')">大模型</button>
          <button class="${state.view === "generic" ? "active" : ""}" onclick="switchView('generic')">通用密钥</button>
          <button class="${state.view === "settings" ? "active" : ""}" onclick="switchView('settings')">设置</button>
        </nav>
        <main class="content">${renderCurrentView()}</main>
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
            <button type="button" onclick="openOrderModal('providers')" ${state.providers.length > 1 ? "" : "disabled"}>调整顺序</button>
            <button class="primary icon" type="button" title="添加供应商" onclick="openProviderModal()">＋</button>
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
  return `
    <div class="pane-head">
      <div>
        <h2>${escapeHtml(provider.name)}</h2>
        <div class="meta">${escapeHtml(provider.base_url)} · ${provider.api_formats.map((item) => formatLabels[item] || item).join("，")}</div>
      </div>
      <div class="toolbar">
        <button type="button" onclick="copyText(${jsLiteral(provider.base_url)})">复制端点</button>
        <button type="button" onclick="openProviderModal(${provider.id})">编辑</button>
        <button class="danger" type="button" onclick="deleteProvider(${provider.id})">删除</button>
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
  return `
    <section class="section">
      <div class="section-head">
        <h2>API密钥</h2>
        <div class="toolbar">
          <button type="button" onclick="testSelectedKey(${provider.id})" ${provider.test_key_id ? "" : "disabled"}>测试指定密钥</button>
          <button type="button" onclick="openOrderModal('keys')" ${(provider.keys || []).length > 1 ? "" : "disabled"}>调整顺序</button>
          <button class="primary" type="button" onclick="openKeyModal(${provider.id})">添加密钥</button>
        </div>
      </div>
      <div class="hint">选择一条密钥作为测试密钥；模型列表获取和模型测试都会使用它。</div>
      ${rows.length ? `
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>测试密钥</th>
                <th>名称</th>
                <th>密钥</th>
                <th>测试状态</th>
                <th>上次测试</th>
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
  const statusText = status === "success" ? "成功" : status === "failed" ? "失败" : "未测试";
  return `
    <tr>
      <td><input type="radio" name="test-key" ${provider.test_key_id === key.id ? "checked" : ""} onchange="setTestKey(${provider.id}, ${key.id})" /></td>
      <td>${escapeHtml(key.key_name)}</td>
      <td class="secret">${escapeHtml(key.masked_key)}</td>
      <td><span class="status ${status}">${statusText}</span></td>
      <td>${escapeHtml(formatUtc8Time(key.last_tested) || "-")}</td>
      <td>
        <div class="toolbar">
          <button type="button" onclick="copyText(${jsLiteral(key.api_key)})">复制</button>
          <button type="button" onclick="openKeyModal(${key.provider_id}, ${key.id})">编辑</button>
          <button class="danger" type="button" onclick="deleteKey(${key.id})">删除</button>
        </div>
      </td>
    </tr>
    ${key.test_message ? `<tr><td colspan="6" class="meta">${escapeHtml(key.test_message)}</td></tr>` : ""}
  `;
}

function renderProviderTestConfig(provider) {
  const config = provider.test_config || { test_model: "" };
  const models = (provider.model_cache && provider.model_cache.model_ids) || [];
  return `
    <section class="section">
      <div class="section-head">
        <h2>测试模型</h2>
        <button class="primary" type="button" onclick="saveProviderTestConfig(${provider.id})">保存模型</button>
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
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <h2>模型列表</h2>
          <div class="meta">上次获取：${escapeHtml(formatUtc8Time(cache.last_fetched) || "尚未获取")}</div>
        </div>
        <button class="primary" type="button" onclick="refreshModels(${provider.id})" ${provider.test_key_id ? "" : "disabled"}>刷新模型列表</button>
      </div>
      <div class="hint">刷新模型列表不依赖测试模型配置，只使用当前指定的测试密钥请求模型端点。</div>
      ${cache.model_ids.length ? `
        <div class="model-list">
          ${cache.model_ids.map((model) => `
            <div class="model-row">
              <span class="secret">${escapeHtml(model)}</span>
              <button type="button" onclick="copyText(${jsLiteral(model)})">复制</button>
            </div>
          `).join("")}
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
            <button type="button" onclick="openOrderModal('categories')" ${state.generic.length > 1 ? "" : "disabled"}>调整顺序</button>
            <button class="primary icon" type="button" title="添加类别" onclick="openGenericModal()">＋</button>
          </div>
        </div>
        ${state.generic.length ? state.generic.map(renderGenericListItem).join("") : `<div class="empty">暂无类别</div>`}
      </aside>
      <section class="detail-pane">
        <div class="detail-body">
          ${state.generic.length ? state.generic.map(renderGenericGroup).join("") : `<div class="empty">请先添加键值对</div>`}
        </div>
      </section>
    </div>
  `;
}

function renderGenericListItem(group, index) {
  return `
    <div class="list-entry">
      <button class="list-main" onclick="scrollCategory(${jsLiteral(group.category)})">
        <strong>${escapeHtml(group.category)}</strong>
        <span>${group.items.length} 个键值</span>
      </button>
    </div>
  `;
}

function renderGenericGroup(group) {
  return `
    <section class="section" id="cat-${cssSafe(group.category)}">
      <div class="section-head">
        <h2>${escapeHtml(group.category)}</h2>
        <div class="toolbar">
          <button type="button" onclick="openOrderModal('genericKeys', ${jsLiteral(group.category)})" ${group.items.length > 1 ? "" : "disabled"}>调整顺序</button>
          <button class="primary" type="button" onclick="openGenericModal(${jsLiteral(group.category)})">添加键值对</button>
          <button class="danger" type="button" onclick="deleteGenericCategory(${jsLiteral(group.category)})">删除类别</button>
        </div>
      </div>
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
                    <button type="button" onclick="copyText(${jsLiteral(item.key_value)})">复制</button>
                    <button type="button" onclick="openGenericModal(${jsLiteral(group.category)}, ${item.id})">编辑</button>
                    <button class="danger" type="button" onclick="deleteGenericKey(${item.id})">删除</button>
                  </div>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
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
          <button type="button" onclick="copyText(${jsLiteral(state.status.database_path)})">复制</button>
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
    state.testSettings = null;
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
    await loadProviderDetail(providerId);
    render();
  });
}

function openProviderModal(providerId) {
  const provider = providerId ? state.providerDetail : null;
  const selected = new Set(provider ? provider.api_formats : ["openai_response"]);
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
  if (!confirm("确认删除该供应商及其所有密钥、测试配置和模型缓存？")) return;
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
  if (!confirm("确认删除该密钥？")) return;
  await run(async () => {
    await api(`/api/keys/${keyId}`, { method: "DELETE" });
    await loadProviderDetail(state.selectedProviderId);
    render();
  });
}

async function testSelectedKey(providerId) {
  await run(async () => {
    showToast("正在测试指定密钥");
    await api(`/api/providers/${providerId}/test-selected-key`, jsonOptions("POST"));
    await loadProviderDetail(providerId);
    render();
  });
}

async function refreshModels(providerId) {
  await run(async () => {
    showToast("正在刷新模型列表");
    await api(`/api/providers/${providerId}/models/refresh`, jsonOptions("POST"));
    await loadProviderDetail(providerId);
    render();
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

function openGenericModal(category, itemId) {
  let item = null;
  if (itemId) {
    for (const group of state.generic) {
      item = group.items.find((entry) => entry.id === itemId);
      if (item) break;
    }
  }
  openModal(`
    <form class="modal" onsubmit="submitGeneric(event, ${itemId || "null"})">
      <h2>${item ? "编辑键值对" : "添加键值对"}</h2>
      <div class="field">
        <label>类别名称</label>
        <input name="category" value="${escapeAttr(item ? item.category : category || "")}" required />
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

async function submitGeneric(event, itemId) {
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
    closeModal();
    await loadGeneric();
    render();
  });
}

async function deleteGenericKey(itemId) {
  if (!confirm("确认删除该键值对？")) return;
  await run(async () => {
    await api(`/api/generic/${itemId}`, { method: "DELETE" });
    await loadGeneric();
    render();
  });
}

async function deleteGenericCategory(category) {
  if (!confirm(`确认删除“${category}”类别下的所有键值对？`)) return;
  await run(async () => {
    await api(`/api/generic/category/${encodeURIComponent(category)}`, { method: "DELETE" });
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

function scrollCategory(category) {
  const target = document.getElementById(`cat-${cssSafe(category)}`);
  if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function copyText(text) {
  await run(async () => {
    await navigator.clipboard.writeText(text);
    showToast("已复制");
  });
}

function openModal(html) {
  modalRoot.innerHTML = `<div class="modal-backdrop">${html}</div>`;
}

function closeModal() {
  orderDraft = null;
  modalRoot.innerHTML = "";
}

async function run(task) {
  try {
    await task();
  } catch (error) {
    showToast(error.message || "操作失败");
    await loadStatus().catch(() => {});
    render();
  }
}

let toastTimer = null;
function showToast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 2000);
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
