"use strict";

const $ = (id) => document.getElementById(id);
const loginForm = $("login-form");
const email = $("email");
const password = $("password");
const passwordToggle = $("password-toggle");
const loginSubmit = $("login-submit");
const refreshButton = $("account-refresh");
const refreshTime = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium" });
const linkCards = Array.from(document.querySelectorAll("[data-subscription]"), (card) => ({
  mode: card.dataset.subscription,
  url: card.querySelector("[data-url]"),
  copy: card.querySelector("[data-copy]"),
  toggle: card.querySelector("[data-toggle]"),
  download: card.querySelector("[data-download]"),
  warning: card.querySelector("[data-copy-failed]"),
  copied: false,
  expanded: false,
}));

const state = {
  status: null,
  statusFailed: false,
  refreshing: false,
  sub: null, // /api/subscription response
  subFailed: false,
  relogin: false,
  loggingIn: false,
  loginError: "",
  linkUsed: false,
};

function model() {
  const s = state.status;
  let account = "checking";
  if (state.statusFailed) account = "unreachable";
  else if (s) {
    account = s.account_state || (s.token_saved ? "saved" : "signed_out");
    if (account === "connected" && s.plan_count === 0) account = "connected_empty";
  }
  const oauth = Boolean(s?.oauth_configured);
  const hasSession = Boolean(s?.token_saved) && account !== "expired" && account !== "signed_out";
  const needLogin = account === "signed_out" || account === "expired" || state.relogin;
  const subOk = Boolean(state.sub) && !state.subFailed;
  let active;
  if (needLogin || ["checking", "unreachable", "unavailable", "connected_empty"].includes(account)) active = 1;
  else active = subOk && state.linkUsed ? 3 : 2;
  return { account, oauth, hasSession, needLogin, subOk, active };
}

function stepState(n, m) {
  if (n === m.active) {
    if (n === 1 && ((m.needLogin && !m.oauth) || m.account === "unreachable")) return "blocked";
    if (n === 1 && (m.account === "unavailable" || m.account === "connected_empty")) return "warn";
    if (n === 2 && state.subFailed) return "blocked";
    return "active";
  }
  if (n < m.active && (n !== 1 || m.hasSession)) return "done";
  return "idle";
}

function setStep(id, n, value) {
  const step = $(id);
  step.dataset.s = value;
  if (["active", "warn", "blocked"].includes(value)) step.setAttribute("aria-current", "step");
  else step.removeAttribute("aria-current");
  step.querySelector("[data-glyph]").textContent = value === "done" ? "✓" : String(n);
  step.querySelector("[data-step-label]").textContent = `步骤 ${n}${value === "done" ? "，已完成" : ""}`;
}

function show(id, visible) {
  $(id).hidden = !visible;
}

function pill(text, kind) {
  const element = $("account-pill");
  element.hidden = !text;
  element.textContent = text;
  element.className = `pill ${kind}`;
}

function renderAccount(m) {
  const s = state.status;
  let title = "MonoCloud 账户";
  let meta = "";
  pill("", "mute");
  if (m.account === "checking") pill("读取中…", "mute");
  else if (m.account === "unreachable") {
    pill("无法读取状态", "err");
    meta = "请检查服务是否运行，然后重试。";
  } else if (state.relogin) {
    title = "切换 MonoCloud 账户";
    meta = state.loggingIn
      ? "正在登录新账户，请等待结果；处理期间无法取消。"
      : "登录成功后替换当前账户；取消或失败时保留原账户。";
  } else if (m.account === "signed_out") {
    title = "登录 MonoCloud 账户";
    meta = "使用你的 MonoCloud 邮箱和密码。";
  } else if (m.account === "expired") {
    title = "重新登录 MonoCloud 账户";
    pill("登录已失效", "err");
    meta = "失效期间，客户端无法更新订阅。";
  } else if (m.account === "saved") {
    pill("登录已保存", "mute");
  } else if (m.account === "unavailable") {
    pill("刷新失败", "warn");
    meta = "暂时无法获取套餐和节点，请稍后重试。";
  } else if (m.account === "connected_empty") {
    pill("没有可用套餐", "warn");
    meta = "账户已验证，但目前没有可用套餐。";
  } else {
    pill(s.node_count === 0 ? "没有可用节点" : "已验证", s.node_count === 0 ? "warn" : "ok");
    meta = `${s.plan_names.join("、")} · ${s.node_count} 个 Shadowsocks 节点`;
  }
  if (m.needLogin && !m.oauth && s) pill("暂时无法登录", "err");
  $("account-title").textContent = title;
  $("account-meta").textContent = meta;
  show("account-meta", Boolean(meta));

  const updated = new Date(s?.refreshed_at ?? NaN);
  const hasRefreshTime = !state.relogin && Number.isFinite(updated.getTime());
  if (hasRefreshTime) {
    const timestamp = $("account-refreshed-at");
    timestamp.dateTime = s.refreshed_at;
    timestamp.textContent = refreshTime.format(updated);
  }
  show("account-refresh-time", hasRefreshTime);
  show("account-actions", m.hasSession && !state.relogin);
  refreshButton.disabled = state.refreshing;
  refreshButton.setAttribute("aria-busy", String(state.refreshing));
  refreshButton.textContent = state.refreshing ? "正在刷新…" : "刷新账户与节点";
  $("account-switch").disabled = state.refreshing;

  const blocked = m.needLogin && !m.oauth && Boolean(s);
  const canLogin = m.needLogin && m.oauth;
  const retryStatus = m.account === "unreachable";
  show("account-blocked", blocked);
  show("login-form", canLogin);
  show("login-cancel-row", state.relogin);
  show("retry-status", retryStatus);
  show("account-body", blocked || canLogin || retryStatus || state.relogin);

  loginForm.setAttribute("aria-busy", String(state.loggingIn));
  for (const control of [email, password, passwordToggle, loginSubmit]) control.disabled = state.loggingIn;
  $("login-cancel").disabled = state.loggingIn;
  if (!m.oauth) loginSubmit.disabled = true;
  $("login-label").textContent = state.loggingIn ? "正在登录…" : "登录";
  $("login-feedback").textContent = state.loginError;
  show("login-feedback", Boolean(state.loginError) && !state.loggingIn);
}

