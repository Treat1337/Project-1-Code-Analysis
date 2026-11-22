import json
import os

import requests
import streamlit as st
import streamlit.components.v1 as components

from app.services.problem_catalog import Problem, list_problem_ids, load_problem


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")


@st.cache_data(show_spinner=False)
def cached_problem_ids() -> list[str]:
    return list_problem_ids()


@st.cache_data(show_spinner=False)
def cached_problem(problem_id: str) -> Problem:
    return load_problem(problem_id)


st.set_page_config(
    page_title="AI Code Analysis",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    [data-testid="stHeader"], [data-testid="stToolbar"] { display:none; }
    [data-testid="stSidebar"] { display:none; }
    section[data-testid="stMain"] { padding:0; }
    .block-container { max-width:none; padding:0; }
    iframe { border:0; }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    problem_ids = cached_problem_ids()
except (OSError, ValueError) as exc:
    st.error(f"Không thể tải danh sách bài: {exc}")
    st.stop()

selected_id = st.query_params.get("problem")
if not selected_id:
    selected_id = st.session_state.get("selected_problem")
if selected_id not in problem_ids:
    selected_id = problem_ids[0]
    st.session_state["selected_problem"] = selected_id
else:
    st.session_state["selected_problem"] = selected_id

try:
    problem = cached_problem(selected_id)
except (OSError, ValueError) as exc:
    st.error(f"Không thể tải đề {selected_id}: {exc}")
    st.stop()

payload = {
    "apiUrl": API_URL,
    "problemId": selected_id,
    "problemTitle": problem.title,
    "problemHtml": problem.html,
    "sampleCases": problem.sample_test_cases,
    "problemIds": problem_ids,
    "problemCatalog": [
        {
            "id": "1",
            "title": "Two Sum",
            "difficulty": "Easy",
            "statement": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
            "examples": "<p><strong>Input:</strong> nums = [2,7,11,15], target = 9<br><strong>Output:</strong> [0,1]</p>",
            "constraints": "2 <= nums.length <= 10^4",
            "cases": [{"stdin": "[2,7,11,15]\n9", "expected_stdout": "[0,1]"}, {"stdin": "[3,2,4]\n6", "expected_stdout": "[1,2]"}, {"stdin": "[3,3]\n6", "expected_stdout": "[0,1]"}],
        },
        {
            "id": "2",
            "title": "Add Two Numbers",
            "difficulty": "Medium",
            "statement": "Add two numbers represented by linked lists and return the sum as a linked list.",
            "examples": "<p><strong>Input:</strong> l1 = [2,4,3], l2 = [5,6,4]<br><strong>Output:</strong> [7,0,8]</p>",
            "constraints": "Each linked list contains 1 to 100 nodes.",
            "cases": [{"stdin": "[2,4,3]\n[5,6,4]", "expected_stdout": "[7,0,8]"}],
        },
        {
            "id": "3",
            "title": "Longest Substring Without Repeating Characters",
            "difficulty": "Medium",
            "statement": "Given a string s, find the length of the longest substring without repeating characters.",
            "examples": "<p><strong>Input:</strong> s = \"abcabcbb\"<br><strong>Output:</strong> 3</p>",
            "constraints": "0 <= s.length <= 5 * 10^4",
            "cases": [{"stdin": "abcabcbb", "expected_stdout": "3"}, {"stdin": "bbbbb", "expected_stdout": "1"}, {"stdin": "pwwkew", "expected_stdout": "3"}],
        },
        {
            "id": "20",
            "title": "Valid Parentheses",
            "difficulty": "Easy",
            "statement": "Determine whether a string containing brackets is valid.",
            "examples": "<p><strong>Input:</strong> s = \"()[]{}\"<br><strong>Output:</strong> true</p>",
            "constraints": "1 <= s.length <= 10^4",
            "cases": [{"stdin": "()[]{}", "expected_stdout": "true"}, {"stdin": "(]", "expected_stdout": "false"}],
        },
        {
            "id": "53",
            "title": "Maximum Subarray",
            "difficulty": "Medium",
            "statement": "Find the contiguous subarray with the largest sum and return its sum.",
            "examples": "<p><strong>Input:</strong> nums = [-2,1,-3,4,-1,2,1,-5,4]<br><strong>Output:</strong> 6</p>",
            "constraints": "1 <= nums.length <= 10^5",
            "cases": [{"stdin": "-2 1 -3 4 -1 2 1 -5 4", "expected_stdout": "6"}],
        },
    ],
}

try:
    list_response = requests.get(f"{API_URL}/api/problems", timeout=8)
    list_response.raise_for_status()
    available = list_response.json().get("problems", [])
except (requests.RequestException, ValueError):
    available = []

dynamic_catalog: list[dict[str, object]] = []
for item in available[:50]:
    try:
        detail_response = requests.get(
            f"{API_URL}/api/problem/{item['problem_id']}",
            timeout=8,
        )
        detail_response.raise_for_status()
        detail = detail_response.json()
    except (requests.RequestException, ValueError):
        continue
    dynamic_catalog.append({
        "id": item["problem_id"].lstrip("p"),
        "title": detail["title"],
        "difficulty": "Easy",
        "statement": detail["plain_text"][:1200],
        "examples": detail["html"],
        "constraints": "",
        "cases": detail["test_cases"],
        "html": detail["html"],
        "accepted_solution": detail["accepted_solution"],
    })
if dynamic_catalog:
    payload["problemCatalog"] = dynamic_catalog

html = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
:root{
  --bg:#0a0a0a;--panel:#1a1a1a;--panel2:#202020;--header:#282828;
  --border:#303030;--text:#f5f5f5;--muted:#a1a1a1;--green:#2cbb5d;
  --blue:#409eff;--yellow:#ffa116;--red:#ef4743;
}
*{box-sizing:border-box}
html,body{width:100%;height:100%;margin:0;overflow:hidden;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,system-ui,sans-serif}
button,input,select,textarea{font:inherit}
button{cursor:pointer}
.app{height:100vh;display:flex;flex-direction:column;background:var(--bg)}
.topbar{height:48px;flex:none;display:flex;align-items:center;gap:10px;padding:0 10px;border-bottom:1px solid var(--border);background:#161616}
.icon-btn,.nav-btn,.action-btn,.panel-btn{border:1px solid transparent;background:transparent;color:var(--muted);border-radius:6px;height:32px;padding:0 9px;display:inline-flex;align-items:center;justify-content:center;gap:7px}
.icon-btn:hover,.nav-btn:hover,.panel-btn:hover{background:#303030;color:#fff}
.nav-btn{font-weight:600;color:#f0f0f0}
.top-title{min-width:220px;display:flex;align-items:center;gap:8px;font-weight:700}
.spacer{flex:1}
.timer{min-width:52px;text-align:center;color:var(--muted);font-variant-numeric:tabular-nums}
.action-btn{height:34px;padding:0 13px;font-weight:700}
.run{background:#262626;border-color:#3b3b3b;color:#fff}
.run:hover{background:#303030}
.submit{background:var(--green);border-color:var(--green);color:#07130a}
.submit:hover{filter:brightness(1.08)}
.workspace{flex:1;min-height:0;display:flex;position:relative}
.pane{min-width:0;min-height:0;background:var(--panel);overflow:hidden}
.problem-pane{width:44%;display:flex;flex-direction:column}
.right-pane{width:56%;display:flex;flex-direction:column}
.vertical-resizer,.horizontal-resizer{flex:none;background:var(--bg);position:relative;z-index:20}
.vertical-resizer{width:5px;cursor:col-resize;border-left:1px solid var(--border);border-right:1px solid var(--border)}
.horizontal-resizer{height:5px;cursor:row-resize;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.vertical-resizer:hover,.vertical-resizer.active,.horizontal-resizer:hover,.horizontal-resizer.active{background:#3e7bca}
.pane-header{height:44px;flex:none;display:flex;align-items:center;border-bottom:1px solid var(--border);background:var(--header);padding:0 8px 0 12px}
.pane-header .title{font-weight:700;display:flex;align-items:center;gap8px}
.tabs{display:flex;align-items:center;height:100%;gap:2px;overflow-x:auto}
.tab{height:100%;padding:0 10px;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--muted);white-space:nowrap}
.tab.active{color:var(--text);border-bottom-color:var(--blue)}
.window-controls{margin-left:auto;display:flex;gap:2px}
.panel-btn{width:31px;padding:0;font-size:14px}
.pane-body{flex:1;min-height:0;overflow:auto}
.problem-body{padding:18px 20px 32px;line-height:1.62}
.problem-body h1{font-size:22px;margin:0 0 10px}
.problem-body h2{font-size:17px;margin:20px 0 8px}
.problem-body pre{background:#262626;border:1px solid #333;border-radius:7px;padding:12px;overflow:auto}
.problem-body code{color:#e6edf3}
.difficulty{display:inline-flex;height:24px;align-items:center;border-radius:999px;padding:0 9px;background:rgba(44,187,93,.12);color:var(--green);font-size:12px;font-weight:700;margin-right:8px}
.problem-meta{display:flex;align-items:center;color:var(--muted);font-size:13px;margin-bottom:12px}
.editor-pane{flex:1;min-height:90px;display:flex;flex-direction:column}
.editor-toolbar{height:44px;flex:none;display:flex;align-items:center;gap:8px;padding:0 8px;border-bottom:1px solid var(--border);background:#222}
select{height:30px;border:1px solid #3a3a3a;border-radius:6px;background:#2a2a2a;color:#ddd;padding:0 8px}
.editor-wrap{flex:1;min-height:0;display:flex;background:#1e1e1e}
.line-numbers{width:52px;flex:none;padding:12px 9px 12px 0;text-align:right;color:#858585;background:#1e1e1e;border-right:1px solid #252525;font:14px/22px Consolas,monospace;overflow:hidden;user-select:none}
.code-editor-layer{position:relative;flex:1;min-width:0;overflow:hidden;background:#1e1e1e}
#codeHighlight{position:absolute;inset:0;margin:0;padding:12px 14px;border:0;overflow:hidden;pointer-events:none;color:#d4d4d4;font:14px/22px Consolas,monospace;tab-size:4;white-space:pre}
#codeEditor{position:absolute;inset:0;width:100%;height:100%;resize:none;border:0;outline:none;background:transparent;color:transparent;-webkit-text-fill-color:transparent;caret-color:#d4d4d4;padding:12px 14px;font:14px/22px Consolas,monospace;tab-size:4;white-space:pre;overflow:auto}
#codeEditor::selection{background:rgba(38,79,120,.65);-webkit-text-fill-color:transparent}
.hl-keyword{color:#569cd6}.hl-type{color:#4ec9b0}.hl-string{color:#ce9178}.hl-comment{color:#6a9955}.hl-number{color:#b5cea8}.hl-preprocessor{color:#c586c0}
.cpp-language{height:30px;display:flex;align-items:center;border:1px solid #3a3a3a;border-radius:6px;background:#2a2a2a;color:#ddd;padding:0 9px;font-weight:600}
.console-pane{height:32%;min-height:90px;display:flex;flex-direction:column}
.console-header{height:44px;flex:none;display:flex;align-items:center;border-bottom:1px solid var(--border);background:#222;padding:0 8px}
.console-body{flex:1;min-height:0;overflow:auto;padding:12px 14px}
.case-pills{display:flex;gap:7px;margin-bottom:12px}
.case-pill{height:30px;border:1px solid #383838;border-radius:6px;background:#242424;color:var(--muted);padding:0 10px}
.case-pill.active{border-color:#4d98ff;color:#fff;background:#2b394a}
.case-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.field-label{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}
.case-input{width:100%;min-height:74px;resize:vertical;border:1px solid #353535;border-radius:7px;background:#202020;color:#f0f0f0;padding:10px;font:13px/20px Consolas,monospace}
.test-result{border-left:3px solid var(--green);background:#202820;border-radius:7px;padding:12px;margin-bottom:10px}
.test-result.error{border-left-color:var(--red);background:#2a2020}
.test-result pre{margin:8px 0 0;white-space:pre-wrap}
.drawer-overlay{position:absolute;inset:48px 0 0 0;z-index:100;background:rgba(0,0,0,.5);display:none}
.drawer-overlay.open{display:block}
.drawer{width:310px;height:100%;background:#1c1c1c;border-right:1px solid var(--border);box-shadow:12px 0 30px rgba(0,0,0,.35);display:flex;flex-direction:column}
.drawer-search{margin:10px;border:1px solid #3a3a3a;border-radius:7px;background:#252525;color:#fff;height:36px;padding:0 10px}
.drawer-list{flex:1;overflow:auto;padding:4px}
.drawer-item{width:100%;border:0;border-radius:6px;background:transparent;color:#ddd;text-align:left;padding:9px 10px}
.drawer-item:hover,.drawer-item.active{background:#303030}
.drawer-item span{display:block;color:#888;font-size:11px;margin-bottom:2px}
.collapsed-v{width:44px!important}
.collapsed-v .pane-body,.collapsed-v .tabs,.collapsed-v .pane-header .title{display:none!important}
.collapsed-v .pane-header{width:44px;padding:0;justify-content:center}
.collapsed-v .window-controls{margin:0;flex-direction:column}
.collapsed-v .pane-header .tabs{display:none}
.collapsed-h{height:44px!important;min-height:44px!important;flex:none!important}
.collapsed-h .console-body,.collapsed-h .pane-body{display:none}
.collapsed-h.editor-pane .editor-toolbar,.collapsed-h.editor-pane .editor-wrap{display:none}
.hidden-pane{display:none!important}
.maximize{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;z-index:80!important}
.loading{display:inline-block;width:14px;height:14px;border:2px solid #777;border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite}
.ai-badge{display:inline-flex;align-items:center;justify-content:center;min-width:16px;height:16px;border-radius:99px;background:var(--red);color:#fff;font-size:10px;margin-left:5px}
.settings-row{display:flex;gap:8px;align-items:center}
.settings-row input{height:30px;width:180px;border:1px solid #3a3a3a;border-radius:6px;background:#2a2a2a;color:#ddd;padding:0 8px}
.ai-card{border:1px solid #343434;border-radius:8px;padding:12px;background:#202020;line-height:1.55}
.ai-card.error-tip{border-left:3px solid var(--red)}
.skel{height:12px;border-radius:5px;background:linear-gradient(90deg,#292929,#3a3a3a,#292929);background-size:200% 100%;animation:skel 1.2s linear infinite;margin:8px 0}
@keyframes skel{to{background-position:-200% 0}}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:900px){
  .problem-pane{width:40%}.right-pane{width:60%}.top-title{min-width:150px}.case-grid{grid-template-columns:1fr}
}
@media(max-width:650px){
  .workspace{flex-direction:column}.problem-pane{width:100%!important;height:42%!important}.right-pane{width:100%!important;height:58%!important}.vertical-resizer{width:100%;height:5px;cursor:row-resize;border:0}.top-title{min-width:0}.top-title strong{display:none}.timer{display:none}
}
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <button class="nav-btn" id="drawerBtn">☰ &nbsp; Problem List</button>
    <button class="icon-btn" id="prevProblem" title="Previous">‹</button>
    <button class="icon-btn" id="nextProblem" title="Next">›</button>
    <button class="icon-btn" id="randomProblem" title="Random problem">🔀 Random</button>
    <div class="top-title"><strong id="topNumber"></strong><span id="topTitle"></span></div>
    <div class="spacer"></div>
    <span class="timer" id="timer">00:00</span>
    <button class="action-btn run" id="runBtn">▶ Run</button>
    <button class="action-btn submit" id="submitBtn">✓ Submit</button>
  </header>
  <main class="workspace" id="workspace">
    <section class="pane problem-pane" id="problemPane">
      <div class="pane-header">
        <div class="tabs" id="problemTabs">
          <button class="tab active" data-tab="description">Description</button>
          <button class="tab" data-tab="solutions">Solutions</button>
        </div>
        <div class="window-controls">
          <button class="panel-btn" data-action="minimize" data-pane="problemPane" title="Collapse">—</button>
          <button class="panel-btn" data-action="maximize" data-pane="problemPane" title="Maximize">⛶</button>
        </div>
      </div>
      <div class="pane-body problem-body" id="problemBody"></div>
    </section>
    <div class="vertical-resizer" id="vResizer"></div>
    <section class="pane right-pane" id="rightPane">
      <section class="editor-pane" id="editorPane">
        <div class="pane-header">
          <div class="title">‹ / › &nbsp; Code</div>
          <div class="window-controls">
            <button class="panel-btn" data-action="minimize" data-pane="editorPane" title="Collapse">—</button>
            <button class="panel-btn" data-action="maximize" data-pane="editorPane" title="Maximize">⛶</button>
          </div>
        </div>
        <div class="editor-toolbar">
          <select id="language">
            <option>C++</option>
            <option>Python3</option>
          </select>
          <button class="icon-btn" id="resetCode">Reset</button>
          <button class="icon-btn" id="formatCode">Format</button>
          <div class="settings-row">
            <input id="ollamaModel" value="qwen2.5-coder:3b" aria-label="Ollama model">
          </div>
          <div class="spacer"></div>
        </div>
        <div class="editor-wrap">
          <div class="line-numbers" id="lineNumbers">1</div>
          <div class="code-editor-layer">
            <pre id="codeHighlight"></pre>
            <textarea id="codeEditor" spellcheck="false" wrap="off"></textarea>
          </div>
        </div>
      </section>
      <div class="horizontal-resizer" id="hResizer"></div>
      <section class="console-pane" id="consolePane">
        <div class="console-header">
          <div class="tabs">
            <button class="tab active" data-console="testcase">Testcase</button>
            <button class="tab" data-console="result">Test Result</button>
            <button class="tab" data-console="ai">AI Feedback<span id="aiBadge"></span></button>
          </div>
          <div class="window-controls">
            <button class="panel-btn" data-action="minimize" data-pane="consolePane" title="Collapse">—</button>
            <button class="panel-btn" data-action="maximize" data-pane="consolePane" title="Maximize">⛶</button>
          </div>
        </div>
        <div class="console-body" id="consoleBody"></div>
      </section>
    </section>
    <div class="drawer-overlay" id="drawerOverlay">
      <aside class="drawer">
        <input class="drawer-search" id="drawerSearch" placeholder="Search problem...">
        <div class="drawer-list" id="drawerList"></div>
      </aside>
    </div>
  </main>
</div>
<script>
const data = __PAYLOAD__;
const catalog=data.problemCatalog;
const state = {activeProblem:0,activeCase:0,cases:[],results:null,aiResponse:"",aiError:"",simulateWrong:false};
const problemPane=document.getElementById("problemPane"),rightPane=document.getElementById("rightPane");
const editorPane=document.getElementById("editorPane"),consolePane=document.getElementById("consolePane");
const codeEditor=document.getElementById("codeEditor"),lineNumbers=document.getElementById("lineNumbers");
const codeHighlight=document.getElementById("codeHighlight");

const starters={
  "C++":(p)=>`#include <bits/stdc++.h>\n\nint main()\n{\n    // Solve: ${p.title}\n    \n}`,
  "Python3":(p)=>`# ${p.title}\n\nclass Solution:\n    def solve(self):\n        # Write your solution here\n        pass\n`,
};

function problemDescription(p){
  if(p.html)return p.html;
  const difficultyClass=p.difficulty==="Easy"?"green":"yellow";
  return `<h1>${p.id}. ${p.title}</h1><div class="problem-meta"><span class="difficulty" style="color:var(--${difficultyClass})">${p.difficulty}</span><span>Topics</span></div><p>${p.statement}</p><h2>Examples</h2>${p.examples}<h2>Constraints</h2><pre>${escapeHtml(p.constraints)}</pre>`;
}

function loadProblem(index){
  if(index<0)index=catalog.length-1;
  if(index>=catalog.length)index=0;
  state.activeProblem=index;
  state.activeCase=0;
  state.results=null;
  state.aiResponse="";
  state.aiError="";
  document.getElementById("aiBadge").innerHTML="";
  const p=catalog[index];
  document.getElementById("topTitle").textContent=p.title;
  document.getElementById("topNumber").textContent=p.id+".";
  document.getElementById("problemBody").innerHTML=problemDescription(p);
  state.cases=p.cases.map((c,i)=>({...c,name:"Case "+(i+1)}));
  const lang=document.getElementById("language").value||"C++";
  codeEditor.value=starters[lang](p);
  updateLines();
  renderCases();
  document.querySelectorAll("[data-tab]").forEach(t=>t.classList.toggle("active",t.dataset.tab==="description"));
}

let initialId=null;
try{initialId=new URL(window.top.location.href).searchParams.get("problem")}catch(e){}
const initialIndex=catalog.findIndex(p=>p.id===initialId);
loadProblem(initialIndex>=0?initialIndex:0);

function escapeHtml(v){return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function highlightCpp(code){
  const keywords=new Set(["int","main","return","if","else","for","while","do","switch","case","break","continue","class","struct","namespace","using","const","constexpr","static","void","bool","char","long","double","float","unsigned","signed","auto","template","typename","public","private","protected","true","false","std","vector","string","cin","cout","endl"]);
  const types=new Set(["int","char","void","bool","double","float","long","unsigned","signed","auto","string","vector"]);
  const pattern=/(\/\/.*$|#\s*[^\n]+|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/gm;
  let result="",last=0,match;
  while((match=pattern.exec(code))){
    result+=escapeHtml(code.slice(last,match.index));
    const token=match[0];
    let className="";
    if(token.startsWith("//"))className="hl-comment";
    else if(token.startsWith("#"))className="hl-preprocessor";
    else if(token.startsWith('"')||token.startsWith("'"))className="hl-string";
    else if(/^\d/.test(token))className="hl-number";
    else if(types.has(token))className="hl-type";
    else if(keywords.has(token))className="hl-keyword";
    result+=className?`<span class="${className}">${escapeHtml(token)}</span>`:escapeHtml(token);
    last=pattern.lastIndex;
  }
  return result+escapeHtml(code.slice(last))+"\n";
}
function updateLines(){
  const count=codeEditor.value.split("\n").length;
  lineNumbers.textContent=Array.from({length:count},(_,i)=>i+1).join("\n");
  lineNumbers.scrollTop=codeEditor.scrollTop;
  codeHighlight.innerHTML=highlightCpp(codeEditor.value);
  codeHighlight.scrollTop=codeEditor.scrollTop;
  codeHighlight.scrollLeft=codeEditor.scrollLeft;
}
codeEditor.addEventListener("input",updateLines);
codeEditor.addEventListener("scroll",()=>{
  lineNumbers.scrollTop=codeEditor.scrollTop;
  codeHighlight.scrollTop=codeEditor.scrollTop;
  codeHighlight.scrollLeft=codeEditor.scrollLeft;
});
codeEditor.addEventListener("keydown",(e)=>{
  if(e.key==="Tab"){e.preventDefault();const s=codeEditor.selectionStart,e2=codeEditor.selectionEnd;codeEditor.setRangeText("    ",s,e2,"end");updateLines();}
});
updateLines();

function elapsedTimer(){
  let seconds=0;
  setInterval(()=>{seconds++;document.getElementById("timer").textContent=String(Math.floor(seconds/60)).padStart(2,"0")+":"+String(seconds%60).padStart(2,"0")},1000);
}
elapsedTimer();

document.getElementById("prevProblem").onclick=()=>loadProblem(state.activeProblem-1);
document.getElementById("nextProblem").onclick=()=>loadProblem(state.activeProblem+1);
document.getElementById("randomProblem").onclick=()=>{
  let next=state.activeProblem;
  while(next===state.activeProblem){
    next=Math.floor(Math.random()*catalog.length);
  }
  loadProblem(next);
};

function renderCases(){
  const box=document.getElementById("consoleBody");
  let html=`<div class="case-pills">${state.cases.map((c,i)=>`<button class="case-pill ${i===state.activeCase?"active":""}" data-case="${i}">${c.name}</button>`).join("")}<button class="case-pill" id="addCase">+</button></div><div class="case-grid">`;
  const c=state.cases[state.activeCase];
  html+=`<div><label class="field-label">Input</label><textarea class="case-input" id="caseInput">${escapeHtml(c.stdin||"")}</textarea></div><div><label class="field-label">Expected output</label><textarea class="case-input" id="caseExpected">${escapeHtml(c.expected_stdout||"")}</textarea></div></div>`;
  box.innerHTML=html;
  box.querySelectorAll("[data-case]").forEach(btn=>btn.onclick=()=>{saveCurrentCase();state.activeCase=Number(btn.dataset.case);renderCases()});
  const input=document.getElementById("caseInput"),expected=document.getElementById("caseExpected");
  input.oninput=()=>state.cases[state.activeCase].stdin=input.value;
  expected.oninput=()=>state.cases[state.activeCase].expected_stdout=expected.value;
  document.getElementById("addCase").onclick=()=>{saveCurrentCase();state.cases.push({name:"Case "+(state.cases.length+1),stdin:"",expected_stdout:""});state.activeCase=state.cases.length-1;renderCases()};
}
function escapeHtml(v){return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function saveCurrentCase(){
  const input=document.getElementById("caseInput"),expected=document.getElementById("caseExpected");
  if(input&&state.cases[state.activeCase]){state.cases[state.activeCase].stdin=input.value;state.cases[state.activeCase].expected_stdout=expected.value}
}
renderCases();

document.querySelectorAll("[data-console]").forEach(tab=>tab.onclick=()=>{
  document.querySelectorAll("[data-console]").forEach(t=>t.classList.remove("active"));tab.classList.add("active");
  if(tab.dataset.console==="testcase")renderCases();
  else if(tab.dataset.console==="result")renderResults();
  else renderAI();
});

function renderResults(){
  const box=document.getElementById("consoleBody");
  if(!state.results){
    box.innerHTML=`<div class="test-result"><strong>Test Result</strong><p>Run or Submit code to see execution results.</p></div>`;
    return;
  }
  const r=state.results;
  const success=r.verdict==="ACCEPTED"||r.verdict==="MOCK_ACCEPTED";
  const tone=success?"test-result":"test-result error";
  let passed=r.tests? r.tests.filter(t=>t.status==="PASSED").length:0,total=r.tests?r.tests.length:0;
  const verdictLabel=r.verdict==="MOCK_ACCEPTED"?"Accepted (Demo)":(r.verdict||"No result");
  let html=`<div class="${tone}"><strong>${verdictLabel}</strong><div>${passed}/${total} test cases passed · ${r.duration_ms||"—"} ms</div>`;
  if(r.stdout)html+=`<pre>${escapeHtml(r.stdout)}</pre>`;
  if(r.diagnostic)html+=`<pre>${escapeHtml(r.diagnostic)}</pre>`;
  html+="</div>";
  if(r.tests)html+=r.tests.map((t,i)=>`<div class="${t.status==="PASSED"?"test-result":"test-result error"}"><strong>Test ${i+1}: ${t.status}</strong><pre>Input:\n${escapeHtml(t.stdin||"")}\nExpected:\n${escapeHtml(t.expected_stdout||"")}\nActual:\n${escapeHtml(t.stdout||"")}</pre></div>`).join("");
  box.innerHTML=html;
}

function markdownLite(text){
  let html=escapeHtml(text);
  html=html.replace(/^### (.*)$/gm,"<h3>$1</h3>").replace(/^## (.*)$/gm,"<h2>$1</h2>");
  html=html.replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>").replace(/`([^`]+)`/g,"<code>$1</code>");
  html=html.replace(/\n/g,"<br>");
  return html;
}

function renderAI(){
  const box=document.getElementById("consoleBody");
  if(state.aiResponse){
    box.innerHTML=`<div class="ai-card">${markdownLite(state.aiResponse)}</div>`;
  }else if(state.aiError){
    box.innerHTML=`<div class="ai-card error-tip"><strong>AI feedback unavailable</strong><p>${escapeHtml(state.aiError)}</p><p>Start Ollama with CORS enabled:</p><pre>OLLAMA_ORIGINS="*" ollama serve</pre><button class="icon-btn" id="retryAI">Retry</button></div>`;
    document.getElementById("retryAI").onclick=explainWithAI;
  }else{
    box.innerHTML=`<div class="ai-card"><strong>AI Feedback</strong><p>Run a failing testcase to request an explanation.</p><button class="icon-btn" id="explainAI">Explain Error with AI</button></div>`;
    document.getElementById("explainAI").onclick=explainWithAI;
  }
}

async function explainWithAI(){
  const box=document.getElementById("consoleBody");
  state.aiResponse="";
  state.aiError="";
  box.innerHTML=`<div class="ai-card"><strong>Generating explanation...</strong><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>`;
  const p=catalog[state.activeProblem];
  const failed=state.results?.tests?.find(t=>t.status==="WRONG_ANSWER")||state.cases[state.activeCase]||{};
  const verdict=state.results?.verdict||"Wrong Answer";
  try{
    const response=await fetch(data.apiUrl+"/api/ai-feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      problem_description:p.html||p.statement||p.title,
      code:codeEditor.value,
      verdict,
      failing_input:failed.stdin||"",
      actual_output:failed.stdout||"",
      expected_output:failed.expected_stdout||"",
      model:document.getElementById("ollamaModel").value.trim()||"qwen2.5-coder:3b-instruct-q8_0"
    })});
    const payload=await response.json();
    if(payload.available)state.aiResponse=payload.response||"No explanation returned.";
    else state.aiError=`${payload.error||"AI feedback unavailable"}${payload.detail?"\n"+payload.detail:""}`;
  }catch(error){
    state.aiError=`Could not reach the FastAPI AI feedback proxy. ${error.message}`;
  }
  renderAI();
  document.querySelectorAll("[data-console]").forEach(t=>t.classList.toggle("active",t.dataset.console==="ai"));
}

async function runCode(){
  saveCurrentCase();
  const btn=document.getElementById("runBtn");btn.innerHTML='<span class="loading"></span>';
  const c=state.cases[state.activeCase];
  try{
    const r=await fetch(data.apiUrl+"/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({problem_id:catalog[state.activeProblem].id?("p"+String(catalog[state.activeProblem].id).padStart(5,"0")):data.problemId,language:document.getElementById("language").value,code:codeEditor.value,custom_input:c?.stdin||""})});
    const payload=await r.json();
    const verdict=payload.verdict||"Wrong Answer";
    state.results={verdict,stdout:payload.actual_output||"",diagnostic:payload.stderr||"",duration_ms:payload.duration_ms||0,tests:[{status:verdict==="Accepted"?"PASSED":verdict,stdin:c?.stdin||"",expected_stdout:payload.expected_output||c?.expected_stdout||"",stdout:payload.actual_output||""}]};
  }catch(error){
    state.results={verdict:"Runtime Error",stdout:"",diagnostic:String(error),duration_ms:0,tests:[{status:"Runtime Error",stdin:c?.stdin||"",expected_stdout:c?.expected_stdout||"",stdout:""}]};
  }
  if(state.results.verdict!=="Accepted"){
    document.getElementById("aiBadge").innerHTML='<span class="ai-badge">!</span>';
    explainWithAI();
  }
  btn.textContent="▶ Run";renderResults();document.querySelectorAll("[data-console]").forEach(t=>t.classList.toggle("active",t.dataset.console==="result"));
}
async function submitCode(){
  saveCurrentCase();
  const btn=document.getElementById("submitBtn");btn.innerHTML='<span class="loading"></span>';
  const p=catalog[state.activeProblem];
  const problemId="p"+String(p.id).padStart(5,"0");
  const tests=[];
  let overall="Accepted";
  let duration=0;
  for(let i=0;i<state.cases.length;i++){
    const c=state.cases[i];
    try{
      const r=await fetch(data.apiUrl+"/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({problem_id:problemId,language:document.getElementById("language").value,code:codeEditor.value,custom_input:c.stdin||""})});
      const payload=await r.json();
      const verdict=payload.verdict||"Wrong Answer";
      duration+=payload.duration_ms||0;
      tests.push({case:i+1,status:verdict==="Accepted"?"PASSED":verdict,stdin:c.stdin||"",expected_stdout:payload.expected_output||c.expected_stdout||"",stdout:payload.actual_output||"",stderr:payload.stderr||""});
      if(verdict!=="Accepted")overall=verdict;
    }catch(error){
      overall="Runtime Error";
      tests.push({case:i+1,status:"Runtime Error",stdin:c.stdin||"",expected_stdout:c.expected_stdout||"",stdout:"",stderr:String(error)});
    }
  }
  state.results={verdict:overall,diagnostic:"",duration_ms:duration,tests};
  if(overall!=="Accepted"){
    document.getElementById("aiBadge").innerHTML='<span class="ai-badge">!</span>';
    explainWithAI();
  }
  btn.textContent="✓ Submit";renderResults();document.querySelectorAll("[data-console]").forEach(t=>t.classList.toggle("active",t.dataset.console==="result"));
}
document.getElementById("runBtn").onclick=runCode;
document.getElementById("submitBtn").onclick=submitCode;

document.getElementById("language").onchange=e=>{
  const p=catalog[state.activeProblem];
  codeEditor.value=starters[e.target.value](p);
  codeHighlight.className=e.target.value==="C++"?"":"language-"+e.target.value.toLowerCase();
  updateLines();
};
document.getElementById("resetCode").onclick=()=>{const p=catalog[state.activeProblem];codeEditor.value=starters[document.getElementById("language").value](p);updateLines()};
document.getElementById("formatCode").onclick=()=>{
  let indent=0,lines=codeEditor.value.split("\n").map(line=>{line=line.trim();if(line.startsWith("}")||line.startsWith("};"))indent=Math.max(0,indent-1);const out="    ".repeat(indent)+line;if(line.endsWith("{"))indent++;return out});codeEditor.value=lines.join("\n");updateLines();
};

document.querySelectorAll("[data-tab]").forEach(tab=>tab.onclick=()=>{
  document.querySelectorAll("[data-tab]").forEach(t=>t.classList.remove("active"));tab.classList.add("active");
  const key=tab.dataset.tab;
  const p=catalog[state.activeProblem];
  if(key==="description"){document.getElementById("problemBody").innerHTML=problemDescription(p)}
  else{
    const solution=p.accepted_solution;
    if(solution&&solution.available){
      const code=escapeHtml(solution.code);
      document.getElementById("problemBody").innerHTML=`<h1>Solutions</h1><div class="settings-row"><span class="difficulty">${escapeHtml(solution.language||"C++")}</span><button class="icon-btn" id="copySolution">Copy</button></div><pre><code>${code}</code></pre>`;
      document.getElementById("copySolution").onclick=()=>navigator.clipboard.writeText(solution.code);
    }else{
      document.getElementById("problemBody").innerHTML='<h1>Solutions</h1><p>No accepted solution source is available for this problem.</p>';
    }
  }
});

const overlay=document.getElementById("drawerOverlay");
document.getElementById("drawerBtn").onclick=()=>overlay.classList.add("open");
overlay.onclick=e=>{if(e.target===overlay)overlay.classList.remove("open")};
function renderDrawer(filter=""){
  const list=document.getElementById("drawerList");const q=filter.trim().toLowerCase();
  list.innerHTML=catalog.map((p,index)=>({p,index})).filter(({p})=>p.title.toLowerCase().includes(q)||p.id.includes(q)||q==="").map(({p,index})=>`<button class="drawer-item ${index===state.activeProblem?"active":""}" data-index="${index}"><span>${p.id}. ${p.difficulty}</span>${escapeHtml(p.title)}</button>`).join("");
  list.querySelectorAll("[data-index]").forEach(btn=>btn.onclick=()=>{overlay.classList.remove("open");loadProblem(Number(btn.dataset.index));});
}
renderDrawer();
document.getElementById("drawerSearch").oninput=e=>renderDrawer(e.target.value);

window.addEventListener("message",e=>{if(e.data&&e.data.type==="streamlit:rerun")location.reload()});

document.querySelectorAll("[data-action]").forEach(btn=>{
  btn.onclick=()=>{
    const pane=document.getElementById(btn.dataset.pane),action=btn.dataset.action;
    if(action==="minimize"){
      const className=pane===problemPane?"collapsed-v":"collapsed-h";
      pane.classList.toggle(className);
      btn.textContent=pane.classList.contains(className)?"＋":"—";
    }else{
      const was=pane.classList.contains("maximize");
      document.querySelectorAll(".pane,.editor-pane,.console-pane").forEach(p=>p.classList.remove("maximize","hidden-pane"));
      document.querySelectorAll('[data-action="maximize"]').forEach(control=>control.textContent="⛶");
      if(was){
        document.getElementById("vResizer").classList.remove("hidden-pane");
        document.getElementById("hResizer").classList.remove("hidden-pane");
      }else{
        pane.classList.add("maximize");
        if(pane===problemPane){rightPane.classList.add("hidden-pane");document.getElementById("vResizer").classList.add("hidden-pane")}
        if(pane===editorPane){problemPane.classList.add("hidden-pane");consolePane.classList.add("hidden-pane");document.getElementById("vResizer").classList.add("hidden-pane");document.getElementById("hResizer").classList.add("hidden-pane")}
        if(pane===consolePane){problemPane.classList.add("hidden-pane");editorPane.classList.add("hidden-pane");document.getElementById("vResizer").classList.add("hidden-pane");document.getElementById("hResizer").classList.add("hidden-pane")}
        btn.textContent="🗗";
      }
    }
  }
});

function dragResizer(resizer,axis){
  resizer.addEventListener("mousedown",start);
  function start(e){
    e.preventDefault();
    resizer.classList.add("active");
    document.body.style.cursor=axis==="x"?"col-resize":"row-resize";
    const move=e2=>{
      if(axis==="x"){
        const rect=document.getElementById("workspace").getBoundingClientRect();
        const pct=Math.max(22,Math.min(72,(e2.clientX-rect.left)/rect.width*100));
        problemPane.style.width=pct+"%";rightPane.style.width=(100-pct)+"%";
      }else{
        const rect=rightPane.getBoundingClientRect();
        const consoleHeight=Math.max(90,Math.min(rect.height-90,rect.bottom-e2.clientY));
        consolePane.style.height=consoleHeight+"px";
        editorPane.style.flex="1";
      }
    };
    const up=()=>{
      resizer.classList.remove("active");
      document.body.style.cursor="";
      window.removeEventListener("mousemove",move);
      window.removeEventListener("mouseup",up);
    };
    window.addEventListener("mousemove",move);
    window.addEventListener("mouseup",up);
  }
}
dragResizer(document.getElementById("vResizer"),"x");
dragResizer(document.getElementById("hResizer"),"y");
</script>
</body>
</html>
"""

html = html.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))

components.html(html, height=900, scrolling=False)
