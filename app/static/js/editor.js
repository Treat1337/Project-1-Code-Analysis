// =========================================================================
// editor.js — Code Editor Highlighting, Line Numbers, Indentation & Events
// =========================================================================

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// -------------------------------------------------------------------------
// C++ Syntax Highlighting (VS Code Dark+ Palette)
// -------------------------------------------------------------------------
function highlightCpp(code) {
  if (!code) return "";

  const controlKeywords = new Set([
    "if", "else", "for", "while", "do", "return", "break", "continue", "switch", "case",
    "default", "goto", "try", "catch", "throw"
  ]);

  const typeKeywords = new Set([
    "int", "long", "double", "float", "char", "bool", "void", "auto", "const", "static",
    "struct", "class", "using", "namespace", "true", "false", "unsigned", "signed",
    "short", "constexpr", "inline", "virtual", "public", "private", "protected",
    "template", "typename", "typedef", "sizeof", "new", "delete", "explicit", "friend",
    "operator", "this", "enum", "union", "volatile", "mutable"
  ]);

  const stlKeywords = new Set([
    "std", "vector", "string", "map", "set", "pair", "queue", "stack", "deque", "list",
    "priority_queue", "unordered_map", "unordered_set", "multiset", "multimap",
    "bitset", "array", "tuple", "cout", "cin", "cerr", "clog", "endl", "nullptr",
    "size_t", "int64_t", "uint64_t", "int32_t", "uint32_t", "int16_t", "uint16_t",
    "int8_t", "uint8_t", "ptrdiff_t", "stringstream", "ifstream", "ofstream", "iostream"
  ]);

  const knownFunctions = new Set([
    "main", "solve", "sort", "reverse", "push_back", "emplace_back", "pop_back",
    "size", "empty", "clear", "begin", "end", "rbegin", "rend", "front", "back",
    "top", "pop", "push", "insert", "erase", "find", "count", "lower_bound", "upper_bound",
    "min", "max", "abs", "swap", "make_pair", "make_tuple", "get", "fill", "memset",
    "memcpy", "printf", "scanf", "puts", "getline", "gcd", "lcm", "sqrt", "pow"
  ]);

  const tokenRegex = /(\/\*[\s\S]*?\*\/)|(\/\/[^\n]*)|("(?:\\.|[^"\\])*")|('(?:\\.|[^'\\])*')|(^[ \t]*#[ \t]*[a-zA-Z_]\w*(?:[ \t]*<[^>\n]+>)?|[ \t]*#[ \t]*[a-zA-Z_]\w*(?:[ \t]*<[^>\n]+>)?)|(\b(?:0x[0-9a-fA-F]+|0b[01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[fFuUlL]*)\b)|([a-zA-Z_]\w*)|(<<|>>|<=|>=|==|!=|\+\+|--|&&|\|\||::|->|[+\-*/%<>=!&|^~?:;.,\[\]{}()])|(\s+)|(.)/gm;

  let html = "";
  let match;
  while ((match = tokenRegex.exec(code)) !== null) {
    const [
      full,
      commentBlock,
      commentLine,
      strLiteral,
      charLiteral,
      preproc,
      numLiteral,
      ident,
      operator,
      whitespace,
      other
    ] = match;

    if (commentBlock || commentLine) {
      html += `<span class="tok-comment">${escapeHtml(full)}</span>`;
    } else if (strLiteral || charLiteral) {
      html += `<span class="tok-string">${escapeHtml(full)}</span>`;
    } else if (preproc) {
      const incMatch = full.match(/^([ \t]*#[ \t]*\w+)([ \t]*)(<[^>\n]+>)?(.*)$/);
      if (incMatch) {
        html += `<span class="tok-preprocessor">${escapeHtml(incMatch[1])}</span>`;
        if (incMatch[2]) html += escapeHtml(incMatch[2]);
        if (incMatch[3]) html += `<span class="tok-string">${escapeHtml(incMatch[3])}</span>`;
        if (incMatch[4]) html += escapeHtml(incMatch[4]);
      } else {
        html += `<span class="tok-preprocessor">${escapeHtml(full)}</span>`;
      }
    } else if (numLiteral) {
      html += `<span class="tok-number">${escapeHtml(full)}</span>`;
    } else if (ident) {
      if (controlKeywords.has(ident)) {
        html += `<span class="tok-keyword-control">${escapeHtml(ident)}</span>`;
      } else if (typeKeywords.has(ident)) {
        html += `<span class="tok-type">${escapeHtml(ident)}</span>`;
      } else if (stlKeywords.has(ident)) {
        html += `<span class="tok-stl">${escapeHtml(ident)}</span>`;
      } else if (knownFunctions.has(ident)) {
        html += `<span class="tok-function">${escapeHtml(ident)}</span>`;
      } else {
        const nextChar = code[match.index + full.length];
        if (nextChar === "(") {
          html += `<span class="tok-function">${escapeHtml(ident)}</span>`;
        } else {
          html += `<span class="tok-identifier">${escapeHtml(ident)}</span>`;
        }
      }
    } else if (operator) {
      html += `<span class="tok-operator">${escapeHtml(operator)}</span>`;
    } else if (whitespace) {
      html += escapeHtml(whitespace);
    } else {
      html += escapeHtml(other || full);
    }
  }
  return html;
}

// -------------------------------------------------------------------------
// Code Editor Utilities & Synchronization
// -------------------------------------------------------------------------
function updateHighlight() {
  const codeEditor = document.getElementById("codeEditor");
  const codeHighlightContent = document.getElementById("codeHighlightContent");
  if (codeHighlightContent && codeEditor) {
    codeHighlightContent.innerHTML = highlightCpp(codeEditor.value);
  }
}

function updateLineNumbers() {
  const codeEditor = document.getElementById("codeEditor");
  const lineNumbers = document.getElementById("lineNumbers");
  if (!codeEditor || !lineNumbers) return;
  const lines = codeEditor.value.split("\n").length;
  let html = "";
  for (let i = 1; i <= lines; i++) {
    html += `<span>${i}</span>`;
  }
  lineNumbers.innerHTML = html;
  lineNumbers.scrollTop = codeEditor.scrollTop;
}

function updateActiveLine() {
  const codeEditor = document.getElementById("codeEditor");
  const lineNumbers = document.getElementById("lineNumbers");
  const activeLineIndicator = document.getElementById("activeLineIndicator");
  const editorWorkspace = document.getElementById("editorWorkspace");
  if (!codeEditor) return;

  const code = codeEditor.value;
  const pos = codeEditor.selectionStart || 0;
  const lineIdx = code.substring(0, pos).split("\n").length - 1;

  if (lineNumbers) {
    const spans = lineNumbers.querySelectorAll("span");
    spans.forEach((s, idx) => {
      s.classList.toggle("active-num", idx === lineIdx);
    });
  }

  if (activeLineIndicator) {
    const top = 12 + lineIdx * 21 - codeEditor.scrollTop;
    if (top >= -21 && top <= (editorWorkspace?.clientHeight || 600) + 21) {
      activeLineIndicator.style.display = "block";
      activeLineIndicator.style.top = `${top}px`;
    } else {
      activeLineIndicator.style.display = "none";
    }
  }
}

function updateEditor() {
  updateLineNumbers();
  updateHighlight();
  updateActiveLine();
}

function initEditorEvents() {
  const codeEditor = document.getElementById("codeEditor");
  const codeHighlight = document.getElementById("codeHighlight");
  const lineNumbers = document.getElementById("lineNumbers");
  const langSelect = document.getElementById("langSelect");

  if (!codeEditor) return;

  codeEditor.addEventListener("input", () => {
    if (window.state) window.state.code = codeEditor.value;
    updateEditor();
  });

  codeEditor.addEventListener("scroll", () => {
    if (codeHighlight) {
      codeHighlight.scrollTop = codeEditor.scrollTop;
      codeHighlight.scrollLeft = codeEditor.scrollLeft;
    }
    if (lineNumbers) {
      lineNumbers.scrollTop = codeEditor.scrollTop;
    }
    updateActiveLine();
  });

  ["click", "keyup", "focus", "select"].forEach((evt) => {
    codeEditor.addEventListener(evt, updateActiveLine);
  });

  // Tab key inserts 4 spaces
  codeEditor.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const start = codeEditor.selectionStart;
      const end = codeEditor.selectionEnd;
      codeEditor.value = codeEditor.value.substring(0, start) + "    " + codeEditor.value.substring(end);
      codeEditor.selectionStart = codeEditor.selectionEnd = start + 4;
      if (window.state) window.state.code = codeEditor.value;
      updateEditor();
    }
  });

  // Language Change
  if (langSelect) {
    langSelect.addEventListener("change", (e) => {
      if (window.state) {
        window.state.language = e.target.value;
        window.state.code = (window.starterTemplates && window.starterTemplates[window.state.language]) || "";
        codeEditor.value = window.state.code;
        updateEditor();
      }
    });
  }

  // Reset Code
  const btnReset = document.getElementById("btnResetCode");
  if (btnReset) {
    btnReset.addEventListener("click", () => {
      if (confirm("Reset code editor to starter template?")) {
        if (window.state) {
          window.state.code = (window.starterTemplates && window.starterTemplates[window.state.language]) || "";
          codeEditor.value = window.state.code;
          updateEditor();
        }
      }
    });
  }

  // Format Code (Simple Indentation)
  const btnFormat = document.getElementById("btnFormatCode");
  if (btnFormat) {
    btnFormat.addEventListener("click", () => {
      const lines = codeEditor.value.split("\n");
      let indent = 0;
      const formatted = lines.map((line) => {
        let trimmed = line.trim();
        if (trimmed.startsWith("}") || trimmed.startsWith("};")) {
          indent = Math.max(0, indent - 1);
        }
        const indented = "    ".repeat(indent) + trimmed;
        if (trimmed.endsWith("{")) {
          indent++;
        }
        return indented;
      });
      codeEditor.value = formatted.join("\n");
      if (window.state) window.state.code = codeEditor.value;
      updateEditor();
    });
  }
}

// Expose globally
window.highlightCpp = highlightCpp;
window.updateHighlight = updateHighlight;
window.updateLineNumbers = updateLineNumbers;
window.updateActiveLine = updateActiveLine;
window.updateEditor = updateEditor;
window.initEditorEvents = initEditorEvents;
