(() => {
  const $ = (sel) => document.querySelector(sel);
  const money = (n) => Number(n).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let accounts = [];

  async function api(url, method = "GET", body) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
      // session expired or not logged in
      window.location.href = "/login";
      throw new Error("Please log in.");
    }
    const data = await res.json().catch(() => ({ ok: false, error: "Server error." }));
    if (!res.ok || !data.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }

  let toastTimer;
  function toast(msg, isError = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast" + (isError ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 3200);
  }

  // ---------- rendering ----------
  async function loadStats() {
    const s = await api("/api/stats");
    $("#statMoney").textContent = money(s.money);
    $("#statTotal").textContent = s.total;
    $("#statSaving").textContent = s.saving;
    $("#statCurrent").textContent = s.current;
  }

  function renderAccounts() {
    const q = $("#search").value.trim().toLowerCase();
    const list = accounts.filter((a) => a.name.toLowerCase().includes(q) || a.acc_no.toLowerCase().includes(q));
    $("#accountsBody").innerHTML = list
      .map(
        (a) => `<tr>
          <td class="mono">${esc(a.acc_no)}</td>
          <td>${esc(a.name)}</td>
          <td><span class="pill ${a.type}">${a.type_name}</span></td>
          <td class="num">${money(a.balance)}</td>
          <td class="actions">
            <button class="mini" data-act="deposit" data-id="${esc(a.acc_no)}">Deposit</button>
            <button class="mini" data-act="withdraw" data-id="${esc(a.acc_no)}">Withdraw</button>
            <button class="mini" data-act="edit" data-id="${esc(a.acc_no)}">Edit</button>
            <button class="mini danger" data-act="close" data-id="${esc(a.acc_no)}">Close</button>
          </td></tr>`
      )
      .join("");
    $("#emptyAccounts").hidden = list.length > 0;
  }

  async function loadAccounts() {
    accounts = (await api("/api/accounts")).accounts;
    renderAccounts();
  }

  async function loadActivity() {
    const rows = (await api("/api/transactions")).transactions;
    $("#activityBody").innerHTML = rows
      .map(
        (t) => `<tr>
          <td>${esc(t.at)}</td>
          <td class="mono">${esc(t.acc_no)}</td>
          <td><span class="pill ${t.kind}">${t.kind}</span></td>
          <td class="num">${money(t.amount)}</td>
          <td class="num">${money(t.balance)}</td></tr>`
      )
      .join("");
    $("#emptyActivity").hidden = rows.length > 0;
  }

  async function refresh() {
    await Promise.all([loadAccounts(), loadStats(), loadActivity()]);
  }

  // ---------- modal ----------
  const modal = $("#modal");
  let onSubmit = null;

  function openModal({ title, fields, submitLabel = "Save", danger = false, submit }) {
    $("#modalTitle").textContent = title;
    $("#modalFields").innerHTML = fields;
    $("#modalError").hidden = true;
    const btn = $("#modalSubmit");
    btn.textContent = submitLabel;
    btn.className = "btn " + (danger ? "danger" : "primary");
    onSubmit = submit;
    modal.showModal();
    const first = $("#modalFields input, #modalFields select");
    if (first) first.focus();
  }

  $("#modalCancel").addEventListener("click", () => modal.close());
  $("#modalForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = Object.fromEntries(new FormData(e.target));
    const btn = $("#modalSubmit");
    btn.disabled = true;
    try {
      await onSubmit(form);
      modal.close();
    } catch (err) {
      $("#modalError").textContent = err.message;
      $("#modalError").hidden = false;
    } finally {
      btn.disabled = false;
    }
  });

  const typeSelect = (value = "S") => `
    <label class="field">Account type
      <select name="type">
        <option value="S" ${value === "S" ? "selected" : ""}>Saving (minimum 500)</option>
        <option value="C" ${value === "C" ? "selected" : ""}>Current (minimum 1000)</option>
      </select>
    </label>`;

  // ---------- actions ----------
  $("#openCreate").addEventListener("click", () =>
    openModal({
      title: "New account",
      submitLabel: "Create account",
      fields: `
        <label class="field">Account number <span class="hint">letters or digits, e.g. 1001</span>
          <input name="acc_no" required maxlength="20"></label>
        <label class="field">Account holder name
          <input name="name" required maxlength="60"></label>
        ${typeSelect()}
        <label class="field">Initial amount
          <input name="amount" type="number" min="0" step="0.01" required></label>`,
      submit: async (f) => {
        await api("/api/accounts", "POST", f);
        toast("Account created");
        await refresh();
      },
    })
  );

  $("#accountsBody").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const acc = accounts.find((a) => a.acc_no === btn.dataset.id);
    if (!acc) return;
    const act = btn.dataset.act;

    if (act === "deposit" || act === "withdraw") {
      const isDep = act === "deposit";
      openModal({
        title: `${isDep ? "Deposit to" : "Withdraw from"} ${acc.acc_no}`,
        submitLabel: isDep ? "Deposit" : "Withdraw",
        fields: `<p class="hint">${esc(acc.name)} &middot; balance ${money(acc.balance)}${
          isDep ? "" : ` &middot; minimum to keep ${acc.min_balance}`
        }</p>
          <label class="field">Amount
            <input name="amount" type="number" min="0" step="0.01" required></label>`,
        submit: async (f) => {
          await api(`/api/accounts/${encodeURIComponent(acc.acc_no)}/${act}`, "POST", f);
          toast(isDep ? "Amount deposited" : "Amount withdrawn");
          await refresh();
        },
      });
    } else if (act === "edit") {
      openModal({
        title: `Edit account ${acc.acc_no}`,
        fields: `
          <label class="field">Account holder name
            <input name="name" required maxlength="60" value="${esc(acc.name)}"></label>
          ${typeSelect(acc.type)}
          <label class="field">Balance
            <input name="amount" type="number" min="0" step="0.01" required value="${acc.balance}"></label>`,
        submit: async (f) => {
          await api(`/api/accounts/${encodeURIComponent(acc.acc_no)}`, "PUT", f);
          toast("Account updated");
          await refresh();
        },
      });
    } else if (act === "close") {
      openModal({
        title: `Close account ${acc.acc_no}?`,
        submitLabel: "Close account",
        danger: true,
        fields: `<p>This will permanently delete the account of <strong>${esc(acc.name)}</strong> (balance ${money(acc.balance)}). This cannot be undone.</p>`,
        submit: async () => {
          await api(`/api/accounts/${encodeURIComponent(acc.acc_no)}`, "DELETE");
          toast("Account closed");
          await refresh();
        },
      });
    }
  });

  $("#search").addEventListener("input", renderAccounts);

  // ---------- tabs ----------
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      ["accounts", "activity", "enquiry"].forEach((name) => {
        $("#tab-" + name).hidden = name !== tab.dataset.tab;
      });
      if (tab.dataset.tab === "activity") loadActivity().catch((e) => toast(e.message, true));
    })
  );

  // ---------- balance enquiry ----------
  $("#enquiryForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = $("#enquiryResult");
    const accNo = new FormData(e.target).get("acc_no").trim();
    try {
      const { account: a } = await api("/api/accounts/" + encodeURIComponent(accNo));
      box.innerHTML = `<span>Account ${esc(a.acc_no)} &middot; ${esc(a.name)} &middot; ${a.type_name}</span>
        <span class="big">${money(a.balance)}</span>`;
    } catch (err) {
      box.innerHTML = `<span>${esc(err.message)}</span>`;
    }
    box.hidden = false;
  });

  refresh().catch((e) => toast(e.message, true));
})();
