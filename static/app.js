const state = {
  recipients: [],
  enabled: false,
};

const els = {
  onBtn: document.getElementById("onBtn"),
  offBtn: document.getElementById("offBtn"),
  powerLabel: document.getElementById("powerLabel"),
  sendTime: document.getElementById("sendTime"),
  emailTitle: document.getElementById("emailTitle"),
  newEmail: document.getElementById("newEmail"),
  addEmailBtn: document.getElementById("addEmailBtn"),
  recipientChips: document.getElementById("recipientChips"),
  fromName: document.getElementById("fromName"),
  fromEmail: document.getElementById("fromEmail"),
  fromPassword: document.getElementById("fromPassword"),
  saveBtn: document.getElementById("saveBtn"),
  approvedBtn: document.getElementById("approvedBtn"),
  toast: document.getElementById("toast"),
  statusMeta: document.getElementById("statusMeta"),
};

function showToast(message, isError = false) {
  els.toast.hidden = false;
  els.toast.textContent = message;
  els.toast.classList.toggle("error", isError);
}

function paintPower() {
  els.onBtn.setAttribute("aria-pressed", state.enabled ? "true" : "false");
  els.offBtn.setAttribute("aria-pressed", state.enabled ? "false" : "true");
  els.powerLabel.textContent = state.enabled ? "Emails on" : "Emails off";
}

function renderRecipients() {
  els.recipientChips.innerHTML = "";
  if (!state.recipients.length) {
    const empty = document.createElement("span");
    empty.className = "meta";
    empty.textContent = "None yet — add at least one";
    els.recipientChips.appendChild(empty);
    return;
  }

  state.recipients.forEach((email, index) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `<span>${email}</span>`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${email}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      state.recipients.splice(index, 1);
      renderRecipients();
    });
    chip.appendChild(remove);
    els.recipientChips.appendChild(chip);
  });
}

function applyConfig(config, cloud) {
  state.enabled = !!config.enabled;
  paintPower();
  els.sendTime.value = config.send_time || "08:00";
  els.emailTitle.value = config.email_title || "Daily News Brief";
  state.recipients = Array.isArray(config.recipients) ? [...config.recipients] : [];
  renderRecipients();

  els.fromName.value = config.from_name || "Daily News Brief";
  els.fromEmail.value = config.from_email || "";
  els.fromPassword.value = "";
  els.fromPassword.placeholder = config.password_set
    ? "Saved — leave blank to keep"
    : "Paste only the 16 letters";

  const waiting = !!(cloud && cloud.awaiting_approval);
  els.approvedBtn.hidden = !waiting;

  if (!config.enabled) {
    els.statusMeta.textContent = "Emails are off. Nothing will be sent.";
  } else if (waiting) {
    els.statusMeta.textContent = "Finish the Google page, then click I've finished the Google page.";
  } else if (!cloud || !cloud.ready) {
    els.statusMeta.textContent = "Click On and approve Gmail once. After that it sends even if this computer is closed or off.";
  } else if (config.last_error) {
    els.statusMeta.textContent = config.last_error.split("\n")[0];
  } else if (config.send_time) {
    els.statusMeta.textContent = `One email a day at ${config.send_time}, even if this computer is closed, asleep, or off.`;
  } else {
    els.statusMeta.textContent = "";
  }
}

async function loadConfig(attempt = 0) {
  try {
    const res = await fetch("/api/config", { cache: "no-store" });
    if (!res.ok) {
      throw new Error("Couldn't load your settings.");
    }
    const data = await res.json();
    applyConfig(data.config, data.cloud);
    if (!els.toast.classList.contains("error")) {
      els.toast.hidden = true;
    }
  } catch (err) {
    const offline = err instanceof TypeError;
    if (offline && attempt < 6) {
      showToast("Connecting to Daily News Brief…");
      setTimeout(() => loadConfig(attempt + 1), 700);
      return;
    }
    showToast(
      offline
        ? "Couldn't reach the app. Double-click start_dashboard.bat and leave that window open."
        : err.message || String(err),
      true
    );
  }
}

function formPayload() {
  const payload = {
    enabled: state.enabled,
    send_time: els.sendTime.value,
    email_title: els.emailTitle.value.trim(),
    recipients: state.recipients,
    from_name: els.fromName.value.trim(),
    from_email: els.fromEmail.value.trim(),
  };
  if (els.fromPassword.value.trim()) {
    payload.password = els.fromPassword.value.trim();
  }
  return payload;
}

async function saveConfig() {
  els.saveBtn.disabled = true;
  els.onBtn.disabled = true;
  els.offBtn.disabled = true;
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formPayload()),
      cache: "no-store",
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Save failed");
    }
    applyConfig(data.config, data.cloud);
    showToast(data.message || "Saved.");
  } catch (err) {
    const offline = err instanceof TypeError;
    showToast(
      offline
        ? "Couldn't reach the app. Leave the Daily News Brief window open and try again."
        : err.message || String(err),
      true
    );
    loadConfig();
  } finally {
    els.saveBtn.disabled = false;
    els.onBtn.disabled = false;
    els.offBtn.disabled = false;
  }
}

async function setEnabled(next) {
  if (next === state.enabled) return;
  if (next && (!els.fromEmail.value.trim() || !state.recipients.length)) {
    showToast("Add your Gmail address and at least one recipient, then click On.", true);
    return;
  }
  state.enabled = next;
  paintPower();
  showToast(next ? "Turning emails on…" : "Turning emails off…");
  await saveConfig();
}

function addEmail() {
  const email = els.newEmail.value.trim();
  if (!email) return;
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    showToast("Enter a valid email address.", true);
    return;
  }
  if (!state.recipients.includes(email)) {
    state.recipients.push(email);
    renderRecipients();
  }
  els.newEmail.value = "";
  els.newEmail.focus();
}

async function confirmApproval() {
  els.approvedBtn.disabled = true;
  try {
    const res = await fetch("/api/cloud/confirm", { method: "POST", cache: "no-store" });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Could not finish setup.");
    }
    applyConfig(data.config, data.cloud);
    showToast(data.message || "Scheduled.");
  } catch (err) {
    showToast(err.message || String(err), true);
  } finally {
    els.approvedBtn.disabled = false;
  }
}

els.onBtn.addEventListener("click", () => setEnabled(true));
els.offBtn.addEventListener("click", () => setEnabled(false));
els.addEmailBtn.addEventListener("click", addEmail);
els.newEmail.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    addEmail();
  }
});
els.saveBtn.addEventListener("click", saveConfig);
els.approvedBtn.addEventListener("click", confirmApproval);

loadConfig();
