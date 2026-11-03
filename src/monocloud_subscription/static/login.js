"use strict";

const $ = (id) => document.getElementById(id);
const loginForm = $("login-form");
const email = $("email");
const password = $("password");
const passwordToggle = $("password-toggle");
const loginSubmit = $("login-submit");
const subscriptionUrl = $("subscription-url");
const download = $("download-subscription");
const guide = $("guide-clash-mi");
const tailscaleGuide = $("guide-clash-mi-tailscale");

// One state object; render() derives every visible element from it.
const state = {
  status: null, // /api/status?verify=true response
  statusFailed: false,
  sub: null, // /api/subscription response
  subFailed: false,
  draft: null, // unsaved Tailscale choice; null means "same as saved"
  saving: false,
  saveFailed: false,
  justSaved: false,
  relogin: false,
  loggingIn: false,
  loginError: "",
  copied: false,
  copyFailed: false,
  urlOpen: false,
  guideTouched: false,
  tailscaleGuideTouched: false,
};

function model() {
  const s = state.status;
  let account = "checking";
  if (state.statusFailed) account = "unreachable";
  else if (s) {
    account = s.account_state;
    if (account === "connected" && s.plan_count === 0) account = "connected_empty";
  }
  const oauth = Boolean(s?.oauth_configured);
  const verified = account === "connected" || account === "connected_empty";
  const needLogin = account === "signed_out" || account === "expired" || state.relogin;
  const subOk = Boolean(state.sub) && !state.subFailed;
  const saved = Boolean(state.sub?.tailscale_enabled);
  const chosen = state.draft === null ? saved : state.draft;
  const dirty = subOk && chosen !== saved;
  const unchosen = subOk && !state.sub.tailscale_choice_saved;
  let active;
  if (needLogin || ["checking", "unreachable", "unavailable", "connected_empty"].includes(account)) active = 1;
  else if (!subOk || dirty || unchosen) active = 2;
  else active = state.copied ? 4 : 3;
  return { account, oauth, verified, needLogin, subOk, saved, chosen, dirty, unchosen, active };
}

function stepState(n, m) {
  if (n === m.active) {
    if (n === 1 && ((m.needLogin && !m.oauth) || m.account === "unreachable")) return "blocked";
    if (n === 1 && (m.account === "unavailable" || m.account === "connected_empty")) return "warn";
    if (n === 2 && state.subFailed) return "blocked";
    return "active";
  }
  if (n < m.active && (n !== 1 || m.verified)) return "done";
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
  if (m.account === "checking") pill("检查中…", "mute");
  else if (m.account === "unreachable") {
    pill("无法读取状态", "err");
    meta = "请检查服务是否运行，然后重试。";
  } else if (state.relogin) {
    title = "切换 MonoCloud 账户";
    meta = "登录成功后替换当前账户；取消或失败时保留原账户。";
  } else if (m.account === "signed_out") {
    title = "登录 MonoCloud 账户";
    meta = "使用你的 MonoCloud 邮箱和密码。";
  } else if (m.account === "expired") {
    title = "重新登录 MonoCloud 账户";
    pill("登录已失效", "err");
    meta = "失效期间，客户端无法更新订阅。";
  } else if (m.account === "unavailable") {
    pill("暂时无法验证", "warn");
    meta = "已保存登录，但现在无法确认账户状态。";
  } else if (m.account === "connected_empty") {
    pill("没有可用套餐", "warn");
    meta = "账户已验证，但目前没有可用套餐。";
  } else {
    pill("已验证", "ok");
    meta = `${s.plan_count} 个可用套餐：${s.plan_names.join("、")}`;
  }
  if (m.needLogin && !m.oauth && s) pill("暂时无法登录", "err");
  $("account-title").textContent = title;
  $("account-meta").textContent = meta;
  show("account-meta", Boolean(meta));

  const switchable = (m.verified || m.account === "unavailable") && !state.relogin;
  $("account-switch").textContent = m.account === "unavailable" ? "重新登录" : "切换账户";
  show("account-switch", switchable);

  const blocked = m.needLogin && !m.oauth && Boolean(s);
  const canLogin = m.needLogin && m.oauth;
  const recheck = ["unavailable", "connected_empty", "unreachable"].includes(m.account) && !state.relogin;
  show("account-blocked", blocked);
  show("login-form", canLogin);
  show("login-cancel-row", state.relogin);
  show("account-recheck", recheck);
  $("account-recheck-text").textContent = {
    unavailable: "可能是 MonoCloud 暂时无法访问。稍后重试即可，不必重新输入密码。",
    connected_empty: "请在 MonoCloud 确认套餐状态，然后回来重新验证。",
    unreachable: "暂时无法读取本服务的状态。",
  }[m.account] || "";
  $("verify-again").textContent = m.account === "unreachable" ? "重试" : "重新验证";
  show("account-body", blocked || canLogin || recheck || state.relogin);

  loginForm.setAttribute("aria-busy", String(state.loggingIn));
  for (const control of [email, password, passwordToggle, loginSubmit]) control.disabled = state.loggingIn;
  if (!m.oauth) loginSubmit.disabled = true;
  $("login-label").textContent = state.loggingIn ? "正在登录…" : "登录";
  $("login-feedback").textContent = state.loginError;
  show("login-feedback", Boolean(state.loginError) && !state.loggingIn);
}

