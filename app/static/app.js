const app = document.querySelector("#app");
let token = sessionStorage.getItem("token") || "";
let me = null;
let selectedId = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function shortDate(iso) {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }).replace(",", "");
}

function weekLabel(start, end) {
  const a = new Date(`${start}T00:00:00`);
  const b = new Date(`${end}T00:00:00`);
  const left = a.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
  const right = b.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return `${left} to ${right}`;
}

function scoreClass(score) {
  if (score >= 80) return "high";
  if (score >= 70) return "mid";
  return "";
}

function statusLabel(status) {
  return { new: "New", contacted: "Contacted", quote_sent: "Quote sent", won: "Won" }[status] || status;
}

function lateLabel(count) {
  if (!count) return "—";
  if (count === 1) return "1 lead";
  return `${count} stuck`;
}

function pct(value) {
  return value == null ? "" : `${value}%`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && token) {
    token = "";
    sessionStorage.removeItem("token");
    renderLogin("Sign in again.");
    throw new Error("unauthorized");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Something went wrong");
  }
  if (response.headers.get("content-type")?.includes("text/csv")) return response;
  return response.json();
}

function renderLogin(message = "") {
  app.innerHTML = `
    <div class="login-wrap">
      <form class="login-card" id="login">
        <div class="brand"><span class="mark"></span> WHITE LIGHT · LEADS</div>
        <h1>Sign in</h1>
        <p>Salesmen see their own leads. The CEO and managers see the week.</p>
        <label for="email">Email</label>
        <input id="email" name="email" type="email" autocomplete="username" required>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required>
        <p class="error">${esc(message)}</p>
        <button class="primary" type="submit">Sign in</button>
        <p class="hint">Sample salesman: ahmed@example.com<br>Password: password123<br>CEO: the email and password in your .env file.</p>
      </form>
    </div>`;
  document.querySelector("#login").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    try {
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      token = body.access_token;
      sessionStorage.setItem("token", token);
      await boot();
    } catch (error) {
      if (error.message !== "unauthorized") renderLogin(error.message);
    }
  });
}

function shell(sample, extra = "") {
  return `
    <header class="topbar">
      <div class="brand"><span class="mark"></span> WHITE LIGHT · LEADS</div>
      <div class="top-actions">
        ${sample ? '<span class="badge">SAMPLE DATA</span>' : ""}
        ${extra}
        <button class="linkish" id="signout" type="button">Sign out</button>
      </div>
    </header>`;
}

function bindSignOut() {
  document.querySelector("#signout").addEventListener("click", () => {
    token = "";
    me = null;
    sessionStorage.removeItem("token");
    renderLogin();
  });
}

function leadButton(lead, selected) {
  const when = lead.status === "quote_sent" && lead.quote_sent_on
    ? `Quote sent ${shortDate(lead.quote_sent_on)}`
    : lead.contact_by
      ? `Contact by ${shortDate(lead.contact_by)}`
      : "";
  return `
    <button class="lead-row ${selected ? "selected" : ""}" data-id="${lead.id}" type="button">
      <span class="score ${scoreClass(lead.score)}">${lead.score}</span>
      <span>
        <span class="row-top">
          <strong>${esc(lead.name)}</strong>
          <span class="pill ${esc(lead.status)}">${esc(statusLabel(lead.status))}</span>
        </span>
        <span class="meta">${esc(lead.category)} · ${esc(lead.area)}</span><br>
        <span class="meta">${esc(lead.summary)}</span>
        ${when ? `<br><span class="when">${esc(when)}</span>` : ""}
      </span>
    </button>`;
}

