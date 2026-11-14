#!/usr/bin/env python3
"""Build sanitized public projection from internal unified memory + PR metadata."""
from __future__ import annotations
import argparse, json, re, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

def clean(s):
    if s is None:
        return None
    s = str(s)
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "[session]", s, flags=re.I)
    s = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[local path]", s)
    s = re.sub(r"/(?:c|d|f)/[^\s\"']+", "[local path]", s, flags=re.I)
    s = re.sub(r"%TEMP%[^\s\"']*", "[temp dir]", s, flags=re.I)
    s = re.sub(r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9]+", "[redacted]", s)
    return s

def load_lessons(memory: Path):
    c = sqlite3.connect(memory)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("SELECT * FROM lessons ORDER BY id")]
    out = []
    for r in rows:
        out.append({k: clean(r.get(k)) for k in ["id","title","repo","problem","lesson","conditions","counterexamples","status","confidence","source_type","source_ref","tags"]})
    return out

def load_mrs(prs: Path):
    data = json.loads(prs.read_text(encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])
    out = []
    for it in items:
        url = it.get("html_url") or ""
        m = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
        repo = m.group(1) if m else "unknown"
        pr = it.get("pull_request") or {}
        merged = bool(pr.get("merged_at"))
        out.append({
            "repo": repo,
            "number": it.get("number"),
            "title": clean(it.get("title")),
            "state": "merged" if merged else it.get("state"),
            "url": url,
            "updated_at": it.get("updated_at"),
            "merged_at": pr.get("merged_at"),
        })
    return out

def shanghai_day(iso):
    if not iso:
        return None
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8)))
    return dt.date().isoformat()

def attach_mrs(days, mrs):
    by_day = {}
    for m in mrs:
        if shanghai_day(m.get("updated_at")) is None:
            continue
        if datetime.fromisoformat(str(m.get("updated_at")).replace("Z", "+00:00")) < datetime.fromisoformat("2026-11-09T16:12:04+00:00"):
            continue
        by_day.setdefault(shanghai_day(m.get("updated_at")), []).append(m)
    out = []
    for d in days:
        item = dict(d)
        item["recordUpdatedAt"] = NOW
        item["mrs"] = by_day.get(d.get("date"), [])
        for key in ("date", "window", "summary"):
            item[key] = clean(item.get(key))
        cleaned_items = []
        for row in item.get("items") or []:
            cleaned_items.append({k: clean(row.get(k)) for k in ("repo", "work", "status", "evidence")})
        item["items"] = cleaned_items
        out.append(item)
    return out