function renderContent(m) {
  const loading = !state.sub && !state.subFailed;
  $("content-meta").textContent = loading ? "读取中…" : "";
  show("content-meta", loading);
  show("content-choice", m.subOk);
  show("content-dirty", m.dirty);
  for (const radio of document.querySelectorAll('input[name="content"]')) {
    radio.checked = (radio.value === "tailscale") === m.chosen;
    radio.disabled = state.saving;
  }
  const error = state.subFailed
    ? "无法读取订阅设置。请确认服务正在运行，然后刷新页面。"
    : state.saveFailed ? "保存失败，你的选择仍保留，请重试。" : "";
  $("content-error").textContent = error;
  show("content-error", Boolean(error));
  show("content-ts-note", m.subOk && m.chosen);
  // A first-time confirmation waits until earlier steps are done.
  const pending = m.dirty || (m.unchosen && m.active === 2);
  show("content-actions", m.subOk && pending);
  $("content-save").setAttribute("aria-busy", String(state.saving));
  $("content-save").disabled = state.saving;
  $("content-undo").disabled = state.saving;
  show("content-undo", m.dirty);
  $("content-save-label").textContent = state.saving
    ? "正在保存…"
    : state.saveFailed ? "重试保存" : m.unchosen && !m.dirty ? "确认" : "保存";
  $("content-hint").textContent = m.unchosen && !m.dirty ? "之后可以随时修改，链接不变" : "订阅链接不变";
  show("content-saved", state.justSaved && !pending);
  show("content-body", state.subFailed || (m.subOk && (m.chosen || pending || state.justSaved || state.saveFailed)));
}

function renderLink(m, stepValue) {
  let pending = "";
  if (m.account === "checking" || (!state.sub && !state.subFailed)) pending = "";
  else if (state.subFailed) pending = "订阅读取恢复后在这里显示。";
  else if (m.needLogin || m.account === "unreachable") pending = "登录账户后，在这里复制链接。";
  else if (m.account === "connected_empty") pending = "账户有可用套餐后，客户端才能从这个链接获取配置。";
  const ready = m.subOk && !pending && m.account !== "checking";
  $("link-pending").textContent = pending;
  show("link-pending", Boolean(pending));
  show("link-ready", ready);
  if (!ready) return;

  const url = state.sub.url;
  subscriptionUrl.textContent = url;
  subscriptionUrl.classList.toggle("expanded", state.urlOpen);
  download.href = url;
  $("url-toggle").textContent = state.urlOpen ? "收起" : "显示完整链接";
  $("url-toggle").setAttribute("aria-expanded", String(state.urlOpen));
  const copy = $("copy-subscription");
  copy.textContent = state.copied ? "已复制" : "复制链接";
  copy.className = `btn ${stepValue === "active" ? "blue" : "ghost"}`;
  $("link-unsaved").textContent = m.dirty
    ? `订阅内容的修改还没保存。这个链接目前提供的是已保存的内容（${m.saved ? "代理 + Tailscale" : "仅代理"}）。`
    : "";
  show("link-unsaved", m.dirty);
  let host = "";
  try {
    host = new URL(url).hostname;
  } catch {
    host = "";
  }
  show("link-loopback", ["localhost", "127.0.0.1", "[::1]"].includes(host));
  show("link-copy-failed", state.copyFailed);
  show("link-unverified", m.account === "unavailable");
}

function renderClient(m, stepValue) {
  const names = state.status?.plan_names || [];
  for (const slot of document.querySelectorAll("[data-plan-names]")) {
    slot.textContent = names.length ? `可选套餐：${names.join("、")}。` : "";
  }
  if (guide && !state.guideTouched) guide.open = stepValue === "active";
  if (tailscaleGuide && !state.tailscaleGuideTouched) tailscaleGuide.open = m.saved;
}