function renderDesk(list, detail) {
  app.innerHTML = `
    ${shell(list.sample_data)}
    <main class="workspace">
      <section class="panel list" id="list">
        <div class="panel-head">
          <h2>My leads</h2>
          <p class="sub">${esc(list.salesman_name)} · ${list.to_contact} to contact this week</p>
        </div>
        ${list.leads.map((lead) => leadButton(lead, lead.id === detail.id)).join("")}
      </section>
      <section class="panel detail open" id="detail">
        ${renderDetail(detail)}
      </section>
    </main>`;
  bindSignOut();
  document.querySelectorAll(".lead-row").forEach((button) => {
    button.addEventListener("click", () => openLead(Number(button.dataset.id), list));
  });
  bindDetail(detail, () => showSalesman());
}

function renderDetail(lead) {
  const phone = lead.phone ? lead.phone.replace(/^\+973/, "+973 ") : "";
  return `
    <div class="detail-head">
      <button class="linkish" id="back" type="button">Back</button>
      <div class="row-top">
        <span class="score ${scoreClass(lead.score)}">${lead.score}</span>
        <span class="pill ${esc(lead.status)}">${esc(statusLabel(lead.status))}</span>
      </div>
      <h2>${esc(lead.name)}</h2>
      <p class="sub">${esc(lead.category)} · ${esc(lead.area)}${phone ? ` · ${esc(phone)}` : ""}</p>
    </div>
    <div class="section">
      <h3>Why this lead scores ${lead.score}</h3>
      ${lead.reasons.map((reason) => `
        <div class="reason">
          <span>${esc(reason.text)}</span>
          <b class="${reason.points ? "" : "zero"}">+${reason.points}</b>
        </div>`).join("")}
    </div>
    <div class="section">
      <h3>First message <span class="lang">EN</span></h3>
      <div class="message" id="message">${esc(lead.message)}</div>
    </div>
    <div class="actions">
      <button class="ghost" id="copy" type="button">Copy message</button>
      <button class="primary" id="whatsapp" type="button" ${lead.phone ? "" : "disabled"}>Open WhatsApp</button>
    </div>
    <div class="status-actions">
      <button class="ghost" data-status="contacted" type="button">Mark contacted</button>
      <button class="ghost" data-status="quote_sent" type="button">Quote sent</button>
      <button class="ghost" data-status="won" type="button">Won</button>
    </div>`;
}