def write_sqlite(path: Path, lessons, mrs, days):
    if path.exists():
        path.unlink()
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE lessons (id TEXT PRIMARY KEY, title TEXT, repo TEXT, problem TEXT, lesson TEXT, conditions TEXT, counterexamples TEXT, status TEXT, confidence TEXT, source_type TEXT, source_ref TEXT, tags TEXT);
    CREATE TABLE mrs (repo TEXT, number INTEGER, title TEXT, state TEXT, url TEXT, updated_at TEXT, merged_at TEXT);
    CREATE TABLE days (date TEXT, window TEXT, summary TEXT, items TEXT, record_updated_at TEXT, mrs TEXT);
    """)
    for r in lessons:
        c.execute("INSERT INTO lessons VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tuple(r.get(k) for k in ["id","title","repo","problem","lesson","conditions","counterexamples","status","confidence","source_type","source_ref","tags"]))
    for r in mrs:
        c.execute("INSERT INTO mrs VALUES (?,?,?,?,?,?,?)", tuple(r.get(k) for k in ["repo","number","title","state","url","updated_at","merged_at"]))
    for d in days:
        c.execute("INSERT INTO days VALUES (?,?,?,?,?,?)", (d.get("date"), d.get("window"), d.get("summary"), json.dumps(d.get("items", []), ensure_ascii=False), d.get("recordUpdatedAt"), json.dumps(d.get("mrs", []), ensure_ascii=False)))
    c.commit()
    c.close()

HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Work Log · Public Memory Projection</title>
<style>
:root{color-scheme:dark;--bg:#171b18;--card:#202622;--ink:#e6ece7;--muted:#acb7ae;--line:#3b463e;--accent:#a5d2b5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}
main{width:min(1000px,calc(100% - 32px));margin:auto;padding:28px 0 60px}h1{font-size:clamp(26px,5vw,40px);line-height:1.2;color:var(--accent)}h2{margin-top:28px}.meta{color:var(--muted);font-size:14px}.note{border:1px solid var(--line);padding:12px;border-radius:8px;background:var(--card)}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.tabs button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:8px 12px;border-radius:8px;cursor:pointer}.tabs button.active{border-color:var(--accent);color:var(--accent)}
input[type=search]{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);margin:10px 0}
.card{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:14px;margin:12px 0;overflow-wrap:anywhere}.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin-right:6px}.badge.merged{color:var(--accent);border-color:var(--accent)}.badge.open{color:#e3c18b;border-color:#e3c18b}
a{color:var(--accent)}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}ul{padding-left:20px}.downloads a{display:inline-block;margin-right:12px}
@media(max-width:600px){table,tbody,tr,td{display:block;width:100%}thead{display:none}tr{border:1px solid var(--line);margin:8px 0;padding:6px 0}td{border:0;padding:6px 10px}td:before{content:attr(data-label);display:block;font-size:12px;color:var(--muted)}}
</style></head><body><main>
<p class="meta">yhyu13 / agent-work-log · public projection · 页面更新时间 __UPDATED__</p>
<h1>Agent Work Log</h1>
<p>每日工作、PR/MR 进展、公开经验数据库。内部统一记忆库是正本；这里只发布脱敏投影。</p>
<p class="note">候选经验不等于已批准规则。公开数据库可下载，但不会自动回注到任何 repo。</p>
<div class="tabs"><button data-tab="days" class="active">每日工作</button><button data-tab="mrs">PR / MR</button><button data-tab="lessons">经验库</button><button data-tab="db">数据库</button></div>
<input id="q" type="search" placeholder="搜索 repo / 标题 / 经验">
<section id="days"></section><section id="mrs" hidden></section><section id="lessons" hidden></section><section id="db" hidden></section>
<script id="data" type="application/json">__DATA__</script>
<script>
let data=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function render(){const q=($("#q").value||"").toLowerCase();
 $("#days").innerHTML=(data.coverageNote?`<p class="note">${esc(data.coverageNote)}</p>`:"")+data.days.map(d=>{const mrs=(d.mrs||[]).map(m=>`<li><span class="badge ${m.state==="merged"?"merged":"open"}">${esc(m.state)}</span> <a href="${esc(m.url)}">${esc(m.repo)} #${m.number}</a> ${esc(m.title)}<br><span class="meta">MR 更新时间 ${esc(m.updated_at)}</span></li>`).join("")||"<li>这一天没有落在任务窗口内的 MR 更新。</li>";return `<div class="card"><h2>${esc(d.date)}</h2><p class="meta">本条记录更新时间 ${esc(d.recordUpdatedAt||data.updatedAt)} · 覆盖 ${esc(d.window)}</p><h3>总结</h3><p>${esc(d.summary)}</p><h3>当日工作</h3><ul>${(d.items||[]).map(i=>`<li><strong>${esc(i.repo)}</strong>：${esc(i.work)}<br><span class="meta">${esc(i.status)} · ${esc(i.evidence)}</span></li>`).join("")}</ul><h3>当日 MR 进展 · ${(d.mrs||[]).length} 条</h3><ul>${mrs}</ul></div>`}).join("");
 $("#mrs").innerHTML=data.mrs.filter(m=>!q||(m.repo+m.title+m.state).toLowerCase().includes(q)).map(m=>`<div class="card"><span class="badge ${m.state==="merged"?"merged":"open"}">${esc(m.state)}</span><span class="badge">${esc(m.repo)} #${m.number}</span><a href="${esc(m.url)}">${esc(m.title)}</a><p class="meta">updated ${esc(m.updated_at)}</p></div>`).join("")||"<p>无匹配</p>";
 $("#lessons").innerHTML=data.lessons.filter(l=>!q||(l.id+l.title+l.repo+l.lesson+l.tags).toLowerCase().includes(q)).map(l=>`<div class="card"><span class="badge">${esc(l.status)}</span><span class="badge">${esc(l.repo||"cross-repo")}</span><strong>${esc(l.id)} · ${esc(l.title)}</strong><p>${esc(l.lesson)}</p><p class="meta">问题：${esc(l.problem||"")}</p><p class="meta">条件：${esc(l.conditions||"")} · 反例：${esc(l.counterexamples||"")}</p><p class="meta">来源：${esc(l.source_type||"")} ${esc(l.source_ref||"")}</p></div>`).join("")||"<p>无匹配</p>";
 $("#db").innerHTML=`<div class="card downloads"><h2>公开数据库</h2><p>JSON 用于页面；SQLite/SQL 用于离线查询。</p><a href="data/latest.json">latest.json</a><a href="data/memory-public.sqlite">memory-public.sqlite</a><a href="data/memory-public.sql">memory-public.sql</a><p class="meta">lessons: ${data.lessons.length} · PR/MR: ${data.mrs.length} · days: ${data.days.length}</p></div>`;}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tabs button").forEach(x=>x.classList.remove("active"));b.classList.add("active");["days","mrs","lessons","db"].forEach(id=>$("#"+id).hidden=id!==b.dataset.tab);render();});
$("#q").oninput=render;render();
fetch("data/latest.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(j=>{if(j&&j.updatedAt>data.updatedAt){data=j;render();}}).catch(()=>{});
</script></main></body></html>"""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--memory", required=True)
    p.add_argument("--prs", required=True)
    p.add_argument("--days", required=True)
    a = p.parse_args()
    lessons = load_lessons(Path(a.memory))
    mrs = load_mrs(Path(a.prs))
    days = attach_mrs(json.loads(Path(a.days).read_text(encoding="utf-8")), mrs)
    latest = {"schemaVersion": 1, "updatedAt": NOW, "repo": "yhyu13/agent-work-log", "pagesUrl": "https://yhyu13.github.io/agent-work-log/", "coverageNote": "每日记录从任务建立日 2026-11-10（上海时间）起。当日 MR 是 yhyu13 名下公开 PR 里、最近一次更新落在这一天的条目，不是本任务单独产生，也不会在每一天重复。早于任务建立的条目只在总表。候选经验不是已批准规则。", "days": days, "mrs": mrs, "lessons": lessons}
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_sqlite(data_dir / "memory-public.sqlite", lessons, mrs, days)
    c = sqlite3.connect(data_dir / "memory-public.sqlite")
    (data_dir / "memory-public.sql").write_text("\n".join(c.iterdump()), encoding="utf-8")
    c.close()
    payload = json.dumps(latest, ensure_ascii=False).replace("</", "<\\/")
    html = HTML.replace("__DATA__", payload).replace("__UPDATED__", NOW)
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print(json.dumps({"lessons": len(lessons), "mrs": len(mrs), "days": len(days), "index": str(ROOT / "index.html")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
