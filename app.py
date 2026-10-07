"""ShowBoss AV multi-user CRM with Flex Rental Solutions proxy."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / "crm.db"
SECRET = os.environ.get("CRM_SECRET") or "showboss-dev-secret-change-me"

app = FastAPI(title="ShowBoss AV CRM")
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax")

STAGES = {
    "event": ["Inquiry", "Qualification", "Proposal", "Negotiation", "Confirmed", "Delivered"],
    "install": ["Inquiry", "Site survey", "Design & quote", "Proposal", "Confirmed", "Installed"],
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_pw(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def check_pw(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(digest, test)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY,
          username TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          password TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'sales'
        );
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        CREATE TABLE IF NOT EXISTS accounts (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          type TEXT,
          city TEXT,
          state TEXT,
          notes TEXT,
          flex_id TEXT
        );
        CREATE TABLE IF NOT EXISTS contacts (
          id INTEGER PRIMARY KEY,
          account_id INTEGER,
          name TEXT NOT NULL,
          title TEXT,
          email TEXT,
          phone TEXT,
          flex_id TEXT
        );
        CREATE TABLE IF NOT EXISTS deals (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          account_id INTEGER,
          contact_id INTEGER,
          pipeline TEXT NOT NULL,
          stage TEXT NOT NULL,
          value REAL DEFAULT 0,
          event_date TEXT,
          owner TEXT,
          notes TEXT,
          flex_id TEXT,
          flex_number TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS call_log (
          id INTEGER PRIMARY KEY,
          name TEXT,
          note TEXT,
          user_name TEXT,
          at TEXT
        );
        """
    )
    if not conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        conn.execute(
            "INSERT INTO users (username, name, password, role) VALUES (?,?,?,?)",
            ("admin", "Justin Taft", hash_pw("showboss"), "admin"),
        )
    if not conn.execute("SELECT 1 FROM accounts").fetchone():
        seed(conn)
    if not conn.execute("SELECT 1 FROM settings WHERE key='flex_subdomain'").fetchone():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('flex_subdomain', ?)",
            (os.environ.get("FLEX_SUBDOMAIN", ""),),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('flex_api_key', ?)",
            (os.environ.get("FLEX_API_KEY", ""),),
        )
    conn.commit()
    conn.close()


def seed(conn):
    accounts = [
        ("City of Tempe", "City / town", "Tempe", "AZ", "Festival and city events."),
        ("Desert FC", "Pro sports", "Phoenix", "AZ", "Match-day video."),
        ("Northline Hotels", "Corporate", "Scottsdale", "AZ", "Leadership summits."),
        ("Redline Nightclub", "Hospitality", "Las Vegas", "NV", "Permanent LED wall."),
        ("Westfield High", "School", "Mesa", "AZ", "Stadium scoreboard."),
    ]
    for row in accounts:
        conn.execute(
            "INSERT INTO accounts (name, type, city, state, notes) VALUES (?,?,?,?,?)", row
        )
    conn.execute(
        "INSERT INTO deals (name, account_id, pipeline, stage, value, event_date, owner, notes, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("Mill Ave Festival IMAG", 1, "event", "Proposal", 86500, "2026-11-14", "Justin Taft", "LED, IMAG, delay towers.", now()),
    )
    conn.execute(
        "INSERT INTO deals (name, account_id, pipeline, stage, value, event_date, owner, notes, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("Stadium video scoreboard", 5, "install", "Inquiry", 210000, "2027-06-01", "Justin Taft", "Bond-funded board replacement.", now()),
    )


def setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def user(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None
    conn = db()
    row = conn.execute("SELECT id, username, name, role FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def flex_base(conn):
    sub = (setting(conn, "flex_subdomain") or "").strip().replace("https://", "").split(".")[0]
    return sub, f"https://{sub}.flexrentalsolutions.com/f5/api" if sub else ""


async def flex_get(path: str, params: dict | None = None):
    conn = db()
    sub, base = flex_base(conn)
    key = setting(conn, "flex_api_key")
    conn.close()
    if not sub or not key:
        return 400, {"error": "Set the Flex subdomain and API key in Settings."}
    url = base + path
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            res = await client.get(url, params=params, headers={"X-Auth-Token": key, "Accept": "application/json"})
        try:
            body = res.json()
        except Exception:
            body = {"raw": res.text[:2000]}
        return res.status_code, body
    except httpx.HTTPError as exc:
        return 502, {"error": str(exc)}


init()

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ShowBoss AV CRM</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
:root { --bg:#ffffff; --bg2:#f5f8fb; --bg3:#eaf4ff; --line:#e3e8ef; --steel:#3d4a5c; --muted:#6b7686; --text:#12171f; --blue:#299fff; --amber:#b8860b; --green:#1f8a4c; --danger:#c44747; }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font-family:"Instrument Sans",sans-serif; }
button,input,select,textarea { font-family:inherit; color:inherit; } button { cursor:pointer; }
.app { display:grid; grid-template-columns:240px 1fr; min-height:100vh; }
.side { background:#fff; border-right:1px solid var(--line); padding:18px 14px; display:flex; flex-direction:column; gap:16px; }
.brand img { height:46px; width:auto; display:block; }
nav button, .ghost, .primary, .danger { border:1px solid var(--line); background:#fff; color:var(--steel); border-radius:10px; padding:9px 12px; font-weight:600; }
nav { display:flex; flex-direction:column; gap:4px; } nav button { text-align:left; } nav button.on, nav button:hover { background:var(--bg3); color:var(--blue); border-color:#b9ddff; }
.primary { background:var(--blue); color:#fff; border-color:var(--blue); } .danger { color:var(--danger); }
.side-foot { margin-top:auto; display:flex; flex-direction:column; gap:8px; }
.top { display:flex; justify-content:space-between; align-items:center; padding:16px 22px; border-bottom:1px solid var(--line); position:sticky; top:0; background:#fff; }
.view { padding:20px 22px 40px; } h2 { margin:0; } .sub { color:var(--muted); font-size:13px; }
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:14px; }
.stat, .card, .deal, .col { background:#fff; border:1px solid var(--line); border-radius:14px; }
.stat { padding:14px; } .k { color:var(--muted); font-size:11px; letter-spacing:.08em; text-transform:uppercase; } .v { font-size:24px; font-weight:650; margin-top:4px; color:var(--blue); }
.amber { color:var(--amber); } .green { color:var(--green); }
.board { display:grid; grid-template-columns:repeat(6,minmax(210px,1fr)); gap:10px; overflow:auto; }
.col { min-height:380px; background:var(--bg2); } .head { display:flex; justify-content:space-between; padding:10px 12px; font-size:13px; }
.cards { padding:6px; display:flex; flex-direction:column; gap:8px; min-height:70px; }
.deal { padding:11px; cursor:grab; background:#fff; } .deal .acct { color:var(--muted); font-size:12px; margin:4px 0 8px; }
.money { font-family:"IBM Plex Mono",monospace; }
.pill { border-radius:999px; padding:2px 8px; font-size:12px; font-weight:650; background:#eef2f6; color:var(--steel); }
.pill.inquiry { background:#e7f4ff; color:var(--blue); } .pill.confirmed { background:#e7f6ec; color:var(--green); }
table { width:100%; border-collapse:collapse; font-size:14px; } th,td { text-align:left; padding:8px; border-bottom:1px solid var(--line); } th { color:var(--muted); font-size:12px; text-transform:uppercase; }
tr.click { cursor:pointer; } tr.click:hover td { background:#f3f9ff; }
input,select,textarea { background:#fff; border:1px solid var(--line); border-radius:10px; padding:8px 10px; }
.seg { display:flex; gap:6px; margin-bottom:12px; } .modal { position:fixed; inset:0; background:rgba(18,23,31,.35); display:grid; place-items:center; } .box { width:min(560px,94vw); background:#fff; border:1px solid var(--line); border-radius:16px; padding:16px; }
label { display:grid; gap:4px; font-size:12px; color:var(--muted); margin-bottom:8px; } .row { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.login { min-height:100vh; display:grid; place-items:center; background:#fff; } .err { color:var(--danger); font-size:13px; }
.flex-hit { border-bottom:1px solid var(--line); padding:8px 0; display:flex; justify-content:space-between; gap:8px; align-items:center; }
@media (max-width:900px) { .app { grid-template-columns:1fr; } .stats { grid-template-columns:1fr 1fr; } }
</style>
</head>
<body>
<div id="app"></div>
<script>
const $ = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; };
let me = null, view = "dash", pipe = "event", data = {};
async function api(path, opts={}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401) { me = null; render(); throw new Error("auth"); }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || res.statusText);
  return json;
}
async function boot() {
  const res = await fetch("/api/me");
  if (res.ok) { me = await res.json(); await load(); }
  render();
}
async function load() { data = await api("/api/board"); }
function money(n) { return "$" + Number(n||0).toLocaleString(); }
function esc(s) { return String(s??"").replace(/[&<>"']/g, m => ({'&':'&','<':'<','>':'>','"':'"',"'":'&#39;'}[m])); }
function render() {
  const root = document.getElementById("app");
  root.innerHTML = "";
  if (!me) { root.append(login()); return; }
  const shell = document.createElement("div");
  shell.className = "app";
  shell.innerHTML = `<aside class="side"><div class="brand"><img src="https://showbossav.com/wp-content/uploads/2025/11/SB-Refresh-Logos_Blue-Shade-Black-Fly-scaled.png" alt="ShowBoss AV"></div>
    <nav>
      <button data-v="dash" class="${view==='dash'?'on':''}">Dashboard</button>
      <button data-v="inquiry" class="${view==='inquiry'?'on':''}">Inquiry leads</button>
      <button data-v="calls" class="${view==='calls'?'on':''}">Call list</button>
      <button data-v="pipe" class="${view==='pipe'?'on':''}">Pipeline</button>
      <button data-v="accounts" class="${view==='accounts'?'on':''}">Accounts</button>
      <button data-v="flex" class="${view==='flex'?'on':''}">Flex</button>
      <button data-v="settings" class="${view==='settings'?'on':''}">Settings</button>
    </nav>
    <div class="side-foot"><button class="primary" id="newDeal">New deal</button><button class="ghost" id="logout">Sign out</button></div></aside>
    <main><header class="top"><div><h2 id="ttl"></h2><div class="sub">ShowBoss AV · showbossav.flexrentalsolutions.com</div></div></header><section class="view" id="view"></section></main>`;
  root.append(shell);
  shell.querySelectorAll("nav button").forEach(b => b.onclick = () => { view = b.dataset.v; render(); });
  shell.querySelector("#logout").onclick = async () => { await fetch("/api/logout", {method:"POST"}); me = null; render(); };
  shell.querySelector("#newDeal").onclick = () => dealForm();
  const viewEl = shell.querySelector("#view");
  const titles = {dash:"Dashboard", inquiry:"Inquiry leads", calls:"Call list", pipe:"Pipeline", accounts:"Accounts", flex:"Flex Rental Solutions", settings:"Settings"};
  shell.querySelector("#ttl").textContent = titles[view];
  if (view === "dash") viewEl.append(dash());
  if (view === "inquiry") inquiryView(viewEl);
  if (view === "calls") callsView(viewEl);
  if (view === "pipe") viewEl.append(pipeline());
  if (view === "accounts") viewEl.append(accounts());
  if (view === "flex") flexView(viewEl);
  if (view === "settings") settingsView(viewEl);
}
function login() {
  const el = $(`<div class="login"><form class="box" id="f"><div class="brand" style="margin-bottom:12px"><div class="mark">SB</div><strong>ShowBoss AV CRM</strong></div>
    <label>Username<input name="username" autocomplete="username" required></label>
    <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
    <div class="err" id="err"></div><button class="primary" type="submit">Sign in</button>
    <p class="sub">First login admin / showboss. Change it in Settings.</p></form></div>`);
  el.querySelector("#f").onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target));
    const res = await fetch("/api/login", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    if (!res.ok) { el.querySelector("#err").textContent = "Wrong username or password."; return; }
    me = await res.json(); await load(); render();
  };
  return el;
}
function dash() {
  const deals = data.deals || [];
  const open = deals.filter(d => !["Lost","Delivered","Installed"].includes(d.stage));
  const el = document.createElement("div");
  el.innerHTML = `<div class="stats">
    <div class="stat"><div class="k">Open pipeline</div><div class="v">${money(open.reduce((s,d)=>s+Number(d.value),0))}</div></div>
    <div class="stat"><div class="k">Deals</div><div class="v">${open.length}</div></div>
    <div class="stat"><div class="k">Inquiry</div><div class="v amber">${open.filter(d=>d.stage==="Inquiry").length}</div></div>
    <div class="stat"><div class="k">Confirmed</div><div class="v green">${deals.filter(d=>d.stage==="Confirmed").length}</div></div></div>
    <div class="card" style="padding:8px 12px"><table><thead><tr><th>Deal</th><th>Line</th><th>Stage</th><th>Value</th><th>Flex</th></tr></thead><tbody>
    ${deals.map(d=>`<tr class="click" data-id="${d.id}"><td>${esc(d.name)}<div class="sub">${esc(d.account_name||"")}</div></td><td>${d.pipeline}</td><td><span class="pill ${d.stage==="Inquiry"?"inquiry":d.stage==="Confirmed"?"confirmed":""}">${esc(d.stage)}</span></td><td class="money">${money(d.value)}</td><td>${esc(d.flex_number||"—")}</td></tr>`).join("")}
    </tbody></table></div>`;
  el.querySelectorAll("[data-id]").forEach(r => r.onclick = () => openDeal(r.dataset.id));
  return el;
}
function pipeline() {
  const stages = data.stages[pipe];
  const el = document.createElement("div");
  el.innerHTML = `<div class="seg"><button class="ghost ${pipe==="event"?"on":""}" data-p="event">Event rentals</button><button class="ghost ${pipe==="install"?"on":""}" data-p="install">Permanent installs</button></div><div class="board"></div>`;
  el.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { pipe = b.dataset.p; render(); });
  const board = el.querySelector(".board");
  stages.forEach(stage => {
    const items = (data.deals||[]).filter(d => d.pipeline===pipe && d.stage===stage);
    const col = document.createElement("div");
    col.className = "col";
    col.innerHTML = `<div class="head"><strong>${stage}</strong><span class="sub">${items.length}</span></div><div class="cards" data-stage="${stage}"></div>`;
    const cards = col.querySelector(".cards");
    items.forEach(d => {
      const card = $(`<article class="deal" draggable="true" data-id="${d.id}"><div>${esc(d.name)}</div><div class="acct">${esc(d.account_name||"")}</div><div class="money">${money(d.value)}</div></article>`);
      card.ondragstart = (e) => e.dataTransfer.setData("text/plain", d.id);
      card.onclick = () => openDeal(d.id);
      cards.append(card);
    });
    cards.ondragover = (e) => e.preventDefault();
    cards.ondrop = async (e) => {
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      await api("/api/deals/"+id+"/stage", {method:"POST", body:{stage}});
      await load(); render();
    };
    board.append(col);
  });
  return el;
}
async function inquiryView(el) {
  el.innerHTML = `<div class="card" style="padding:14px"><h3 style="margin-top:0">Quotes in inquiry</h3><p class="sub">Pulled from Flex. These are the leads to work.</p><div id="rows">Loading…</div></div>`;
  try {
    const res = await api("/api/lists/inquiry");
    const rows = res.records || [];
    el.querySelector("#rows").innerHTML = rows.length ? `<table><thead><tr><th>Quote</th><th>Number</th><th>Status</th><th>Start</th><th></th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.documentNumber||"")}</td><td><span class="pill inquiry">${esc(r.status||"Inquiry")}</span></td><td>${esc(r.date||"")}</td><td><button class="primary" data-add="${esc(r.id)}" data-name="${esc(r.name)}" data-num="${esc(r.documentNumber||"")}">Add to pipeline</button></td></tr>`).join("")}
    </tbody></table>` : `<div class="sub">No inquiry quotes came back. ${esc(res.detail||"")}</div>`;
    el.querySelectorAll("[data-add]").forEach(b => b.onclick = () => dealForm({ name: b.dataset.name, flex_id: b.dataset.add, flex_number: b.dataset.num, pipeline: "event" }));
  } catch (e) { el.querySelector("#rows").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function callsView(el) {
  el.innerHTML = `<div class="card" style="padding:14px"><h3 style="margin-top:0">Quiet clients</h3><p class="sub">Jobs whose end date is more than a year ago. Call these companies.</p><div id="rows">Loading…</div></div>`;
  try {
    const res = await api("/api/lists/quiet");
    const rows = res.records || [];
    el.querySelector("#rows").innerHTML = rows.length ? `<table><thead><tr><th>Client / job</th><th>Last end</th><th>Number</th><th></th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.date||"")}</td><td>${esc(r.documentNumber||"")}</td><td><button class="ghost" data-called="${esc(r.name)}">Log call</button></td></tr>`).join("")}
    </tbody></table>` : `<div class="sub">No quiet jobs came back. ${esc(res.detail||"")}</div>`;
    el.querySelectorAll("[data-called]").forEach(b => b.onclick = async () => {
      const note = prompt("Call note for " + b.dataset.called) || "Called";
      await api("/api/lists/call-log", { method:"POST", body:{ name: b.dataset.called, note } });
      b.textContent = "Logged";
    });
  } catch (e) { el.querySelector("#rows").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
function accounts() {
  const el = document.createElement("div");
  el.innerHTML = `<div class="card" style="padding:8px 12px"><table><thead><tr><th>Account</th><th>Type</th><th>Location</th><th>Flex id</th></tr></thead><tbody>
    ${(data.accounts||[]).map(a=>`<tr><td>${esc(a.name)}</td><td>${esc(a.type||"")}</td><td>${esc(a.city||"")} ${esc(a.state||"")}</td><td class="sub">${esc(a.flex_id||"")}</td></tr>`).join("")}
  </tbody></table></div>`;
  return el;
}
async function flexView(el) {
  el.innerHTML = `<div class="card" style="padding:14px"><h3 style="margin:0 0 8px">Search Flex</h3>
    <div class="seg">
      <button class="ghost on" data-k="all">All</button>
      <button class="ghost" data-k="contact">Contacts</button>
      <button class="ghost" data-k="job">Jobs</button>
      <button class="ghost" data-k="po">POs</button>
    </div>
    <div class="row"><input id="q" placeholder="Client, contact, job, or PO"><button class="primary" id="go">Search</button></div>
    <p class="sub">One search checks contacts, jobs, and purchase orders in Flex.</p>
    <div id="hits"></div></div>`;
  let kind = "all";
  el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => {
    kind = b.dataset.k;
    el.querySelectorAll("[data-k]").forEach(x => x.classList.toggle("on", x === b));
  });
  el.querySelector("#go").onclick = async () => {
    const hits = el.querySelector("#hits");
    hits.textContent = "Searching contacts, jobs, and POs…";
    try {
      const res = await api("/api/flex/search?q=" + encodeURIComponent(el.querySelector("#q").value) + "&kind=" + kind);
      const rows = res.records || [];
      hits.innerHTML = rows.length ? "" : `<div class="sub">No matches.</div><pre class="sub">${esc(JSON.stringify(res.attempts || [], null, 2))}</pre>`;
      rows.forEach(r => {
        const row = $(`<div class="flex-hit"><div><span class="pill">${esc(r.group || r.kind || "")}</span> <strong>${esc(r.name || "Record")}</strong><div class="sub">${esc(r.documentNumber || r.id || "")}</div></div><button class="ghost">Link to new deal</button></div>`);
        row.querySelector("button").onclick = () => dealForm({ name: r.name || "Flex job", flex_id: r.id, flex_number: r.documentNumber || "", value: r.budgetedRevenue || 0 });
        hits.append(row);
      });
    } catch (e) { hits.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
}
async function settingsView(el) {
  const s = await api("/api/settings");
  el.innerHTML = `<div class="card" style="padding:14px;max-width:640px"><h3 style="margin-top:0">Flex connection</h3>
    <label>Subdomain<input id="sub" value="${esc(s.flex_subdomain)}" placeholder="showboss"></label>
    <label>API key<input id="key" type="password" placeholder="${s.flex_key_set ? "Saved. Paste to replace." : "Paste X-Auth-Token key"}"></label>
    <button class="primary" id="save">Save</button> <button class="ghost" id="test">Test connection</button>
    <div id="msg" class="sub" style="margin-top:8px"></div>
    <h3>Users</h3>
    ${(s.users||[]).map(u=>`<div>${esc(u.name)} · ${esc(u.username)} · ${esc(u.role)}</div>`).join("")}
    ${me.role==="admin" ? `<form id="uf" class="row" style="margin-top:8px"><input name="username" placeholder="username" required><input name="name" placeholder="name" required><input name="password" placeholder="password" required><button class="ghost">Add user</button></form>` : ""}
    <h3>Your password</h3>
    <form id="pf" class="row"><input name="password" type="password" placeholder="New password" required><button class="ghost">Change</button></form>
    </div>`;
  el.querySelector("#save").onclick = async () => {
    await api("/api/settings", {method:"POST", body:{ flex_subdomain: el.querySelector("#sub").value, flex_api_key: el.querySelector("#key").value }});
    el.querySelector("#msg").textContent = "Saved on the server. The key is not sent back to the browser.";
  };
  el.querySelector("#test").onclick = async () => {
    el.querySelector("#msg").textContent = "Testing…";
    try { const r = await api("/api/flex/test"); el.querySelector("#msg").textContent = "Connected. " + JSON.stringify(r).slice(0, 400); }
    catch (e) { el.querySelector("#msg").textContent = e.message; }
  };
  el.querySelector("#uf")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("/api/users", {method:"POST", body:Object.fromEntries(new FormData(e.target))});
    settingsView(el);
  });
  el.querySelector("#pf").onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/password", {method:"POST", body:Object.fromEntries(new FormData(e.target))});
    el.querySelector("#msg").textContent = "Password updated.";
  };
}
function dealForm(pre={}) {
  const accounts = data.accounts || [];
  const box = $(`<div class="modal"><form class="box" id="f"><h3>Deal</h3>
    <label>Name<input name="name" required value="${esc(pre.name||"")}"></label>
    <div class="row"><label>Line<select name="pipeline"><option value="event">Event rental</option><option value="install">Permanent install</option></select></label>
    <label>Value<input name="value" type="number" value="${pre.value||0}"></label></div>
    <label>Account<select name="account_id">${accounts.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select></label>
    <div class="row"><label>Date<input name="event_date" type="date"></label><label>Flex number<input name="flex_number" value="${esc(pre.flex_number||"")}"></label></div>
    <input type="hidden" name="flex_id" value="${esc(pre.flex_id||"")}">
    <label>Notes<textarea name="notes"></textarea></label>
    <button class="primary" type="submit">Save</button> <button class="ghost" type="button" id="x">Cancel</button></form></div>`);
  box.querySelector("#x").onclick = () => box.remove();
  box.querySelector("#f").onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/deals", {method:"POST", body:Object.fromEntries(new FormData(e.target))});
    box.remove(); await load(); render();
  };
  document.body.append(box);
}
async function openDeal(id) {
  const d = await api("/api/deals/"+id);
  const box = $(`<div class="modal"><div class="box"><h3>${esc(d.name)}</h3>
    <div class="sub">${esc(d.account_name||"")} · ${money(d.value)} · ${esc(d.stage)} ${d.flex_number? "· Flex "+esc(d.flex_number):""}</div>
    <p>${esc(d.notes||"")}</p>
    <label>Note<textarea id="note"></textarea></label>
    <button class="primary" id="add">Log</button> <button class="ghost" id="x">Close</button>
    <div id="log" style="margin-top:10px"></div></div></div>`);
  box.querySelector("#x").onclick = () => box.remove();
  box.querySelector("#log").innerHTML = (d.activity||[]).map(a=>`<div class="sub">${esc(a.at)} · ${esc(a.user_name)}</div><div>${esc(a.text)}</div>`).join("");
  box.querySelector("#add").onclick = async () => {
    await api("/api/deals/"+id+"/note", {method:"POST", body:{text: box.querySelector("#note").value}});
    box.remove(); openDeal(id);
  };
  document.body.append(box);
}
boot();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE


@app.get("/api/me")
def me(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    return u


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (body.get("username", ""),)).fetchone()
    conn.close()
    if not row or not check_pw(body.get("password", ""), row["password"]):
        return JSONResponse({"error": "Invalid login"}, status_code=401)
    request.session["uid"] = row["id"]
    return {"id": row["id"], "username": row["username"], "name": row["name"], "role": row["role"]}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/board")
def board(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    deals = conn.execute(
        """SELECT d.*, a.name AS account_name FROM deals d
           LEFT JOIN accounts a ON a.id = d.account_id ORDER BY d.updated_at DESC"""
    ).fetchall()
    accounts = conn.execute("SELECT * FROM accounts ORDER BY name").fetchall()
    conn.close()
    return {"deals": [dict(r) for r in deals], "accounts": [dict(r) for r in accounts], "stages": STAGES}


@app.post("/api/deals")
async def create_deal(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    pipeline = body.get("pipeline") or "event"
    stage = STAGES[pipeline][0]
    conn = db()
    cur = conn.execute(
        """INSERT INTO deals (name, account_id, pipeline, stage, value, event_date, owner, notes, flex_id, flex_number, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            body.get("name"),
            body.get("account_id") or None,
            pipeline,
            stage,
            float(body.get("value") or 0),
            body.get("event_date"),
            u["name"],
            body.get("notes"),
            body.get("flex_id"),
            body.get("flex_number"),
            now(),
        ),
    )
    conn.execute(
        "INSERT INTO activity (deal_id, user_name, text, at) VALUES (?,?,?,?)",
        (cur.lastrowid, u["name"], "Deal created.", now()),
    )
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid}


@app.get("/api/deals/{deal_id}")
def get_deal(deal_id: int, request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    deal = conn.execute(
        "SELECT d.*, a.name AS account_name FROM deals d LEFT JOIN accounts a ON a.id=d.account_id WHERE d.id=?",
        (deal_id,),
    ).fetchone()
    activity = conn.execute("SELECT * FROM activity WHERE deal_id=? ORDER BY id DESC", (deal_id,)).fetchall()
    conn.close()
    if not deal:
        return JSONResponse({"error": "missing"}, status_code=404)
    out = dict(deal)
    out["activity"] = [dict(a) for a in activity]
    return out


@app.post("/api/deals/{deal_id}/stage")
async def set_stage(deal_id: int, request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute("UPDATE deals SET stage=?, updated_at=? WHERE id=?", (body.get("stage"), now(), deal_id))
    conn.execute(
        "INSERT INTO activity (deal_id, user_name, text, at) VALUES (?,?,?,?)",
        (deal_id, u["name"], f"Moved to {body.get('stage')}.", now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/deals/{deal_id}/note")
async def add_note(deal_id: int, request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    conn = db()
    conn.execute(
        "INSERT INTO activity (deal_id, user_name, text, at) VALUES (?,?,?,?)",
        (deal_id, u["name"], text, now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/settings")
def get_settings(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    users = conn.execute("SELECT id, username, name, role FROM users").fetchall()
    payload = {
        "flex_subdomain": setting(conn, "flex_subdomain"),
        "flex_key_set": bool(setting(conn, "flex_api_key")),
        "users": [dict(r) for r in users],
    }
    conn.close()
    return payload


@app.post("/api/settings")
async def save_settings(request: Request):
    u = user(request)
    if not u or u["role"] != "admin":
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = await request.json()
    conn = db()
    if "flex_subdomain" in body:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('flex_subdomain', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (body.get("flex_subdomain") or "",),
        )
    if body.get("flex_api_key"):
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('flex_api_key', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (body.get("flex_api_key"),),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/users")
async def add_user(request: Request):
    u = user(request)
    if not u or u["role"] != "admin":
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = await request.json()
    conn = db()
    try:
        conn.execute(
            "INSERT INTO users (username, name, password, role) VALUES (?,?,?,?)",
            (body["username"], body.get("name") or body["username"], hash_pw(body["password"]), "sales"),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": "username taken"}, status_code=400)
    conn.close()
    return {"ok": True}


@app.post("/api/password")
async def password(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute("UPDATE users SET password=? WHERE id=?", (hash_pw(body["password"]), u["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/lists/inquiry")
async def inquiry_list(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    status, body = await flex_get("/v1/elements", {"statusName": "Inquiry", "page": 1, "size": 50, "sort": "plannedStartDate,desc"})
    records = flex_records(body) if status < 400 else []
    detail = ""
    if status >= 400 and isinstance(body, dict):
        detail = str(body.get("exceptionMessage") or body.get("error") or body)[:200]
    out = []
    for row in records:
        if not isinstance(row, dict):
            continue
        out.append({
            "id": row.get("id"),
            "name": row.get("name") or row.get("displayName") or "Quote",
            "documentNumber": row.get("documentNumber") or "",
            "status": (row.get("status") or {}).get("name") if isinstance(row.get("status"), dict) else row.get("statusName") or "Inquiry",
            "date": (row.get("plannedStartDate") or "")[:10],
        })
    return {"records": out, "detail": detail, "status": status}


@app.get("/api/lists/quiet")
async def quiet_list(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    status, body = await flex_get("/v1/elements", {"plannedEndBefore": cutoff, "page": 1, "size": 80, "sort": "plannedEndDate,desc"})
    records = flex_records(body) if status < 400 else []
    detail = ""
    if status >= 400 and isinstance(body, dict):
        detail = str(body.get("exceptionMessage") or body.get("error") or body)[:200]
    seen = set()
    out = []
    for row in records:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("displayName") or "Job"
        if name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "documentNumber": row.get("documentNumber") or "",
            "date": (row.get("plannedEndDate") or row.get("plannedStartDate") or "")[:10],
        })
    return {"records": out, "detail": detail, "status": status}


@app.post("/api/lists/call-log")
async def call_log(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute(
        "INSERT INTO call_log (name, note, user_name, at) VALUES (?,?,?,?)",
        (body.get("name"), body.get("note"), u["name"], now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/flex/test")
async def flex_test(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    status, body = await flex_get("/business-location/identity")
    if status >= 400:
        return JSONResponse({"error": f"Flex returned {status}", "body": body}, status_code=502)
    return {"ok": True, "locations": body}


def flex_records(body):
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    for key in ("content", "results", "records", "items", "elements", "contacts"):
        if isinstance(body.get(key), list):
            return body[key]
    return []


def flex_label(record, kind):
    if not isinstance(record, dict):
        return {"name": str(record), "kind": kind, "group": kind}
    definition = record.get("definitionName") or record.get("elementDefinitionName") or ""
    if isinstance(record.get("definition"), dict):
        definition = definition or record["definition"].get("name") or ""
    name = (
        record.get("name")
        or record.get("displayName")
        or record.get("preferredDisplayString")
        or record.get("company")
        or record.get("companyName")
        or " ".join(x for x in [record.get("firstName"), record.get("lastName")] if x)
        or record.get("documentNumber")
        or "Record"
    )
    text = f"{definition} {name}".lower()
    group = kind
    if kind == "element":
        group = "po" if any(word in text for word in ("purchase", "po", "subrental")) else "job"
    return {
        "id": record.get("id"),
        "name": name,
        "kind": definition or kind,
        "group": group,
        "documentNumber": record.get("documentNumber") or record.get("number") or "",
        "budgetedRevenue": record.get("budgetedRevenue") or record.get("resolvedBudgetedRevenue") or 0,
    }


@app.get("/api/flex/search")
async def flex_search(request: Request, q: str = "", kind: str = "all"):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if not q.strip():
        return JSONResponse({"error": "Enter a search term"}, status_code=400)
    calls = []
    if kind in ("all", "contact"):
        for prop in ("company", "companyName", "firstName", "lastName"):
            calls.append(("contact", "/contact-manager/grid-node", {
                "filter": json.dumps([{"property": prop, "value": q}]),
                "page": 0,
                "size": 20,
            }))
        calls.append(("contact", "/contact/search", {"searchText": q, "page": 0, "size": 20}))
    if kind in ("all", "job", "po"):
        calls.append(("element", "/v1/elements", {"q": q, "page": 1, "size": 20}))
        calls.append(("element", "/element/search", {"searchText": q, "page": 0, "size": 20}))
    records = []
    attempts = []
    seen = set()
    for group, path, params in calls:
        status, body = await flex_get(path, params)
        found = flex_records(body) if status < 400 else []
        detail = ""
        if status >= 400:
            if isinstance(body, dict):
                detail = str(body.get("exceptionMessage") or body.get("error") or body)[:180]
            else:
                detail = str(body)[:180]
        attempts.append({"kind": group, "path": path, "status": status, "count": len(found), "detail": detail})
        for row in found:
            item = flex_label(row, group)
            if kind == "po" and item["group"] != "po":
                continue
            if kind == "job" and item["group"] == "po":
                continue
            key = (item.get("id"), item.get("name"), item.get("group"))
            if key in seen:
                continue
            seen.add(key)
            records.append(item)
    return {"records": records[:40], "attempts": attempts}