function nextStep(m) {
  if (m.account === "checking") return "正在检查账户…";
  if (m.account === "unreachable") return "暂时无法读取服务状态，请重试。";
  if (state.relogin) return "下一步：<b>登录另一个 MonoCloud 账户</b>，或取消保留当前账户。";
  if (m.needLogin && !m.oauth) return "暂时无法登录，需要部署者先完成配置。";
  if (m.needLogin) return "下一步：<b>登录 MonoCloud 账户</b>。";
  if (m.account === "unavailable") return "下一步：<b>重新验证账户</b>，或稍后再试。";
  if (m.account === "connected_empty") return "账户已验证，但没有可用套餐。";
  if (state.subFailed) return "订阅设置读取失败，请刷新页面重试。";
  if (!m.subOk) return "正在读取订阅设置…";
  if (m.unchosen && !m.dirty) return "下一步：<b>确认订阅内容</b>。";
  if (m.dirty) return "下一步：<b>保存订阅内容</b>。";
  if (!state.copied) return "下一步：<b>复制订阅链接</b>，导入客户端。";
  return "下一步：<b>按下面的说明在客户端添加或更新订阅</b>。";
}

function render() {
  const m = model();
  const values = [1, 2, 3, 4].map((n) => stepState(n, m));
  setStep("step-account", 1, values[0]);
  setStep("step-content", 2, values[1]);
  setStep("step-link", 3, values[2]);
  setStep("step-client", 4, values[3]);
  // Static markup only: the line never contains server-provided text.
  $("next-step").innerHTML = nextStep(m);
  renderAccount(m);
  renderContent(m);
  renderLink(m, values[2]);
  renderClient(m, values[3]);
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
    const response = await fetch("api/status?verify=true", { cache: "no-store" });
    if (!response.ok) throw new Error("status unavailable");
    state.status = await response.json();
  } catch {
    state.status = null;
    state.statusFailed = true;
  }
  render();
  return state.status?.account_state;
}

async function loadSubscription() {
  try {
    const response = await fetch("api/subscription", { cache: "no-store" });
    if (!response.ok) throw new Error("subscription unavailable");
    state.sub = await response.json();
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
  state.relogin = false;
  state.loginError = "";
  render();
  $("account-switch").focus();
});

$("verify-again").addEventListener("click", loadStatus);

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
      const account = await loadStatus();
      if (account === "connected") toast("账户已连接");
      else if (account === "expired") state.loginError = "登录结果已保存，但账户验证未通过，请重新登录。";
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

for (const radio of document.querySelectorAll('input[name="content"]')) {
  radio.addEventListener("change", () => {
    state.draft = radio.value === "tailscale";
    state.justSaved = false;
    state.saveFailed = false;
    render();
  });
}

$("content-undo").addEventListener("click", () => {
  state.draft = null;
  state.saveFailed = false;
  render();
});

$("content-save").addEventListener("click", async () => {
  if (state.saving || !state.sub) return;
  const m = model();
  const firstChoice = !state.sub.tailscale_choice_saved;
  state.saving = true;
  render();
  try {
    const response = await fetch("api/subscription", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailscale_enabled: m.chosen }),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("save failed");
    state.sub = await response.json();
    state.draft = null;
    state.saveFailed = false;
    state.justSaved = !firstChoice;
  } catch {
    state.saveFailed = true;
  } finally {
    state.saving = false;
    render();
  }
});

$("url-toggle").addEventListener("click", () => {
  state.urlOpen = !state.urlOpen;
  render();
});

function selectUrl() {
  const range = document.createRange();
  range.selectNodeContents(subscriptionUrl);
  const selection = getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  subscriptionUrl.focus();
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

$("copy-subscription").addEventListener("click", async () => {
  const url = state.sub?.url;
  if (!url) return;
  let copied = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(url);
      copied = true;
    } else {
      copied = legacyCopy(url);
    }
  } catch {
    copied = false;
  }
  state.copied = true; // Either way the user now has the link in hand.
  state.copyFailed = !copied;
  if (!copied) state.urlOpen = true;
  render();
  if (copied) toast("已复制订阅链接");
  else selectUrl();
});

download.addEventListener("click", () => {
  state.copied = true;
  render();
});

// Remember explicit toggles so automatic opening never fights the user.
guide?.querySelector("summary").addEventListener("click", () => {
  state.guideTouched = true;
});
tailscaleGuide?.querySelector("summary").addEventListener("click", () => {
  state.tailscaleGuideTouched = true;
});

render();
loadStatus();
loadSubscription();