function renderLink(m) {
  let pending = "";
  if (m.account === "checking" || (!state.sub && !state.subFailed)) pending = "";
  else if (state.subFailed) pending = "订阅读取恢复后在这里显示。";
  else if (m.needLogin || m.account === "unreachable") pending = "登录账户后，在这里复制链接。";
  const ready = m.subOk && !pending && m.account !== "checking";
  $("link-pending").textContent = pending;
  show("link-pending", Boolean(pending));
  show("link-ready", ready);
  if (!ready) return;

  for (const card of linkCards) {
    const url = state.sub[`${card.mode}_url`];
    card.url.textContent = url;
    card.url.classList.toggle("expanded", card.expanded);
    card.toggle.textContent = card.expanded ? "收起" : "显示完整链接";
    card.toggle.setAttribute("aria-expanded", String(card.expanded));
    card.copy.textContent = card.copied ? "已复制" : "复制链接";
    card.download.href = url;
  }
  let host = "";
  try {
    host = new URL(state.sub.proxy_url).hostname;
  } catch {
    host = "";
  }
  show("link-loopback", ["localhost", "127.0.0.1", "[::1]"].includes(host));
  show("link-unverified", m.account === "unavailable");
}

function renderClient() {
  const names = state.status?.plan_names || [];
  for (const slot of document.querySelectorAll("[data-plan-names]")) {
    slot.textContent = names.length ? `可选套餐：${names.join("、")}。` : "";
  }
}

function nextStep(m) {
  if (m.account === "checking") return "正在读取本地会话…";
  if (m.account === "unreachable") return "暂时无法读取服务状态，请重试。";
  if (state.relogin) return state.loggingIn
    ? "正在登录另一个 MonoCloud 账户，请等待结果；处理期间无法取消。"
    : "下一步：<b>登录另一个 MonoCloud 账户</b>，或取消保留当前账户。";
  if (m.needLogin && !m.oauth) return "暂时无法登录，需要部署者先完成配置。";
  if (m.needLogin) return "下一步：<b>登录 MonoCloud 账户</b>。";
  if (m.account === "unavailable") return "可稍后重试刷新，或继续使用订阅链接。";
  if (m.account === "connected_empty") return "账户已验证，但没有可用套餐。";
  if (state.subFailed) return "订阅链接读取失败，请刷新页面重试。";
  if (!m.subOk) return "正在读取订阅链接…";
  if (!state.linkUsed) return "下一步：<b>复制需要的订阅链接</b>，导入客户端。";
  return "下一步：<b>按下面的说明在客户端添加或更新订阅</b>。";
}

function render() {
  const m = model();
  const values = [1, 2, 3].map((n) => stepState(n, m));
  setStep("step-account", 1, values[0]);
  setStep("step-link", 2, values[1]);
  setStep("step-client", 3, values[2]);
  // Static markup only: the line never contains server-provided text.
  $("next-step").innerHTML = nextStep(m);
  renderAccount(m);
  renderLink(m);
  renderClient();
}