function bindDetail(lead, refresh) {
  const back = document.querySelector("#back");
  back.addEventListener("click", () => {
    document.querySelector("#list")?.classList.remove("hidden");
    document.querySelector("#detail")?.classList.remove("open");
  });
  document.querySelector("#copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(lead.message);
    const button = document.querySelector("#copy");
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy message"; }, 1200);
  });
  document.querySelector("#whatsapp").addEventListener("click", () => {
    const digits = lead.phone.replace(/\D/g, "");
    const url = `https://wa.me/${digits}?text=${encodeURIComponent(lead.message)}`;
    window.open(url, "_blank", "noopener");
  });
  document.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      const updated = await api(`/leads/${lead.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: button.dataset.status }),
      });
      selectedId = updated.id;
      refresh();
    });
  });
  if (window.matchMedia("(max-width: 860px)").matches) {
    document.querySelector("#list")?.classList.add("hidden");
  }
}

async function openLead(id, list) {
  selectedId = id;
  const detail = await api(`/leads/${id}`);
  renderDesk(list, detail);
}

async function showSalesman() {
  const list = await api("/leads/mine");
  if (!list.leads.length) {
    app.innerHTML = `${shell(list.sample_data)}<main class="desk"><h2>No leads yet</h2></main>`;
    bindSignOut();
    return;
  }
  const id = selectedId && list.leads.some((lead) => lead.id === selectedId) ? selectedId : list.leads[0].id;
  const detail = await api(`/leads/${id}`);
  renderDesk(list, detail);
}

function renderOverview(report) {
  const max = report.new_leads || 1;
  const bar = (count, kind) => `<div class="bar ${kind}"><span style="width:${Math.round((count / max) * 100)}%"></span></div>`;
  app.innerHTML = `
    ${shell(report.sample_data, '<button class="gold" id="export" type="button">Export leads (CSV)</button>')}
    <main class="desk">
      <section class="hero">
        <h2>This week: ${report.won} deals won from ${report.new_leads} new leads</h2>
        <p class="sub">${esc(weekLabel(report.week_start, report.week_end))} · the same summary goes to the CEO in WhatsApp every Sunday</p>
      </section>
      <section class="cards">
        <article class="card funnel">
          <h3>From lead to sale</h3>
          <div class="funnel-row"><span>New leads</span>${bar(report.new_leads, "new")}<b>${report.new_leads}</b></div>
          <div class="funnel-row"><span>Contacted</span>${bar(report.contacted, "contacted")}<b>${report.contacted} ${pct(report.contacted_pct)}</b></div>
          <div class="funnel-row"><span>Quote sent</span>${bar(report.quotes, "quotes")}<b>${report.quotes} ${pct(report.quotes_pct)}</b></div>
          <div class="funnel-row"><span>Won</span>${bar(report.won, "won")}<b>${report.won} ${pct(report.won_pct)}</b></div>
        </article>
        <article class="card">
          <h3>By salesman</h3>
          <table>
            <thead><tr><th>Salesman</th><th>Assigned</th><th>Contacted</th><th>Quotes</th><th>Won</th><th>Not contacted on time</th></tr></thead>
            <tbody>
              ${report.by_salesman.map((row) => `
                <tr>
                  <td>${esc(row.name)}</td>
                  <td>${row.assigned}</td>
                  <td>${row.contacted}</td>
                  <td>${row.quotes}</td>
                  <td>${row.won}</td>
                  <td class="late">${esc(lateLabel(row.late))}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </article>
        <article class="card">
          <h3>Which sources work</h3>
          <table>
            <thead><tr><th>Source</th><th>Leads</th><th>Quotes</th><th>Won</th></tr></thead>
            <tbody>
              ${report.sources.map((row) => `
                <tr class="${row.enabled ? "" : "off"}">
                  <td>${esc(row.label)}</td>
                  <td>${row.enabled ? row.leads : "—"}</td>
                  <td>${row.enabled ? row.quotes : "—"}</td>
                  <td>${row.enabled ? row.won : "—"}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </article>
      </section>
      <section class="card waiting">
        <h3>Imported today, waiting to be assigned</h3>
        <p class="sub">Not yet counted in this week's numbers.</p>
        ${report.unassigned.map((lead) => `
          <div class="wait-row">
            <span class="score ${scoreClass(lead.score)}">${lead.score}</span>
            <span>
              <strong>${esc(lead.name)}</strong>
              <span class="meta">${esc(lead.category)} · ${esc(lead.area)} · ${esc(lead.summary)}</span>
            </span>
            <span class="wait-actions">
              <select data-suggest="${lead.id}">
                ${report.salesmen.map((person) => `
                  <option value="${person.id}" ${person.id === lead.suggested_salesman_id ? "selected" : ""}>
                    ${esc(person.name)}
                  </option>`).join("")}
              </select>
              <button class="ghost" data-assign="${lead.id}" type="button">Assign</button>
            </span>
          </div>`).join("")}
      </section>
    </main>`;
  bindSignOut();
  document.querySelector("#export").addEventListener("click", downloadCsv);
  document.querySelectorAll("[data-assign]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.assign;
      const salesmanId = Number(document.querySelector(`[data-suggest="${id}"]`).value);
      await api(`/leads/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ salesman_id: salesmanId }),
      });
      await showOverview();
    });
  });
}

async function downloadCsv() {
  const response = await api("/leads/export");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "leads.csv";
  link.click();
  URL.revokeObjectURL(url);
}

async function showOverview() {
  renderOverview(await api("/leads/overview"));
}

async function boot() {
  me = await api("/auth/me");
  if (me.role === "salesman") await showSalesman();
  else await showOverview();
}

if (token) boot().catch(() => renderLogin());
else renderLogin();
