"use strict";

const form = document.querySelector("#login-form");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const toggle = document.querySelector("#password-toggle");
const submit = document.querySelector("#submit");
const submitLabel = document.querySelector("#submit-label");
const feedback = document.querySelector("#feedback");
const connection = document.querySelector("#connection");
const connectionTitle = document.querySelector("#connection-title");
const connectionDetail = document.querySelector("#connection-detail");
let configured = false;

function message(text, kind = "success") {
  feedback.textContent = text;
  feedback.dataset.kind = kind;
  feedback.hidden = false;
}

function savedStatus(saved) {
  connection.dataset.state = saved ? "saved" : "empty";
  connectionTitle.textContent = saved ? "登录凭据已保存" : "尚未保存登录凭据";
  connectionDetail.textContent = saved
    ? "需要更换账户或重新验证时，可再次登录。"
    : "登录后，当前服务会保存连接凭据。";
}

toggle.addEventListener("click", () => {
  const visible = password.type === "password";
  password.type = visible ? "text" : "password";
  toggle.textContent = visible ? "隐藏" : "显示";
  toggle.setAttribute("aria-label", visible ? "隐藏密码" : "显示密码");
  toggle.setAttribute("aria-pressed", String(visible));
});

async function loadStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status unavailable");
    const status = await response.json();
    configured = status.oauth_configured;
    savedStatus(status.token_saved);
    if (!configured) message("当前服务尚未配置登录参数，请联系部署者完成配置。", "error");
  } catch {
    connectionTitle.textContent = "暂时无法读取服务状态";
    connectionDetail.textContent = "请检查服务是否运行，并刷新页面重试。";
    message("无法连接当前服务，请刷新页面重试。", "error");
  }
  submit.disabled = !configured;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!configured || form.getAttribute("aria-busy") === "true") return;
  const payload = { email: email.value.trim(), password: password.value };
  feedback.hidden = true;
  form.setAttribute("aria-busy", "true");
  submitLabel.textContent = "正在验证…";
  for (const control of [email, password, toggle, submit]) control.disabled = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      const errors = {
        login_rejected: "登录未通过，请检查邮箱和密码后重试。",
        oauth_not_configured: "当前服务尚未配置登录参数，请联系部署者完成配置。",
        oauth_client_rejected: "服务的 MonoCloud 登录参数被拒绝，请联系部署者检查配置。",
        invalid_login_input: "请输入有效的邮箱与密码。",
        upstream_unavailable: "暂时无法连接 MonoCloud，请稍后重试。",
        token_save_failed: "登录验证已通过，但凭据保存失败，请检查服务的存储权限。",
      };
      const fallback = response.status >= 500
        ? "当前服务处理登录时发生错误，请稍后重试。"
        : "登录暂未完成，请稍后重试。";
      message(errors[result?.code] || fallback, "error");
    } else if (result?.token_saved !== true) {
      message("当前服务返回了无效的登录结果，请稍后重试。", "error");
    } else {
      savedStatus(true);
      message("登录成功，连接凭据已保存。", "success");
    }
  } catch {
    message("与当前服务的连接中断，请检查连接后重试。", "error");
  } finally {
    payload.password = "";
    password.value = "";
    password.type = "password";
    toggle.textContent = "显示";
    toggle.setAttribute("aria-label", "显示密码");
    toggle.setAttribute("aria-pressed", "false");
    form.setAttribute("aria-busy", "false");
    submitLabel.textContent = "登录 MonoCloud";
    for (const control of [email, password, toggle]) control.disabled = false;
    submit.disabled = !configured;
  }
});

loadStatus();


const subscriptionUrl = document.querySelector("#subscription-url");
const copySubscription = document.querySelector("#copy-subscription");
const downloadSubscription = document.querySelector("#download-subscription");
const subscriptionForm = document.querySelector("#subscription-form");
const tailscaleEnabled = document.querySelector("#tailscale-enabled");
const saveSubscription = document.querySelector("#save-subscription");
const subscriptionFeedback = document.querySelector("#subscription-feedback");
const subscriptionMode = document.querySelector("#subscription-mode");

function subscriptionMessage(text, kind = "success") {
  subscriptionFeedback.textContent = text;
  subscriptionFeedback.dataset.kind = kind;
  subscriptionFeedback.hidden = false;
}

function showSubscription(details) {
  subscriptionUrl.value = details.url;
  downloadSubscription.href = details.url;
  downloadSubscription.setAttribute("aria-disabled", "false");
  copySubscription.disabled = false;
  tailscaleEnabled.checked = details.tailscale_enabled;
  subscriptionMode.textContent = details.tailscale_enabled ? "MonoCloud + Tailscale" : "仅 MonoCloud";
  tailscaleEnabled.disabled = false;
  saveSubscription.disabled = false;
  const host = new URL(details.url).hostname;
  if (["localhost", "127.0.0.1", "[::1]"].includes(host)) {
    document.querySelector("#link-note").textContent = "此链接目前使用本机地址。供手机使用时，请配置手机可访问的服务地址。";
  }
}

async function loadSubscription() {
  try {
    const response = await fetch("/api/subscription", { cache: "no-store" });
    if (!response.ok) throw new Error("subscription unavailable");
    showSubscription(await response.json());
  } catch {
    subscriptionMessage("无法读取订阅设置，请检查服务后刷新页面。", "error");
  }
}

copySubscription.addEventListener("click", async () => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(subscriptionUrl.value);
    } else {
      subscriptionUrl.focus();
      subscriptionUrl.select();
      if (!document.execCommand("copy")) throw new Error("clipboard unavailable");
    }
    subscriptionMessage("链接已复制，可在 Clash Mi 中添加配置链接。");
  } catch {
    subscriptionUrl.focus();
    subscriptionUrl.select();
    subscriptionMessage("请手动复制上方链接。", "error");
  }
});

subscriptionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (subscriptionForm.getAttribute("aria-busy") === "true") return;
  subscriptionForm.setAttribute("aria-busy", "true");
  tailscaleEnabled.disabled = true;
  saveSubscription.disabled = true;
  try {
    const response = await fetch("/api/subscription", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tailscale_enabled: tailscaleEnabled.checked }), cache: "no-store",
    });
    if (!response.ok) throw new Error("save failed");
    showSubscription(await response.json());
    subscriptionMessage("设置已保存。请在 Clash Mi 更新订阅后重新连接。");
  } catch {
    subscriptionMessage("设置未能保存，请稍后重试。", "error");
  } finally {
    subscriptionForm.setAttribute("aria-busy", "false");
    tailscaleEnabled.disabled = false;
    saveSubscription.disabled = false;
  }
});

loadSubscription();
