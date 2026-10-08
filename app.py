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
        CREATE TABLE IF NOT EXISTS sales_leads (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          company TEXT,
          phone TEXT,
          email TEXT,
          source TEXT,
          flex_id TEXT,
          stage TEXT NOT NULL,
          owner TEXT,
          next_step TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS contact_notes (
          id INTEGER PRIMARY KEY,
          contact_id TEXT,
          contact_name TEXT,
          kind TEXT,
          note TEXT,
          user_name TEXT,
          at TEXT
        );
        CREATE TABLE IF NOT EXISTS quote_cards (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          phone TEXT,
          email TEXT,
          event_month TEXT,
          notes TEXT,
          owner TEXT,
          stage TEXT NOT NULL,
          priority INTEGER DEFAULT 0
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
    if not conn.execute("SELECT 1 FROM quote_cards").fetchone():
        cards = [
            ("VLI", "", "", "", "Truss corners and bases", "Justin", "Needs quote", 1),
            ("Louder Exp - Molly Martin", "214.578.9655", "molly@louderexp.com", "Nov 2026", "Truss set up for xmas", "Justin", "Needs quote", 2),
            ("Firebaugh High School", "559.659.1415", "", "", "30 panel wall and curriculum", "Justin", "Needs quote", 3),
            ("Light the Night - Las Vegas", "516.650.3896", "Lisa.Brunenbraber@bloodcancerunited.org", "November 2026", "Light the Night Vegas", "Justin", "Quoted", 0),
            ("AZ Video", "480.861.2001", "info@az-video.com", "October 2026", "Paulden AZ - 16x12 stage, Audio, 16x10 video wall", "Justin", "Quoted", 0),
            ("DDP Worldwide", "480.440.3264", "dpetty@ddpworldwide.com", "December 2026", "Rawhide SL100, Audio, Lighting, JBL 6 per side and video", "Justin", "Quoted", 0),
            ("Jim Woodling", "", "", "", "", "Justin", "Quoted", 0),
            ("Supreme Cheer and Tumble", "480.462.6821", "info@supremecheertumble.com", "Nov 2026", "Sound, DJ Set Up, Lighting, PnD", "Justin", "Confirmed", 0),
            ("EKIN", "", "", "", "Finish quote and send", "Justin", "Cancelled", 0),
        ]
        conn.executemany(
            "INSERT INTO quote_cards (name, phone, email, event_month, notes, owner, stage, priority) VALUES (?,?,?,?,?,?,?,?)",
            cards,
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
.brand img { height:28px; width:auto; max-width:150px; object-fit:contain; display:block; }
.crm-label { color:var(--blue); font-size:22px; font-weight:750; letter-spacing:.08em; margin:6px 0 0; }
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
  shell.innerHTML = `<aside class="side"><div class="brand"><img src="https://showbossav.com/wp-content/uploads/2025/11/SB-Refresh-Logos_Blue-Shade-Black-Fly-scaled.png" alt="ShowBoss AV"><div class="crm-label">CRM</div></div>
    <nav>
      <button data-v="dash" class="${view==='dash'?'on':''}">Dashboard</button>
      <button data-v="pipe" class="${view==='pipe'?'on':''}">Pipeline</button>
      <button data-v="sales" class="${view==='sales'?'on':''}">Sales</button>
      <button data-v="flow" class="${view==='flow'?'on':''}">Quote Flow</button>
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
  const titles = {dash:"Dashboard", sales:"Sales", pipe:"Pipeline", flow:"Quote Flow", accounts:"Accounts", flex:"Flex Rental Solutions", settings:"Settings"};
  shell.querySelector("#ttl").textContent = titles[view];
  if (view === "dash") dashView(viewEl);
  if (view === "sales") salesView(viewEl);
  if (view === "pipe") pipeHub(viewEl);
  if (view === "flow") quoteFlow(viewEl);
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
async function dashView(el) {
  const paint = (d) => {
    el.innerHTML = `<div class="card" style="padding:22px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px">
        <div><div class="k">${esc(d.month||"")}</div><div style="font-size:28px;font-weight:700">${esc(d.date||"")}</div></div>
        <div style="text-align:right"><div class="k">Days left in month</div><div class="v" style="font-size:42px">${d.days_left ?? "—"}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 160px;gap:18px;margin-top:18px">
        <div>
          <div class="k">Confirmed</div>
          <div class="v" style="font-size:40px">${money(d.confirmed_amount)}</div>
        </div>
        <div><div class="k">Jobs</div><div class="v" style="font-size:40px">${d.confirmed_count ?? 0}</div></div>
        <div>
          <div class="k">Inquiry</div>
          <div class="v" style="font-size:40px">${money(d.inquiry_amount)}</div>
        </div>
        <div><div class="k">Jobs</div><div class="v" style="font-size:40px">${d.inquiry_count ?? 0}</div></div>
      </div>
      <p class="sub" style="margin-top:14px">Live from Flex.</p>
    </div>`;
  };
  paint({ date:"Loading…", days_left:"—" });
  const load = async () => { try { paint(await api("/api/dashboard")); } catch (e) { paint({ date:"Flex", detail:e.message, confirmed_amount:0, inquiry_amount:0, confirmed_count:0, inquiry_count:0, days_left:"—" }); } };
  await load();
  setInterval(load, 30000);
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
const SALES = ["New", "Attempting", "Connected", "Qualified", "Quote sent", "Won", "Lost"];
async function salesView(el) {
  el.innerHTML = `<div class="card" style="padding:14px;margin-bottom:12px">
    <div class="seg"><button class="ghost on" data-m="board">Board</button><button class="ghost" data-m="import">Import list</button></div>
    <div class="row"><input id="q" placeholder="Search Flex or type a new lead"><button class="primary" id="find">Add from Flex</button><button class="ghost" id="manual">Add lead</button></div>
    <div id="pick"></div>
    <div id="board"></div>
    <div id="import" style="display:none"><p class="sub">Paste a list. One lead per line: Name, Company, Phone, Email</p><textarea id="csv" rows="8" placeholder="Molly Martin, Louder Exp, 214.578.9655, molly@louderexp.com"></textarea><button class="primary" id="doImport">Import</button></div>
  </div>`;
  const board = el.querySelector("#board");
  const draw = async () => {
    const res = await api("/api/sales");
    const leads = res.leads || [];
    board.innerHTML = `<div class="board">${SALES.map(stage => {
      const mine = leads.filter(l => l.stage === stage);
      return `<div class="col"><div class="head"><strong>${stage}</strong><span class="sub">${mine.length}</span></div><div class="cards" data-stage="${stage}">${mine.map(l => `<article class="deal" draggable="true" data-id="${l.id}"><strong>${esc(l.name)}</strong><div class="sub">${esc(l.company||l.source||"")}</div><div>${l.phone?`<a href="tel:${esc(l.phone)}">${esc(l.phone)}</a>`:""}</div><div>${l.email?`<a href="mailto:${esc(l.email)}">${esc(l.email)}</a>`:""}</div><button class="ghost" data-open="${l.id}">Open</button></article>`).join("")}</div></div>`;
    }).join("")}</div>`;
    board.querySelectorAll(".deal").forEach(card => {
      card.ondragstart = (e) => e.dataTransfer.setData("text/plain", card.dataset.id);
    });
    board.querySelectorAll(".cards").forEach(box => {
      box.ondragover = (e) => e.preventDefault();
      box.ondrop = async (e) => { e.preventDefault(); await api("/api/sales/"+e.dataTransfer.getData("text/plain")+"/stage", {method:"POST", body:{stage: box.dataset.stage}}); draw(); };
    });
    board.querySelectorAll("[data-open]").forEach(b => b.onclick = (e) => { e.stopPropagation(); openLead(b.dataset.open, draw); });
  };
  el.querySelectorAll("[data-m]").forEach(b => b.onclick = () => {
    el.querySelectorAll("[data-m]").forEach(x => x.classList.toggle("on", x===b));
    el.querySelector("#import").style.display = b.dataset.m === "import" ? "block" : "none";
    board.style.display = b.dataset.m === "import" ? "none" : "block";
  });
  el.querySelector("#find").onclick = async () => {
    const q = el.querySelector("#q").value;
    const res = await api("/api/flex/search?q=" + encodeURIComponent(q) + "&kind=contact");
    const pick = el.querySelector("#pick");
    pick.innerHTML = (res.records||[]).map(r => `<div class="flex-hit"><div><strong>${esc(r.name)}</strong><div class="sub">${esc(r.id||"")}</div></div><button class="primary" data-flex="${esc(r.id)}" data-name="${esc(r.name)}">Add</button></div>`).join("") || `<div class="sub">No Flex contact with that name.</div>`;
    pick.querySelectorAll("[data-flex]").forEach(b => b.onclick = async () => {
      await api("/api/sales", {method:"POST", body:{ name: b.dataset.name, flex_id: b.dataset.flex, source: "Flex" }});
      pick.innerHTML = "";
      draw();
    });
  };
  el.querySelector("#manual").onclick = async () => {
    const name = el.querySelector("#q").value || prompt("Lead name");
    if (!name) return;
    await api("/api/sales", {method:"POST", body:{ name, source: "Manual" }});
    draw();
  };
  el.querySelector("#doImport").onclick = async () => {
    await api("/api/sales/import", {method:"POST", body:{ text: el.querySelector("#csv").value }});
    el.querySelector("#csv").value = "";
    draw();
  };
  draw();
}
async function openLead(id, refresh) {
  const lead = await api("/api/sales/" + id);
  const box = $(`<div class="modal"><div class="box" style="width:min(680px,94vw)"><h3>${esc(lead.name)}</h3>
    <div class="sub">${esc(lead.company||"")} · ${esc(lead.source||"")}</div>
    <div class="kv"><span>Phone</span><div>${lead.phone?`<a href="tel:${esc(lead.phone)}">${esc(lead.phone)}</a>`:"—"}</div><span>Email</span><div>${lead.email?`<a href="mailto:${esc(lead.email)}">${esc(lead.email)}</a>`:"—"}</div><span>Stage</span><div>${esc(lead.stage)}</div></div>
    <label>Next step<input id="next" value="${esc(lead.next_step||"")}"></label>
    <h3>Attempts</h3><div id="log"></div>
    <div class="row"><select id="kind"><option>Called</option><option>LM</option><option>Txt</option><option>Email</option></select><input id="note" placeholder="What happened"></div>
    <button class="primary" id="save">Save attempt</button> <button class="ghost" id="x">Close</button></div></div>`);
  const drawLog = (notes) => { box.querySelector("#log").innerHTML = (notes||[]).map(n => `<div class="flex-hit"><div><span class="pill">${esc(n.kind)}</span> ${esc(n.note||"")}<div class="sub">${esc(n.at||"")} · ${esc(n.user_name||"")}</div></div></div>`).join("") || `<div class="sub">No attempts yet.</div>`; };
  drawLog(lead.notes);
  box.querySelector("#x").onclick = () => box.remove();
  box.querySelector("#save").onclick = async () => {
    await api("/api/sales/"+id+"/note", {method:"POST", body:{ kind: box.querySelector("#kind").value, note: box.querySelector("#note").value, next_step: box.querySelector("#next").value }});
    const again = await api("/api/sales/" + id);
    drawLog(again.notes);
    box.querySelector("#note").value = "";
    refresh();
  };
  document.body.append(box);
}
function pipeHub(el) {
  el.innerHTML = `<div class="seg"><button class="ghost on" data-t="inquiry">Inquiry Status</button><button class="ghost" data-t="quiet">Quiet</button></div><div id="pane"></div>`;
  const pane = el.querySelector("#pane");
  const show = (t) => { el.querySelectorAll("[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t===t)); pane.innerHTML=""; if (t==="inquiry") inquiryView(pane); else callsView(pane); };
  el.querySelectorAll("[data-t]").forEach(b => b.onclick = () => show(b.dataset.t));
  show("inquiry");
}
const FLOW = ["Needs quote", "Quoted", "Confirmed", "Cancelled"];
async function quoteFlow(el) {
  el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><div class="sub">Needs quote, then quoted, then confirmed or cancelled.</div><button class="primary" id="addCard">+ New client card</button></div><div class="board" id="flow"></div>`;
  const board = el.querySelector("#flow");
  let cards = [];
  try { cards = (await api("/api/quotes")).cards || []; } catch (e) { board.innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  FLOW.forEach(stage => {
    const mine = cards.filter(c => c.stage === stage);
    const col = document.createElement("div");
    col.className = "col";
    col.innerHTML = `<div class="head"><strong>${stage}</strong><span class="sub">${mine.length}</span></div><div class="cards" data-stage="${stage}"></div>`;
    const box = col.querySelector(".cards");
    mine.forEach(c => {
      const card = $(`<article class="deal" draggable="true"><div class="sub">Assigned to ${esc(c.owner||"")}</div><strong>${esc(c.name)}</strong><div>${esc(c.phone||"")}</div><div><a href="mailto:${esc(c.email||"")}">${esc(c.email||"")}</a></div><div class="sub">${esc(c.event_month||"")}</div><div>${esc(c.notes||"")}</div><button class="ghost" data-del="${c.id}">Delete</button></article>`);
      card.ondragstart = (e) => e.dataTransfer.setData("text/plain", String(c.id));
      box.append(card);
    });
    box.ondragover = (e) => e.preventDefault();
    box.ondrop = async (e) => { e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); if (!id) return; await api("/api/quotes/"+id+"/stage", {method:"POST", body:{stage: box.dataset.stage}}); quoteFlow(el); };
    col.ondragover = (e) => e.preventDefault();
    col.ondrop = box.ondrop;
    board.append(col);
  });
  board.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { await api("/api/quotes/"+b.dataset.del, {method:"DELETE"}); quoteFlow(el); });
  el.querySelector("#addCard").onclick = () => {
    const box = $(`<div class="modal"><form class="box" id="f"><h3>New client card</h3>
      <label>Name<input name="name" required></label>
      <div class="row"><label>Phone<input name="phone"></label><label>Email<input name="email"></label></div>
      <div class="row"><label>Month<input name="event_month" placeholder="Nov 2026"></label><label>Stage<select name="stage">${FLOW.map(s=>`<option>${s}</option>`).join("")}</select></label></div>
      <label>Notes<textarea name="notes"></textarea></label>
      <button class="primary">Save</button> <button type="button" class="ghost" id="x">Cancel</button></form></div>`);
    box.querySelector("#x").onclick = () => box.remove();
    box.querySelector("#f").onsubmit = async (e) => { e.preventDefault(); await api("/api/quotes", {method:"POST", body:Object.fromEntries(new FormData(e.target))}); box.remove(); quoteFlow(el); };
    document.body.append(box);
  };
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
      <button class="ghost on" data-k="contact">Contact</button>
      <button class="ghost" data-k="show">Show / Quote #</button>
      <button class="ghost" data-k="spo">SPO's</button>
      <button class="ghost" data-k="rpo">RPO's</button>
    </div>
    <div class="row"><input id="q" placeholder="Company, person, quote number, SPO, or RPO"><button class="primary" id="go">Search</button></div>
    <div id="hits"></div></div>`;
  let kind = "contact";
  el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => {
    kind = b.dataset.k;
    el.querySelectorAll("[data-k]").forEach(x => x.classList.toggle("on", x === b));
    if (el.querySelector("#q").value) el.querySelector("#go").click();
  });
  el.querySelector("#go").onclick = async () => {
    const hits = el.querySelector("#hits");
    hits.textContent = "Searching…";
    try {
      const res = await api("/api/flex/search?q=" + encodeURIComponent(el.querySelector("#q").value) + "&kind=" + kind);
      const rows = res.records || [];
      hits.innerHTML = rows.length ? "" : `<div class="sub">No matches in this tab.</div>`;
      rows.forEach(r => {
        const row = $(`<div class="flex-hit"><div><span class="pill">${esc(r.group||"")}</span> <strong>${esc(r.name||"Record")}</strong><div class="sub">${esc(r.documentNumber||r.id||"")}</div></div><button class="ghost">${kind==="contact"?"Open contact":"Link to new deal"}</button></div>`);
        row.querySelector("button").onclick = () => kind==="contact" ? openContact(r.id, r.name) : dealForm({ name: r.name, flex_id: r.id, flex_number: r.documentNumber||"" });
        if (kind==="contact") row.querySelector("strong").onclick = () => openContact(r.id, r.name);
        hits.append(row);
      });
    } catch (e) { hits.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
}
async function openContact(id, name) {
  const box = $(`<div class="modal"><div class="box" style="width:min(640px,94vw)"><h3>${esc(name||"Contact")}</h3><div id="body">Loading…</div><h3>Notes</h3><div id="log"></div>
    <div class="row"><select id="kind"><option>Called</option><option>LM</option><option>Txt</option></select><input id="note" placeholder="What happened"></div>
    <button class="primary" id="save">Save note</button> <button class="ghost" id="x">Close</button></div></div>`);
  box.querySelector("#x").onclick = () => box.remove();
  document.body.append(box);
  const draw = (c) => {
    const phone = c.phone || "";
    const email = c.email || "";
    box.querySelector("#body").innerHTML = `<div class="kv"><span>Company</span><div>${esc(c.company||"—")}</div>
      <span>Phone</span><div>${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a> <button class="ghost" id="callnote">Note this call</button>`:"—"}</div>
      <span>Email</span><div>${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:"—"}</div></div>`;
    const notes = c.notes || [];
    box.querySelector("#log").innerHTML = notes.length ? notes.map(n => `<div class="flex-hit"><div><span class="pill">${esc(n.kind)}</span> ${esc(n.note||"")}<div class="sub">${esc(n.at||"")} · ${esc(n.user_name||"")}</div></div></div>`).join("") : `<div class="sub">No attempts yet.</div>`;
    box.querySelector("#callnote")?.addEventListener("click", () => { box.querySelector("#kind").value = "Called"; box.querySelector("#note").focus(); });
  };
  const load = async () => { draw(await api("/api/flex/contact/" + id)); };
  box.querySelector("#save").onclick = async () => {
    await api("/api/contacts/notes", { method:"POST", body:{ contact_id:id, contact_name:name, kind:box.querySelector("#kind").value, note:box.querySelector("#note").value } });
    box.querySelector("#note").value = "";
    await load();
  };
  try { await load(); } catch (e) { box.querySelector("#body").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
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


def money_of(row):
    if isinstance(row, (int, float)) and not isinstance(row, bool):
        return float(row)
    if isinstance(row, str):
        cleaned = row.replace(",", "").replace("$", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0
    if isinstance(row, list):
        return sum(money_of(item) for item in row)
    if not isinstance(row, dict):
        return 0
    total = 0
    code = str(row.get("code") or row.get("name") or "").lower()
    if code in ("budgetedrevenue", "resolvedbudgetedrevenue", "totalprice", "estimatedprice", "budgetedcost"):
        total += money_of(row.get("value"))
    for key, value in row.items():
        if key.lower() in ("budgetedrevenue", "resolvedbudgetedrevenue", "totalprice", "estimatedprice", "total", "amount", "grandtotal"):
            total += money_of(value)
        elif isinstance(value, (dict, list)):
            total += money_of(value)
    return total


@app.get("/api/dashboard")
async def dashboard(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    from datetime import date
    import calendar
    today = date.today()
    last = calendar.monthrange(today.year, today.month)[1]
    start = today.replace(day=1).isoformat()
    end = today.replace(day=last).isoformat()
    days_left = last - today.day
    money_codes = ("budgetedRevenue", "resolvedBudgetedRevenue", "totalPrice", "estimatedPrice", "budgetedCost")

    async def pull(status_name):
        base = {"statusName": status_name, "plannedStartAfter": start, "plannedStartBefore": end, "page": 1, "size": 100}
        status, body = await flex_get("/v1/elements", base)
        rows = flex_records(body) if status < 400 else []
        detail = f"{status_name} {status}/{len(rows)}"
        amount = 0
        if rows:
            sample = rows[0].get("id")
            for code in ("budgetedRevenue", "resolvedBudgetedRevenue", "totalPrice", "estimatedPrice"):
                h_status, h_body = await flex_get(f"/element/{sample}/header-data", {"codeList": code})
                if h_status < 400 and money_of(h_body):
                    amount = 0
                    for row in rows:
                        one_status, one_body = await flex_get(f"/element/{row.get('id')}/header-data", {"codeList": code})
                        if one_status < 400:
                            amount += money_of(one_body)
                    break
        return rows, amount

    confirmed, c_amount = await pull("Confirmed")
    inquiry, i_amount = await pull("Inquiry")
    return {
        "date": f"{today.strftime('%B')} {today.day}, {today.year}",
        "month": today.strftime("%B %Y"),
        "days_left": days_left,
        "confirmed_count": len(confirmed),
        "confirmed_amount": c_amount,
        "inquiry_count": len(inquiry),
        "inquiry_amount": i_amount,
    }


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


@app.get("/api/sales")
def sales_list(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    rows = conn.execute("SELECT * FROM sales_leads ORDER BY updated_at DESC").fetchall()
    conn.close()
    return {"leads": [dict(r) for r in rows]}


@app.get("/api/sales/{lead_id}")
def sales_one(lead_id: int, request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    row = conn.execute("SELECT * FROM sales_leads WHERE id=?", (lead_id,)).fetchone()
    notes = conn.execute("SELECT kind, note, user_name, at FROM contact_notes WHERE contact_id=? ORDER BY id DESC", (f"lead:{lead_id}",)).fetchall()
    conn.close()
    if not row:
        return JSONResponse({"error": "missing"}, status_code=404)
    out = dict(row)
    out["notes"] = [dict(n) for n in notes]
    return out


@app.post("/api/sales")
async def sales_add(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    phone, email, company = body.get("phone") or "", body.get("email") or "", body.get("company") or ""
    if body.get("flex_id") and not phone:
        status, phones = await flex_get("/phone-number/contact-phone-numbers", {"contactId": body["flex_id"]})
        status, emails = await flex_get("/internet-address/contact-internet-addresses", {"contactId": body["flex_id"]})
        phone = first_text(phones, ("phoneNumber", "number", "value", "displayString"))
        email = first_text(emails, ("internetAddress", "email", "address", "value", "displayString"))
    conn = db()
    conn.execute(
        "INSERT INTO sales_leads (name, company, phone, email, source, flex_id, stage, owner, next_step, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (body.get("name") or "Lead", company, phone, email, body.get("source") or "Manual", body.get("flex_id"), "New", u["name"], "", now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/sales/import")
async def sales_import(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    for line in (body.get("text") or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        company = parts[1] if len(parts) > 1 else ""
        phone = parts[2] if len(parts) > 2 else ""
        email = parts[3] if len(parts) > 3 else ""
        conn.execute(
            "INSERT INTO sales_leads (name, company, phone, email, source, stage, owner, next_step, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, company, phone, email, "Import", "New", u["name"], "", now()),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/sales/{lead_id}/stage")
async def sales_stage(lead_id: int, request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute("UPDATE sales_leads SET stage=?, updated_at=? WHERE id=?", (body.get("stage"), now(), lead_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/sales/{lead_id}/note")
async def sales_note(lead_id: int, request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    row = conn.execute("SELECT name FROM sales_leads WHERE id=?", (lead_id,)).fetchone()
    conn.execute(
        "INSERT INTO contact_notes (contact_id, contact_name, kind, note, user_name, at) VALUES (?,?,?,?,?,?)",
        (f"lead:{lead_id}", row["name"] if row else "", body.get("kind") or "Called", body.get("note") or "", u["name"], now()),
    )
    if body.get("next_step") is not None:
        conn.execute("UPDATE sales_leads SET next_step=?, updated_at=? WHERE id=?", (body.get("next_step"), now(), lead_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/quotes")
def quotes(request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    rows = conn.execute("SELECT * FROM quote_cards ORDER BY priority, id").fetchall()
    conn.close()
    return {"cards": [dict(r) for r in rows]}


@app.post("/api/quotes")
async def add_quote(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute(
        "INSERT INTO quote_cards (name, phone, email, event_month, notes, owner, stage, priority) VALUES (?,?,?,?,?,?,?,?)",
        (body.get("name"), body.get("phone"), body.get("email"), body.get("event_month"), body.get("notes"), u["name"], body.get("stage") or "Needs quote", 0),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/quotes/{card_id}/stage")
async def quote_stage(card_id: int, request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute("UPDATE quote_cards SET stage=? WHERE id=?", (body.get("stage"), card_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/quotes/{card_id}")
def delete_quote(card_id: int, request: Request):
    if not user(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    conn = db()
    conn.execute("DELETE FROM quote_cards WHERE id=?", (card_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def first_text(rows, keys):
    if isinstance(rows, dict):
        rows = rows.get("content") or rows.get("results") or [rows]
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            if row.get(key):
                return str(row[key])
    return ""


@app.get("/api/flex/contact/{contact_id}")
async def flex_contact(contact_id: str, request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    status, body = await flex_get(f"/contact/{contact_id}/key-info")
    if status >= 400:
        status, body = await flex_get(f"/contact/{contact_id}")
    company = ""
    if isinstance(body, dict):
        company = body.get("company") or body.get("companyName") or body.get("organizationName") or body.get("name") or ""
    phone_status, phones = await flex_get("/phone-number/contact-phone-numbers", {"contactId": contact_id})
    email_status, emails = await flex_get("/internet-address/contact-internet-addresses", {"contactId": contact_id})
    phone = first_text(phones, ("phoneNumber", "number", "value", "displayString"))
    email = first_text(emails, ("internetAddress", "email", "address", "value", "displayString"))
    conn = db()
    notes = [dict(r) for r in conn.execute(
        "SELECT kind, note, user_name, at FROM contact_notes WHERE contact_id=? ORDER BY id DESC",
        (contact_id,),
    ).fetchall()]
    conn.close()
    return {"phone": phone, "email": email, "company": company, "notes": notes, "phone_status": phone_status, "email_status": email_status}


@app.post("/api/contacts/notes")
async def add_contact_note(request: Request):
    u = user(request)
    if not u:
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    conn = db()
    conn.execute(
        "INSERT INTO contact_notes (contact_id, contact_name, kind, note, user_name, at) VALUES (?,?,?,?,?,?)",
        (body.get("contact_id"), body.get("contact_name"), body.get("kind") or "Called", body.get("note") or "", u["name"], now()),
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
    if kind in ("all", "show", "job"):
        calls.append(("element", "/v1/elements", {"q": q, "page": 1, "size": 20}))
        calls.append(("element", "/element/search", {"searchText": q, "page": 0, "size": 20}))
    if kind in ("all", "spo", "rpo", "po"):
        calls.append(("element", "/v1/elements", {"q": q, "page": 1, "size": 20}))
        calls.append(("po", "/element/search", {"searchText": q, "page": 0, "size": 20}))
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
            if kind == "spo" and not str(item.get("documentNumber") or "").upper().startswith("SPO") and "spo" not in str(item.get("kind") or "").lower():
                continue
            if kind == "rpo" and not str(item.get("documentNumber") or "").upper().startswith("RPO") and "rpo" not in str(item.get("kind") or "").lower():
                continue
            if kind == "show" and item.get("group") == "po":
                continue
            if kind == "contact" and item.get("group") not in ("contact", "contact"):
                if group != "contact":
                    continue
            key = (item.get("id"), item.get("name"), item.get("group"))
            if key in seen:
                continue
            seen.add(key)
            records.append(item)
    return {"records": records[:40], "attempts": attempts}
