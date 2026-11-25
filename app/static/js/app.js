// -------------------------------------------------------------------------
    // Application State
    // -------------------------------------------------------------------------
    const API_BASE = (window.location.protocol === "file:" || !window.location.origin || window.location.origin === "null")
      ? "http://127.0.0.1:8000"
      : "";
    const AUTH_API_BASE = window.AUTH_API_BASE || "http://127.0.0.1:8080";
    const state = {
      problems: [],
      currentProblemId: "p00001",
      problemDetail: null,
      activeLeftTab: "description",
      activeConsoleTab: "testcase",
      activeCaseIndex: 0,
      cases: [],
      code: "",
      language: "C++",
      lastRunResult: null,
      aiLoading: false,
      aiFeedback: "",
      aiError: "",
      user: null,
      csrfToken: "",
      historyPage: 1,
      historyLimit: 10,
      historyTotal: 0,
      historyItems: [],
      lastSubmissionAnalysis: null,
    };

    // Clean default C++ starter template (C++ only)
    const starterTemplates = {
      "C++": `#include <bits/stdc++.h>
using namespace std;

int main() {
    
    return 0;
}
`,
    };
    window.state = state;
    window.starterTemplates = starterTemplates;

    // DOM Elements
    const leftPane = document.getElementById("leftPane");
    const rightPane = document.getElementById("rightPane");
    const editorPane = document.getElementById("editorPane");
    const consolePane = document.getElementById("consolePane");
    const codeEditor = document.getElementById("codeEditor");
    const codeHighlight = document.getElementById("codeHighlight");
    const codeHighlightContent = document.getElementById("codeHighlightContent");
    const activeLineIndicator = document.getElementById("activeLineIndicator");
    const editorWorkspace = document.getElementById("editorWorkspace");
    const lineNumbers = document.getElementById("lineNumbers");
    const langSelect = document.getElementById("langSelect");
    const leftBody = document.getElementById("leftBody");
    const consoleBody = document.getElementById("consoleBody");
    const topProblemId = document.getElementById("topProblemId");
    const topProblemTitle = document.getElementById("topProblemTitle");
    const drawerBackdrop = document.getElementById("drawerBackdrop");
    const drawerList = document.getElementById("drawerList");
    const drawerSearch = document.getElementById("drawerSearch");
    const aiBadgeContainer = document.getElementById("aiBadgeContainer");

    // -------------------------------------------------------------------------
    // Markdown & String Utilities
    // -------------------------------------------------------------------------
    function escapeHtml(str) {
      return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function renderMarkdown(text) {
      if (!text) return "";
      if (window.marked && typeof window.marked.parse === "function") {
        try {
          return window.marked.parse(text);
        } catch (e) {
          console.warn("marked.parse error, using fallback", e);
        }
      }
      let html = escapeHtml(text);
      html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
      html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
      html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");
      html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");
      html = html.replace(/\*(.*?)\*/gim, "<em>$1</em>");
      html = html.replace(/```([a-z0-9]*)\n([\s\S]*?)```/gim, "<pre><code>$2</code></pre>");
      html = html.replace(/`([^`]+)`/gim, "<code>$1</code>");
      html = html.replace(/^\- (.*$)/gim, "<ul><li>$1</li></ul>");
      html = html.replace(/\n\n/gim, "<br><br>");
      return html;
    }

    // -------------------------------------------------------------------------
    // Problem Loading & Rendering
    // -------------------------------------------------------------------------
    async function loadProblemList() {
      try {
        const res = await fetch(`${API_BASE}/api/problems`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        state.problems = data.problems || [];
        renderDrawerList();

        // Check URL query param or default to p00001
        const urlParams = new URLSearchParams(window.location.search);
        const queryPid = urlParams.get("problem");
        const initialPid = (queryPid && state.problems.some((p) => p.problem_id === queryPid))
          ? queryPid
          : (state.problems[0]?.problem_id || "p00001");

        loadProblem(initialPid);
      } catch (err) {
        console.error("Failed to load problem list:", err);
        leftBody.innerHTML = `<div class="result-card error"><strong>Error loading problems:</strong><p>${err.message}</p></div>`;
      }
    }

    async function loadProblem(problemId) {
      state.currentProblemId = problemId;
      topProblemId.textContent = problemId;
      topProblemTitle.textContent = "Loading...";
      leftBody.innerHTML = `<div style="padding: 20px;"><div class="spinner"></div> Loading ${problemId}...</div>`;

      // Update URL
      const url = new URL(window.location);
      url.searchParams.set("problem", problemId);
      window.history.replaceState({}, "", url);

      try {
        const res = await fetch(`${API_BASE}/api/problem/${problemId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const detail = await res.json();
        state.problemDetail = detail;

        topProblemTitle.textContent = detail.title || problemId;

        // Populate test cases
        if (detail.test_cases && detail.test_cases.length > 0) {
          state.cases = detail.test_cases.map((c, i) => ({
            name: c.name || `Case ${i + 1}`,
            stdin: c.stdin || "",
            expected_stdout: c.expected_stdout || "",
          }));
        } else {
          state.cases = [{ name: "Case 1", stdin: "", expected_stdout: "" }];
        }
        state.activeCaseIndex = 0;

        // Reset starter template if editor is empty or unchanged
        state.code = starterTemplates[state.language] || "";
        codeEditor.value = state.code;
        updateEditor();

        // Reset execution results & AI feedback
        state.lastRunResult = null;
        state.aiFeedback = "";
        state.aiError = "";
        aiBadgeContainer.innerHTML = "";

        renderLeftPane();
        renderConsole();
        renderDrawerList();
      } catch (err) {
        topProblemTitle.textContent = "Error loading problem";
        leftBody.innerHTML = `<div class="result-card error"><strong>Failed to load problem ${problemId}:</strong><p>${err.message}</p></div>`;
      }
    }

    // Render Left Pane (Description vs Solutions)
    function renderLeftPane() {
      if (state.activeLeftTab === "description") {
        if (!state.problemDetail) return;
        leftBody.innerHTML = state.problemDetail.html || `<p>${escapeHtml(state.problemDetail.plain_text || "")}</p>`;
      } else if (state.activeLeftTab === "solutions") {
        const sol = state.problemDetail?.accepted_solution;
        if (sol && sol.available) {
          leftBody.innerHTML = `
            <div class="solution-view">
              <div class="solution-meta-bar">
                <span class="badge badge-green">✓ Accepted Solution</span>
                <span class="badge badge-blue">${escapeHtml(sol.language || "C++")}</span>
                <span style="font-size: 12px; color: var(--text-muted);">Submission: <code>${escapeHtml(sol.submission_id || "")}</code></span>
                <button class="copy-btn" id="btnCopySolution">📋 Copy Code</button>
              </div>
              <pre class="solution-code-block"><code id="solutionCode">${highlightCpp(sol.code || "")}</code></pre>
            </div>
          `;
          document.getElementById("btnCopySolution").addEventListener("click", () => {
            navigator.clipboard.writeText(sol.code || "");
            const btn = document.getElementById("btnCopySolution");
            btn.textContent = "✓ Copied!";
            setTimeout(() => { btn.textContent = "📋 Copy Code"; }, 2000);
          });
        } else {
          leftBody.innerHTML = `
            <div class="result-card" style="border-left-color: var(--yellow);">
              <strong style="color: var(--yellow);">Accepted Solution Not Available</strong>
              <p style="margin-top: 6px; color: #bbb;">${escapeHtml(sol?.reason || "No accepted source submission found for this problem.")}</p>
            </div>
          `;
        }
      }
    }

    // Left Tabs Switching
    document.querySelectorAll("#leftTabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#leftTabs .tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        state.activeLeftTab = tab.dataset.tab;
        renderLeftPane();
      });
    });

    // -------------------------------------------------------------------------
    // Console Rendering (Testcase, Test Result, AI Feedback)
    // -------------------------------------------------------------------------
    function renderConsole() {
      if (state.activeConsoleTab === "testcase") {
        renderTestcaseTab();
      } else if (state.activeConsoleTab === "result") {
        renderResultTab();
      } else if (state.activeConsoleTab === "ai") {
        renderAITab();
      }
    }

    function renderTestcaseTab() {
      let pillsHtml = state.cases
        .map((c, i) => `
          <button class="case-pill ${i === state.activeCaseIndex ? "active" : ""}" data-case-index="${i}">
            ${escapeHtml(c.name)}
          </button>
        `)
        .join("");
      pillsHtml += `<button class="case-pill" id="btnAddCase" title="Add Custom Test Case">+</button>`;

      const cur = state.cases[state.activeCaseIndex] || { stdin: "", expected_stdout: "" };

      consoleBody.innerHTML = `
        <div class="case-pills-row">${pillsHtml}</div>
        <div class="case-grid">
          <div class="field-group">
            <label class="field-label">Input</label>
            <textarea class="field-textarea" id="caseInput">${escapeHtml(cur.stdin)}</textarea>
          </div>
          <div class="field-group">
            <label class="field-label">Expected Output</label>
            <textarea class="field-textarea" id="caseExpected">${escapeHtml(cur.expected_stdout)}</textarea>
          </div>
        </div>
      `;

      // Event handlers for case pills
      consoleBody.querySelectorAll("[data-case-index]").forEach((btn) => {
        btn.addEventListener("click", () => {
          saveCurrentCaseInputs();
          state.activeCaseIndex = Number(btn.dataset.caseIndex);
          renderTestcaseTab();
        });
      });

      // Add custom case
      document.getElementById("btnAddCase").addEventListener("click", () => {
        saveCurrentCaseInputs();
        state.cases.push({
          name: `Case ${state.cases.length + 1}`,
          stdin: "",
          expected_stdout: "",
        });
        state.activeCaseIndex = state.cases.length - 1;
        renderTestcaseTab();
      });

      // Realtime input updating
      const inEl = document.getElementById("caseInput");
      const outEl = document.getElementById("caseExpected");
      inEl.addEventListener("input", () => {
        if (state.cases[state.activeCaseIndex]) {
          state.cases[state.activeCaseIndex].stdin = inEl.value;
        }
      });
      outEl.addEventListener("input", () => {
        if (state.cases[state.activeCaseIndex]) {
          state.cases[state.activeCaseIndex].expected_stdout = outEl.value;
        }
      });
    }

    function saveCurrentCaseInputs() {
      const inEl = document.getElementById("caseInput");
      const outEl = document.getElementById("caseExpected");
      if (inEl && state.cases[state.activeCaseIndex]) {
        state.cases[state.activeCaseIndex].stdin = inEl.value;
      }
      if (outEl && state.cases[state.activeCaseIndex]) {
        state.cases[state.activeCaseIndex].expected_stdout = outEl.value;
      }
    }

    function renderResultTab() {
      if (!state.lastRunResult) {
        consoleBody.innerHTML = `
          <div style="padding: 18px 0; color: var(--text-muted); text-align: center;">
            <p>You must run your code first to see execution results.</p>
          </div>
        `;
        return;
      }

      const res = state.lastRunResult;
      const verdict = res.verdict || "Unknown";
      let toneClass = "wrong";
      let verdictColor = "var(--red)";

      if (verdict === "Accepted") {
        toneClass = "accepted";
        verdictColor = "var(--green)";
      } else if (verdict === "Time Limit Exceeded") {
        toneClass = "tle";
        verdictColor = "var(--yellow)";
      } else if (verdict === "Compilation Error" || verdict === "Runtime Error") {
        toneClass = "error";
      }

      let summaryHtml = "";
      if (res.tests && res.tests.length > 0) {
        summaryHtml = `<span style="margin-left: 8px;">Passed ${res.passed_count}/${res.total_count} test cases</span>`;
      }

      let diffHtml = "";
      if (res.actual_output !== undefined || res.expected_output !== undefined) {
        diffHtml = `
          <div class="output-diff-grid">
            <div>
              <div class="field-label">Your Stdout:</div>
              <div class="output-box">${escapeHtml(res.actual_output || "(empty)")}</div>
            </div>
            <div>
              <div class="field-label">Expected Output:</div>
              <div class="output-box">${escapeHtml(res.expected_output || "(empty)")}</div>
            </div>
          </div>
        `;
      }

      let stderrHtml = "";
      if (res.stderr) {
        stderrHtml = `
          <div class="field-label" style="margin-top: 10px; color: #ff8888;">Error Diagnostic / Compiler Output:</div>
          <div class="stderr-box">${escapeHtml(res.stderr)}</div>
        `;
      }

      let aiActionHtml = "";
      if (verdict !== "Accepted") {
        aiActionHtml = `
          <div style="margin-top: 12px; display: flex; align-items: center; justify-content: space-between; padding-top: 10px; border-top: 1px solid #333;">
            <span style="color: #ffa116; font-size: 12px;">AI analysis in progress...</span>
            <button class="btn btn-run" id="btnGoToAI" style="height: 28px; padding: 0 10px; font-size: 12px;">
              View AI Feedback →
            </button>
          </div>
        `;
      }

      consoleBody.innerHTML = `
        <div class="result-card ${toneClass}">
          <div class="result-header">
            <span class="result-verdict" style="color: ${verdictColor};">${escapeHtml(verdict)}</span>
            <span class="result-meta">Runtime: ${res.duration_ms ?? 0} ms ${summaryHtml}</span>
          </div>
          ${diffHtml}
          ${stderrHtml}
          ${aiActionHtml}
        </div>
      `;

      const btnGoToAI = document.getElementById("btnGoToAI");
      if (btnGoToAI) {
        btnGoToAI.addEventListener("click", () => {
          switchConsoleTab("ai");
        });
      }
    }

    function renderAITab() {
      if (state.aiLoading) {
        consoleBody.innerHTML = `
          <div class="ai-card">
            <div class="ai-header-bar">
              <div class="spinner"></div>
              <span class="ai-header-title">Analyzing code with AI...</span>
            </div>
            <div class="skeleton-bar" style="width: 85%;"></div>
            <div class="skeleton-bar" style="width: 95%;"></div>
            <div class="skeleton-bar" style="width: 70%;"></div>
          </div>
        `;
        return;
      }

      if (state.aiError) {
        consoleBody.innerHTML = `
          <div class="ai-card" style="border-left: 3px solid var(--red);">
            <div class="ai-header-bar">
              <span class="ai-header-title" style="color: var(--red);">AI Feedback Unavailable</span>
              <button class="btn btn-run" id="btnRetryAI" style="margin-left: auto; height: 26px; font-size: 11px;">↺ Retry</button>
            </div>
            <p style="color: #ff9999; margin-bottom: 8px;">${escapeHtml(state.aiError)}</p>
            <div style="background: #141414; padding: 8px; border-radius: 4px; font-size: 12px; color: #aaa;">
              <strong>Troubleshooting:</strong>
              <ul style="margin: 6px 0 0 18px;">
                <li>Make sure Ollama is running (<code>ollama serve</code>)</li>
                <li>Verify the AI service is ready and reachable</li>
                <li>Check endpoints at <a href="http://127.0.0.1:11434/api/tags" target="_blank" style="color: var(--blue);">http://127.0.0.1:11434/api/tags</a></li>
              </ul>
            </div>
          </div>
        `;
        document.getElementById("btnRetryAI").addEventListener("click", triggerAIFeedback);
        return;
      }

      if (state.aiFeedback) {
        consoleBody.innerHTML = `
          <div class="ai-card">
            <div class="ai-header-bar">
              <span class="ai-header-title">AI Feedback</span>
              <button class="btn btn-run" id="btnReanalyzeAI" style="margin-left: auto; height: 26px; font-size: 11px;">↻ Re-analyze</button>
            </div>
            <div class="ai-markdown">${renderMarkdown(state.aiFeedback)}</div>
          </div>
        `;
        document.getElementById("btnReanalyzeAI").addEventListener("click", triggerAIFeedback);
        return;
      }

      consoleBody.innerHTML = `
        <div class="ai-card" style="text-align: center; padding: 24px;">
          <p style="color: var(--text-muted); margin-bottom: 12px;">No errors detected yet. Run or submit code to receive automated AI feedback when a testcase fails.</p>
          <button class="btn btn-run" id="btnManualAI">Ask AI to Review Code</button>
        </div>
      `;
      document.getElementById("btnManualAI")?.addEventListener("click", triggerAIFeedback);
    }

    function switchConsoleTab(tabKey) {
      document.querySelectorAll("#consoleTabs .tab").forEach((t) => {
        t.classList.toggle("active", t.dataset.console === tabKey);
      });
      state.activeConsoleTab = tabKey;
      renderConsole();
    }

    document.querySelectorAll("#consoleTabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        saveCurrentCaseInputs();
        switchConsoleTab(tab.dataset.console);
      });
    });

    // -------------------------------------------------------------------------
    // Execution & AI Feedback Logic
    // -------------------------------------------------------------------------
    async function runCode(runAll = false) {
      if (!state.user) {
        openAuthModal("login", "Please log in to run or submit code. Your code in the editor is preserved.");
        return;
      }

      saveCurrentCaseInputs();
      const runBtns = [document.getElementById("btnRun")].filter(Boolean);
      const submitBtns = [document.getElementById("btnSubmit")].filter(Boolean);
      const activeBtns = runAll ? submitBtns : runBtns;
      const originalTexts = activeBtns.map((b) => b.innerHTML);
      activeBtns.forEach((b) => {
        b.innerHTML = `<span class="spinner"></span> ${runAll ? "Submitting..." : "Running..."}`;
        b.disabled = true;
      });

      const curCase = state.cases[state.activeCaseIndex] || { stdin: "", expected_stdout: "" };

      try {
        if (!runAll) {
          const payload = {
            problem_id: state.currentProblemId,
            language: "cpp",
            code: codeEditor.value,
            custom_input: curCase.stdin,
            expected_output: curCase.expected_stdout,
          };
          const res = await authFetch("/api/code/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.status === 401) return;
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || `Execution error: HTTP ${res.status}`);

          state.lastSubmissionAnalysis = null;
          state.lastRunResult = {
            verdict: data.verdict || data.execution_status || "Unknown",
            actual_output: data.stdout || "",
            expected_output: curCase.expected_stdout || "",
            stderr: data.stderr || (Array.isArray(data.compile_diagnostics) ? data.compile_diagnostics.join("\n") : ""),
            duration_ms: data.execution_time_ms || 0,
            tests: data.tests || [],
            passed_count: data.passed_count || 0,
            total_count: data.total_count || 0,
          };
        } else {
          const requestId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + "-" + Math.random().toString(36).slice(2);
          const payload = {
            problem_id: state.currentProblemId,
            language: "cpp",
            code: codeEditor.value,
            custom_input: curCase.stdin,
            problem_description: state.problemDetail?.plain_text || "",
            sample_input: curCase.stdin || "",
            sample_output: curCase.expected_stdout || "",
            request_id: requestId,
          };
          const res = await authFetch("/api/code/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.status === 401) return;
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || `Submit error: HTTP ${res.status}`);

          const comp = data.compiler || {};
          const analysis = data.analysis || {};
          state.lastSubmissionAnalysis = { submission: data.submission, analysis };
          state.lastRunResult = {
            verdict: comp.verdict || analysis.compiler?.verdict || data.submission?.status || "Unknown",
            actual_output: comp.stdout || "",
            expected_output: curCase.expected_stdout || "",
            stderr: comp.stderr || (Array.isArray(analysis.compiler?.diagnostics) ? analysis.compiler.diagnostics.join("\n") : ""),
            duration_ms: comp.execution_time_ms || analysis.compiler?.execution_time_ms || 0,
            tests: comp.tests || [],
            passed_count: comp.passed_count || analysis.compiler?.passed_count || 0,
            total_count: comp.total_count || analysis.compiler?.total_count || 0,
          };
        }

        if (state.lastRunResult.verdict !== "Accepted") {
          aiBadgeContainer.innerHTML = `<span class="ai-badge-dot">!</span>`;
          switchConsoleTab("ai");
          triggerAIFeedback();
        } else {
          switchConsoleTab("result");
          aiBadgeContainer.innerHTML = "";
        }
      } catch (err) {
        state.lastRunResult = {
          verdict: "Runtime Error",
          actual_output: "",
          expected_output: curCase.expected_stdout,
          stderr: String(err.message || err),
          duration_ms: 0,
        };
        switchConsoleTab("ai");
        aiBadgeContainer.innerHTML = `<span class="ai-badge-dot">!</span>`;
        triggerAIFeedback();
      } finally {
        activeBtns.forEach((b, i) => {
          b.innerHTML = originalTexts[i];
          b.disabled = false;
        });
      }
    }

    async function triggerAIFeedback() {
      state.aiLoading = true;
      state.aiFeedback = "";
      state.aiError = "";

      // Switch to AI Feedback tab so user sees loading state
      switchConsoleTab("ai");

      const curCase = state.cases[state.activeCaseIndex] || {};
      const failingInput = state.lastRunResult?.failing_input || curCase.stdin || "";
      const actualOut = state.lastRunResult?.actual_output || "";
      const expectedOut = state.lastRunResult?.expected_output || curCase.expected_stdout || "";
      const stderr = state.lastRunResult?.stderr || "";
      const verdict = state.lastRunResult?.verdict || "Wrong Answer";

      try {
        const payload = {
          problem_description: state.problemDetail?.plain_text || state.problemDetail?.html || "",
          code: codeEditor.value,
          verdict: verdict,
          failing_input: failingInput,
          actual_output: actualOut,
          expected_output: expectedOut,
          stderr: stderr,
          language: state.language,
        };

        const res = await fetch(`${API_BASE}/api/ai-feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.available) {
          state.aiFeedback = data.response || "No feedback generated.";
        } else {
          state.aiError = `${data.error || "Failed to get AI feedback."} ${data.detail || ""}`;
        }
      } catch (err) {
        state.aiError = `Error reaching AI tutor proxy: ${err.message}`;
      } finally {
        state.aiLoading = false;
        renderAITab();
      }
    }

    document.getElementById("btnRun")?.addEventListener("click", () => runCode(false));
    document.getElementById("btnSubmit")?.addEventListener("click", () => runCode(true));

    // -------------------------------------------------------------------------
    // Navigation & Random Problem Logic
    // -------------------------------------------------------------------------
    function getCurrentProblemIndex() {
      return state.problems.findIndex((p) => p.problem_id === state.currentProblemId);
    }

    document.getElementById("btnPrev").addEventListener("click", () => {
      const idx = getCurrentProblemIndex();
      if (idx > 0) {
        loadProblem(state.problems[idx - 1].problem_id);
      } else if (state.problems.length > 0) {
        loadProblem(state.problems[state.problems.length - 1].problem_id);
      }
    });

    document.getElementById("btnNext").addEventListener("click", () => {
      const idx = getCurrentProblemIndex();
      if (idx >= 0 && idx < state.problems.length - 1) {
        loadProblem(state.problems[idx + 1].problem_id);
      } else if (state.problems.length > 0) {
        loadProblem(state.problems[0].problem_id);
      }
    });

    // Random button strictly picks a different problem (newId !== currentId)
    document.getElementById("btnRandom").addEventListener("click", () => {
      if (state.problems.length <= 1) return;
      let newProblemId = state.currentProblemId;
      while (newProblemId === state.currentProblemId) {
        const randIdx = Math.floor(Math.random() * state.problems.length);
        newProblemId = state.problems[randIdx].problem_id;
      }
      loadProblem(newProblemId);
    });

    // -------------------------------------------------------------------------
    // Problem Drawer (Slide-out)
    // -------------------------------------------------------------------------
    function renderDrawerList(filter = "") {
      const query = filter.trim().toLowerCase();
      const filtered = state.problems.filter((p) => {
        return p.problem_id.toLowerCase().includes(query) || p.title.toLowerCase().includes(query);
      });

      drawerList.innerHTML = filtered
        .map((p) => `
          <button class="drawer-item ${p.problem_id === state.currentProblemId ? "active" : ""}" data-prob-id="${p.problem_id}">
            <span class="drawer-item-id">${p.problem_id}</span>
            <span class="drawer-item-title">${escapeHtml(p.title)}</span>
          </button>
        `)
        .join("");

      drawerList.querySelectorAll("[data-prob-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
          drawerBackdrop.classList.remove("open");
          loadProblem(btn.dataset.probId);
        });
      });
    }

    document.getElementById("btnDrawer").addEventListener("click", () => {
      drawerBackdrop.classList.add("open");
      drawerSearch.value = "";
      renderDrawerList();
      drawerSearch.focus();
    });

    document.getElementById("btnCloseDrawer").addEventListener("click", () => {
      drawerBackdrop.classList.remove("open");
    });

    drawerBackdrop.addEventListener("click", (e) => {
      if (e.target === drawerBackdrop) {
        drawerBackdrop.classList.remove("open");
      }
    });

    drawerSearch.addEventListener("input", (e) => {
      renderDrawerList(e.target.value);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && drawerBackdrop.classList.contains("open")) {
        drawerBackdrop.classList.remove("open");
      }
    });

    // -------------------------------------------------------------------------
    // Resizers (Draggable Splitters)
    // -------------------------------------------------------------------------
    function initSplitter(resizerEl, direction) {
      let isDragging = false;

      resizerEl.addEventListener("mousedown", (e) => {
        e.preventDefault();
        isDragging = true;
        resizerEl.classList.add("active");
        document.body.style.cursor = direction === "v" ? "col-resize" : "row-resize";
        document.body.style.userSelect = "none";
      });

      window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        if (direction === "v") {
          const workspaceRect = document.getElementById("workspace").getBoundingClientRect();
          const offset = e.clientX - workspaceRect.left;
          const pct = Math.min(Math.max((offset / workspaceRect.width) * 100, 20), 80);
          leftPane.style.width = `${pct}%`;
          rightPane.style.width = `${100 - pct}%`;
        } else {
          const rightRect = rightPane.getBoundingClientRect();
          const offsetFromBottom = rightRect.bottom - e.clientY;
          const h = Math.min(Math.max(offsetFromBottom, 70), rightRect.height - 100);
          consolePane.style.height = `${h}px`;
        }
      });

      window.addEventListener("mouseup", () => {
        if (isDragging) {
          isDragging = false;
          resizerEl.classList.remove("active");
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
        }
      });
    }

    initSplitter(document.getElementById("vResizer"), "v");
    initSplitter(document.getElementById("hResizer"), "h");

    // -------------------------------------------------------------------------
    // Window Controls (Collapse & Maximize on Every Header)
    // -------------------------------------------------------------------------
    document.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.action;
        const targetId = btn.dataset.target;
        const target = document.getElementById(targetId);

        if (action === "collapse") {
          if (target === leftPane) {
            target.classList.toggle("collapsed-v");
            btn.textContent = target.classList.contains("collapsed-v") ? "+" : "—";
          } else {
            target.classList.toggle("collapsed-h");
            btn.textContent = target.classList.contains("collapsed-h") ? "+" : "—";
          }
        } else if (action === "maximize") {
          const isMax = target.classList.contains("maximized");
          // Reset all maximizes
          document.querySelectorAll(".pane, .editor-pane, .console-pane").forEach((el) => {
            el.classList.remove("maximized", "hidden-pane");
          });
          document.querySelectorAll('[data-action="maximize"]').forEach((b) => (b.textContent = "⛶"));

          if (!isMax) {
            target.classList.add("maximized");
            btn.textContent = "❐";
            // Hide other panes
            if (target === leftPane) {
              rightPane.classList.add("hidden-pane");
              document.getElementById("vResizer").classList.add("hidden-pane");
            } else if (target === editorPane) {
              leftPane.classList.add("hidden-pane");
              consolePane.classList.add("hidden-pane");
              document.getElementById("vResizer").classList.add("hidden-pane");
              document.getElementById("hResizer").classList.add("hidden-pane");
            } else if (target === consolePane) {
              leftPane.classList.add("hidden-pane");
              editorPane.classList.add("hidden-pane");
              document.getElementById("vResizer").classList.add("hidden-pane");
              document.getElementById("hResizer").classList.add("hidden-pane");
            }
          } else {
            document.getElementById("vResizer").classList.remove("hidden-pane");
            document.getElementById("hResizer").classList.remove("hidden-pane");
          }
        }
      });
    });

    // -------------------------------------------------------------------------
    // Elapsed Timer
    // -------------------------------------------------------------------------
    let elapsedSeconds = 0;
    setInterval(() => {
      elapsedSeconds++;
      const m = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
      const s = String(elapsedSeconds % 60).padStart(2, "0");
      document.getElementById("topTimer").textContent = `${m}:${s}`;
    }, 1000);

    // -------------------------------------------------------------------------
    // Authentication, Account, Submission History & Detail Logic
    // -------------------------------------------------------------------------
    function getCookie(name) {
      const match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"));
      return match ? decodeURIComponent(match[1]) : "";
    }

    async function ensureCSRFToken() {
      if (state.csrfToken) return state.csrfToken;
      const fromCookie = getCookie("ca_csrf");
      if (fromCookie) {
        state.csrfToken = fromCookie;
        return fromCookie;
      }
      try {
        const res = await fetch(`${AUTH_API_BASE}/api/auth/csrf`, { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          state.csrfToken = data.csrf_token || "";
        }
      } catch (_) {}
      return state.csrfToken;
    }

    async function authFetch(path, options = {}) {
      const method = (options.method || "GET").toUpperCase();
      const headers = new Headers(options.headers || {});
      if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
        const csrf = await ensureCSRFToken();
        if (csrf) headers.set("X-CSRF-Token", csrf);
      }

      const res = await fetch(`${AUTH_API_BASE}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });

      if (res.status === 401 && state.user) {
        state.user = null;
        renderAuthToolbar();
        if (window.location.hash.startsWith("#account") || window.location.hash.startsWith("#submission/")) {
          window.location.hash = "#ide";
        }
        openAuthModal("login", "Your session expired. Please log in again.");
      }
      return res;
    }

    function renderAuthToolbar() {
      const btnOpenAuth = document.getElementById("btnOpenAuth");
      const btnUserMenu = document.getElementById("btnUserMenu");
      const navUsername = document.getElementById("navUsername");
      const dropdown = document.getElementById("userDropdown");

      if (state.user) {
        btnOpenAuth.style.display = "none";
        btnUserMenu.style.display = "inline-flex";
        navUsername.textContent = state.user.username;
      } else {
        btnOpenAuth.style.display = "inline-flex";
        btnUserMenu.style.display = "none";
        dropdown.classList.remove("open");
      }
    }

    function showAlert(el, type, msg) {
      if (!el) return;
      if (!msg) {
        el.className = "form-alert";
        el.textContent = "";
        return;
      }
      el.className = `form-alert ${type}`;
      el.textContent = msg;
    }

    function openAuthModal(tab = "login", infoMsg = "") {
      const modal = document.getElementById("authModal");
      switchAuthTab(tab);
      showAlert(document.getElementById("authModalAlert"), infoMsg ? "info" : "", infoMsg);
      modal.classList.add("open");
    }

    function closeAuthModal() {
      document.getElementById("authModal").classList.remove("open");
      document.getElementById("loginPassword").value = "";
      document.getElementById("regPassword").value = "";
      document.getElementById("regConfirmPassword").value = "";
    }

    function switchAuthTab(tab) {
      const isLogin = tab === "login";
      document.getElementById("tabLoginBtn").classList.toggle("active", isLogin);
      document.getElementById("tabRegisterBtn").classList.toggle("active", !isLogin);
      document.getElementById("loginForm").style.display = isLogin ? "flex" : "none";
      document.getElementById("registerForm").style.display = isLogin ? "none" : "flex";
      showAlert(document.getElementById("authModalAlert"), "", "");
    }

    async function restoreSession() {
      try {
        const res = await fetch(`${AUTH_API_BASE}/api/auth/me`, { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          state.user = data.user || null;
          await ensureCSRFToken();
        } else {
          state.user = null;
        }
      } catch (_) {
        state.user = null;
      }
      renderAuthToolbar();
      handleRoute();
    }

    async function handleLogout() {
      try {
        await authFetch("/api/auth/logout", { method: "POST" });
      } catch (_) {}
      state.user = null;
      state.csrfToken = "";
      renderAuthToolbar();
      window.location.hash = "#ide";
    }

    function formatDateTime(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
    }

    function statusPillClass(status) {
      const s = String(status || "").toLowerCase();
      if (s === "completed" || s === "accepted" || s === "success") return "ok";
      if (s === "compile_error" || s === "failed" || s === "error") return "err";
      return "warn";
    }

    async function loadAccountPage() {
      if (!state.user) {
        window.location.hash = "#ide";
        openAuthModal("login", "Please log in to view My Account.");
        return;
      }

      document.getElementById("acctUsername").textContent = state.user.username || "—";
      document.getElementById("acctEmail").textContent = state.user.email || "Not set";
      document.getElementById("acctCreatedAt").textContent = formatDateTime(state.user.created_at);

      try {
        const statsRes = await authFetch("/api/submissions/stats");
        if (statsRes.ok) {
          const stats = await statsRes.json();
          document.getElementById("statTotal").textContent = stats.total ?? 0;
          document.getElementById("statAccepted").textContent = stats.accepted ?? 0;
          document.getElementById("statIncorrect").textContent = stats.incorrect ?? 0;
          document.getElementById("statCompileErrors").textContent = stats.compile_errors ?? 0;
        }
      } catch (_) {}

      await loadSubmissionHistory();
    }

    async function loadSubmissionHistory() {
      const alertEl = document.getElementById("histAlert");
      showAlert(alertEl, "", "");

      const status = document.getElementById("histStatusFilter").value;
      const search = document.getElementById("histSearch").value.trim().toLowerCase();
      const sort = document.getElementById("histSort").value;

      const params = new URLSearchParams({
        page: String(state.historyPage),
        limit: String(state.historyLimit),
      });
      if (status) params.set("status", status);

      try {
        const res = await authFetch(`/api/submissions?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        let items = Array.isArray(data.submissions) ? data.submissions : [];

        if (search) {
          items = items.filter((it) =>
            String(it.problem_id || "").toLowerCase().includes(search) ||
            String(it.id || "").includes(search)
          );
        }
        if (sort === "oldest") {
          items = items.slice().reverse();
        }

        state.historyTotal = data.total ?? items.length;
        state.historyItems = items;
        renderHistoryTable(items);
      } catch (err) {
        showAlert(alertEl, "error", `Failed to load submission history: ${err.message}`);
      }
    }

    function renderHistoryTable(items) {
      const tbody = document.getElementById("histTableBody");
      const totalPages = Math.max(1, Math.ceil((state.historyTotal || 0) / state.historyLimit));
      document.getElementById("histPageInfo").textContent = `Page ${state.historyPage} of ${totalPages} (${state.historyTotal} total)`;
      document.getElementById("btnHistPrev").disabled = state.historyPage <= 1;
      document.getElementById("btnHistNext").disabled = state.historyPage >= totalPages;

      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="color: var(--text-muted); text-align: center;">No submissions found.</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map((s) => `
        <tr>
          <td>#${s.id}</td>
          <td><span class="prob-id-badge">${escapeHtml(s.problem_id || "")}</span></td>
          <td>${escapeHtml(formatDateTime(s.created_at))}</td>
          <td><span class="status-pill ${statusPillClass(s.status)}">${escapeHtml(s.status)}</span></td>
          <td>${escapeHtml(s.compile_status || "—")}</td>
          <td><button class="btn" onclick="window.location.hash='#submission/${s.id}'" style="height: 28px; font-size: 12px;">View Detail</button></td>
        </tr>
      `).join("");
    }

    function renderModelCard(title, modelObj) {
      if (!modelObj) {
        return `<div class="stat-box"><div class="stat-label">${escapeHtml(title)}</div><div style="color: var(--text-muted); font-size: 13px;">Unavailable</div></div>`;
      }
      if (!modelObj.available) {
        return `<div class="stat-box"><div class="stat-label">${escapeHtml(title)}</div><div style="color: var(--text-muted); font-size: 12.5px;">${escapeHtml(modelObj.reason || "Not available")}</div></div>`;
      }
      const pct = typeof modelObj.confidence === "number" ? `${(modelObj.confidence * 100).toFixed(1)}%` : "—";
      const cls = String(modelObj.label || "").toLowerCase() === "correct" ? "ok" : "warn";
      return `
        <div class="stat-box">
          <div class="stat-label">${escapeHtml(title)}</div>
          <div style="display:flex; align-items:center; justify-content:space-between; margin-top:4px;">
            <span class="status-pill ${cls}">${escapeHtml(modelObj.label || "Unknown")}</span>
            <span style="font-size: 14px; font-weight: 600;">${pct}</span>
          </div>
        </div>
      `;
    }

    async function loadSubmissionDetail(id) {
      if (!state.user) {
        window.location.hash = "#ide";
        openAuthModal("login", "Please log in to view submission details.");
        return;
      }
      const alertEl = document.getElementById("detailAlert");
      showAlert(alertEl, "", "");
      document.getElementById("detailHeading").textContent = `Submission #${id}`;
      document.getElementById("detailSubheading").textContent = "Loading...";

      try {
        const res = await authFetch(`/api/submissions/${id}`);
        if (res.status === 404) {
          showAlert(alertEl, "error", "Submission not found or you do not have permission to view it.");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const sub = data.submission;
        let analysis = {};
        if (sub.analysis_result) {
          try { analysis = JSON.parse(sub.analysis_result); } catch (_) {}
        }

        document.getElementById("detailHeading").textContent = `Submission #${sub.id} — ${sub.problem_id}`;
        document.getElementById("detailSubheading").textContent = `Submitted at: ${formatDateTime(sub.created_at)} | Language: ${sub.language} | Status: ${sub.status}`;

        const comp = analysis.compiler || {};
        const verdict = comp.verdict || sub.compile_status || sub.status;
        const badge = document.getElementById("detailVerifiedBadge");
        badge.textContent = verdict;
        badge.className = `status-pill ${statusPillClass(verdict)}`;

        const diagList = Array.isArray(comp.diagnostics) && comp.diagnostics.length
          ? `<pre class="code-readonly" style="margin-top:8px; color:#ff9c9e;">${escapeHtml(comp.diagnostics.join("\n"))}</pre>`
          : `<div style="margin-top:6px; color: var(--text-muted);">No compiler diagnostics.</div>`;
        document.getElementById("detailCompilerBox").innerHTML = `
          <div>Compile Status: <strong>${escapeHtml(comp.status || sub.compile_status || "—")}</strong> | Execution Time: <strong>${comp.execution_time_ms ?? 0} ms</strong></div>
          ${diagList}
        `;

        const mv = analysis.model_version || {};
        const mvText = [
          mv.astnn ? `ASTNN: ${mv.astnn}` : "",
          mv.codebert ? `CodeBERT: ${mv.codebert}` : "",
          mv.codeclassifier ? `Classifier: ${mv.codeclassifier}` : "",
          analysis.pipeline_version ? `Pipeline: ${analysis.pipeline_version}` : "",
        ].filter(Boolean).join(" | ");
        document.getElementById("detailModelVersions").textContent = mvText || (sub.model_version || "");

        document.getElementById("detailModelsGrid").innerHTML = [
          renderModelCard("ASTNN", analysis.astnn),
          renderModelCard("CodeBERT", analysis.codebert),
          renderModelCard("CodeClassifier", analysis.codeclassifier),
        ].join("");

        const errCard = document.getElementById("detailErrorSummaryCard");
        if (sub.error_summary) {
          errCard.style.display = "block";
          document.getElementById("detailErrorSummary").textContent = sub.error_summary;
        } else {
          errCard.style.display = "none";
        }

        document.getElementById("detailSourceCode").innerHTML = highlightCpp(sub.source_code || "");
      } catch (err) {
        showAlert(alertEl, "error", `Failed to load submission detail: ${err.message}`);
      }
    }

    function handleRoute() {
      const hash = window.location.hash || "#ide";
      const workspaceEl = document.getElementById("workspace");
      const accountEl = document.getElementById("accountView");
      const detailEl = document.getElementById("submissionDetailView");

      workspaceEl.style.display = "none";
      accountEl.classList.remove("active");
      detailEl.classList.remove("active");

      if (hash === "#account") {
        accountEl.classList.add("active");
        loadAccountPage();
      } else if (hash.startsWith("#submission/")) {
        const id = hash.slice("#submission/".length);
        detailEl.classList.add("active");
        loadSubmissionDetail(id);
      } else {
        workspaceEl.style.display = "flex";
      }
    }

    window.addEventListener("hashchange", handleRoute);

    // Event bindings for Auth, Account, Modals & History
    document.getElementById("btnOpenAuth").addEventListener("click", () => openAuthModal("login"));
    document.getElementById("btnCloseAuthModal").addEventListener("click", closeAuthModal);
    document.getElementById("tabLoginBtn").addEventListener("click", () => switchAuthTab("login"));
    document.getElementById("tabRegisterBtn").addEventListener("click", () => switchAuthTab("register"));
    document.getElementById("linkToRegister").addEventListener("click", (e) => { e.preventDefault(); switchAuthTab("register"); });
    document.getElementById("linkToLogin").addEventListener("click", (e) => { e.preventDefault(); switchAuthTab("login"); });

    document.getElementById("btnUserMenu").addEventListener("click", (e) => {
      e.stopPropagation();
      document.getElementById("userDropdown").classList.toggle("open");
    });
    document.addEventListener("click", () => document.getElementById("userDropdown").classList.remove("open"));
    document.getElementById("btnMenuAccount").addEventListener("click", () => {
      document.getElementById("userDropdown").classList.remove("open");
      window.location.hash = "#account";
    });
    document.getElementById("btnMenuLogout").addEventListener("click", handleLogout);
    document.getElementById("btnAccountLogout").addEventListener("click", handleLogout);
    document.getElementById("btnBackToIdeFromAccount").addEventListener("click", () => { window.location.hash = "#ide"; });
    document.getElementById("btnBackToIdeFromDetail").addEventListener("click", () => { window.location.hash = "#ide"; });
    document.getElementById("btnBackToAccount").addEventListener("click", () => { window.location.hash = "#account"; });

    document.getElementById("btnOpenChangePassword").addEventListener("click", () => {
      showAlert(document.getElementById("changePwdAlert"), "", "");
      document.getElementById("changePasswordModal").classList.add("open");
    });
    document.getElementById("btnCloseChangePwdModal").addEventListener("click", () => {
      document.getElementById("changePasswordModal").classList.remove("open");
    });

    document.getElementById("loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("authModalAlert");
      const btn = document.getElementById("btnLoginSubmit");
      const identifier = document.getElementById("loginIdentifier").value.trim();
      const password = document.getElementById("loginPassword").value;

      if (!identifier || !password) {
        showAlert(alertEl, "error", "Please enter username/email and password.");
        return;
      }

      btn.disabled = true;
      btn.textContent = "Logging in...";
      try {
        const res = await fetch(`${AUTH_API_BASE}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ username: identifier, password }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          showAlert(alertEl, "error", data.error || `Login failed (HTTP ${res.status})`);
          return;
        }
        state.user = data.user;
        state.csrfToken = data.csrf_token || getCookie("ca_csrf");
        renderAuthToolbar();
        closeAuthModal();
      } catch (err) {
        showAlert(alertEl, "error", `Network error: ${err.message}`);
      } finally {
        btn.disabled = false;
        btn.textContent = "Login";
      }
    });

    document.getElementById("registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("authModalAlert");
      const btn = document.getElementById("btnRegisterSubmit");
      const username = document.getElementById("regUsername").value.trim();
      const email = document.getElementById("regEmail").value.trim();
      const password = document.getElementById("regPassword").value;
      const confirm = document.getElementById("regConfirmPassword").value;

      if (password !== confirm) {
        showAlert(alertEl, "error", "Passwords do not match.");
        return;
      }

      btn.disabled = true;
      btn.textContent = "Creating account...";
      try {
        const res = await fetch(`${AUTH_API_BASE}/api/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ username, email, password }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          showAlert(alertEl, "error", data.error || `Registration failed (HTTP ${res.status})`);
          return;
        }
        switchAuthTab("login");
        document.getElementById("loginIdentifier").value = username;
        showAlert(alertEl, "success", "Account created! You can now log in.");
      } catch (err) {
        showAlert(alertEl, "error", `Network error: ${err.message}`);
      } finally {
        btn.disabled = false;
        btn.textContent = "Create Account";
      }
    });

    document.getElementById("changePasswordForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const alertEl = document.getElementById("changePwdAlert");
      const btn = document.getElementById("btnChangePwdSubmit");
      const current_password = document.getElementById("curPwd").value;
      const new_password = document.getElementById("newPwd").value;
      const confirm = document.getElementById("confirmNewPwd").value;

      if (new_password !== confirm) {
        showAlert(alertEl, "error", "New passwords do not match.");
        return;
      }

      btn.disabled = true;
      btn.textContent = "Updating...";
      try {
        const res = await authFetch("/api/auth/change-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password, new_password }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          showAlert(alertEl, "error", data.error || `Failed (HTTP ${res.status})`);
          return;
        }
        document.getElementById("curPwd").value = "";
        document.getElementById("newPwd").value = "";
        document.getElementById("confirmNewPwd").value = "";
        showAlert(alertEl, "success", "Password updated successfully.");
      } catch (err) {
        showAlert(alertEl, "error", `Network error: ${err.message}`);
      } finally {
        btn.disabled = false;
        btn.textContent = "Update Password";
      }
    });

    document.getElementById("btnHistRefresh").addEventListener("click", () => { state.historyPage = 1; loadSubmissionHistory(); });
    document.getElementById("histStatusFilter").addEventListener("change", () => { state.historyPage = 1; loadSubmissionHistory(); });
    document.getElementById("histSort").addEventListener("change", () => loadSubmissionHistory());
    document.getElementById("histSearch").addEventListener("input", () => loadSubmissionHistory());
    document.getElementById("btnHistPrev").addEventListener("click", () => {
      if (state.historyPage > 1) { state.historyPage--; loadSubmissionHistory(); }
    });
    document.getElementById("btnHistNext").addEventListener("click", () => {
      state.historyPage++; loadSubmissionHistory();
    });

    // -------------------------------------------------------------------------
    // Initialize App
    // -------------------------------------------------------------------------
    if (window.initEditorEvents) {
      window.initEditorEvents();
    }
    codeEditor.value = starterTemplates["C++"] || "";
    if (typeof updateEditor === "function") {
      updateEditor();
    }
    loadProblemList();
    restoreSession();