let toastTimer;
function toast(text) {
  const element = $("toast");
  element.textContent = text;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 2200);
}

async function loadStatus() {
  state.statusFailed = false;
  render();
  try {
    const response = await fetch("api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status unavailable");
    state.status = await response.json();
  } catch {
    state.status = null;
    state.statusFailed = true;
  }
  render();
}

async function loadSubscription() {
  try {
    const response = await fetch("api/subscription", { cache: "no-store" });
    if (!response.ok) throw new Error("subscription unavailable");
    const subscription = await response.json();
    if (!subscription?.proxy_url || !subscription?.tailscale_url) throw new Error("missing subscription URLs");
    state.sub = subscription;
    state.subFailed = false;
  } catch {
    state.subFailed = true;
  }
  render();
}

passwordToggle.addEventListener("click", () => {
  const visible = password.type === "password";
  password.type = visible ? "text" : "password";
  passwordToggle.textContent = visible ? "隐藏" : "显示";
  passwordToggle.setAttribute("aria-label", visible ? "隐藏密码" : "显示密码");
  passwordToggle.setAttribute("aria-pressed", String(visible));
});

$("account-switch").addEventListener("click", () => {
  state.relogin = true;
  state.loginError = "";
  render();
  email.focus();
});

$("login-cancel").addEventListener("click", () => {
  if (state.loggingIn) return;
  state.relogin = false;
  state.loginError = "";
  render();
  $("account-switch").focus();
});

$("retry-status").addEventListener("click", loadStatus);

refreshButton.addEventListener("click", async () => {
  if (state.refreshing || !model().hasSession || state.relogin) return;
  state.refreshing = true;
  render();
  try {
    const response = await fetch("api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    if (!response.ok) throw new Error("refresh unavailable");
    state.status = await response.json();
  } catch {
    state.status = { ...state.status, account_state: "unavailable", refreshed_at: new Date().toISOString() };
  } finally {
    state.refreshing = false;
    render();
  }
});

const loginErrors = {
  login_rejected: "登录未通过，请检查邮箱和密码后重试。",
  oauth_not_configured: "此服务还没有完成 MonoCloud 登录配置，请联系部署者处理。",
  oauth_client_rejected: "服务的 MonoCloud 登录配置被拒绝，请联系部署者检查。",
  invalid_login_input: "请输入有效的邮箱与密码。",
  upstream_unavailable: "暂时无法连接 MonoCloud，请稍后重试。",
  token_save_failed: "登录验证已通过，但登录凭据保存失败，请联系部署者检查存储权限。",
};

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.loggingIn || !state.status?.oauth_configured) return;
  const payload = { email: email.value.trim(), password: password.value };
  state.loggingIn = true;
  state.loginError = "";
  render();
  try {
    const response = await fetch("api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      state.loginError = loginErrors[result?.code]
        || (response.status >= 500 ? "本服务处理登录时发生错误，请稍后重试。" : "登录暂未完成，请稍后重试。");
    } else if (result?.token_saved !== true) {
      state.loginError = "本服务返回了无效的登录结果，请稍后重试。";
    } else {
      state.relogin = false;
      state.status = { oauth_configured: true, token_saved: true };
      toast("登录已保存");
    }
  } catch {
    state.loginError = "与本服务的连接中断，请检查连接后重试。";
  } finally {
    payload.password = "";
    password.value = "";
    password.type = "password";
    passwordToggle.textContent = "显示";
    passwordToggle.setAttribute("aria-label", "显示密码");
    passwordToggle.setAttribute("aria-pressed", "false");
    state.loggingIn = false;
    render();
  }
});

function selectUrl(element) {
  const range = document.createRange();
  range.selectNodeContents(element);
  const selection = getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  element.focus();
}

function legacyCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.className = "visually-hidden";
  document.body.append(area);
  area.select();
  try {
    return document.execCommand("copy");
  } finally {
    area.remove();
  }
}

for (const card of linkCards) {
  card.toggle.addEventListener("click", () => {
    card.expanded = !card.expanded;
    render();
  });

  card.copy.addEventListener("click", async () => {
    const url = state.sub?.[`${card.mode}_url`];
    if (!url) return;
    card.copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
        card.copied = true;
      } else {
        card.copied = legacyCopy(url);
      }
    } catch {
      card.copied = false;
    }
    state.linkUsed = true;
    card.warning.hidden = card.copied;
    if (!card.copied) card.expanded = true;
    render();
    if (card.copied) toast("已复制订阅链接");
    else selectUrl(card.url);
  });

  card.download.addEventListener("click", () => {
    state.linkUsed = true;
    render();
  });
}

render();
loadStatus();
loadSubscription();
