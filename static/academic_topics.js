// ──────────────────────────────────────────────────────────────────────────────
// Academic Topics — extraction, storage, screen-skip logic, and local catalog UI
// ──────────────────────────────────────────────────────────────────────────────

(function () {
  "use strict";

  /* ── state ─────────────────────────────────────────────────────────────── */
  let fullCatalog       = null;   // local JSON (Physics / Chemistry / Math)
  let storedRaw         = null;   // raw API response
  let autoPickedSubject = null;   // normalized subject string
  let autoPickedTopics  = null;   // most-specific topic list

  let selectedSubject   = null;   // user's manual pick
  let selectedChapters  = [];
  let selectedConcepts  = [];     // [{chapter, concept}]

  /* ── catalog loader ────────────────────────────────────────────────────── */
  async function initCatalog() {
    if (fullCatalog) return fullCatalog;
    try {
      const r = await fetch("/data/acadza_catalog.json");
      if (!r.ok) throw new Error("HTTP " + r.status);
      fullCatalog = await r.json();
      return fullCatalog;
    } catch (e) {
      console.error("catalog load failed:", e);
      return null;
    }
  }

  /* ── subject normalization (mirrors backend) ───────────────────────────── */
  function normalizeSubject(raw) {
    if (!raw) return null;
    const l = raw.toLowerCase().trim();
    if (l.startsWith("phy"))  return "Physics";
    if (l.startsWith("chem")) return "Chemistry";
    if (l.startsWith("math")) return "Math";
    if (l.startsWith("bio"))  return "Biology";
    return null;
  }

  /* ── helpers ───────────────────────────────────────────────────────────── */
  function arr(v) { return Array.isArray(v) ? v.filter(Boolean) : []; }

  function normalizeConvo(h) {
    return Array.isArray(h) ? h.filter(t => t && typeof t === "object") : [];
  }

  /* ── 1. extract (POST /api/extract/academic-topics) ────────────────────── */
  async function extractAcademicTopics(sessionId, text, conversationHistory) {
    try {
      const resp = await postJSON("/api/extract/academic-topics", {
        text,
        conversation_history: normalizeConvo(conversationHistory),
      }, { timeoutMs: 15000 });

      if (!resp || typeof resp !== "object") return null;
      return resp;                       // {academic_talk_detected, subjects, chapters, concepts, sub_concepts}
    } catch (e) {
      console.error("extract failed:", e);
      return null;
    }
  }

  /* ── 2. decide + store ─────────────────────────────────────────────────── */
  //  Returns { raw, autoPickedSubject, autoPickedTopics }
  //  Caller uses those to decide which screens to skip.
  async function decideAndStore(sessionId, text, conversationHistory) {
    console.log("[academic] decideAndStore called, text:", text?.substring(0, 80));
    const raw = await extractAcademicTopics(sessionId, text, conversationHistory);
    if (!raw) { console.warn("[academic] extraction returned null"); return null; }

    storedRaw = raw;
    console.log("[academic] extraction raw:", JSON.stringify(raw));

    // --- autoPickedSubject ---
    const firstSubject = arr(raw.subjects)[0];
    autoPickedSubject = normalizeSubject(firstSubject);
    console.log("[academic] firstSubject:", firstSubject, "→ normalized:", autoPickedSubject);

    // --- autoPickedTopics (most-specific non-empty list) ---
    autoPickedTopics = null;
    if (autoPickedSubject) {
      const sub  = arr(raw.sub_concepts);
      const con  = arr(raw.concepts);
      const ch   = arr(raw.chapters);
      if (sub.length)       autoPickedTopics = sub;
      else if (con.length)  autoPickedTopics = con;
      else if (ch.length)   autoPickedTopics = ch;
    }
    console.log("[academic] autoPickedTopics:", autoPickedTopics);

    // persist to session backend
    try {
      await postJSON(`/api/session/${sessionId}/academic-topics`, {
        result: { raw: storedRaw, autoPickedSubject, autoPickedTopics },
      });
    } catch (_) { /* best effort */ }

    return { raw: storedRaw, autoPickedSubject, autoPickedTopics };
  }

  /* ── 3. reset (on retake) ──────────────────────────────────────────────── */
  async function resetAcademicTopics(sessionId) {
    storedRaw = null;
    autoPickedSubject = null;
    autoPickedTopics = null;
    selectedSubject = null;
    selectedChapters = [];
    selectedConcepts = [];
    try { await deleteJSON(`/api/session/${sessionId}/academic-topics`); } catch (_) {}
  }

  /* ══════════════════════════════════════════════════════════════════════════
     UI  —  Subject → Chapter → Concept local-catalog selector
     ══════════════════════════════════════════════════════════════════════════ */

  /* ── selection summary bar ─────────────────────────────────────────────── */
  function ensureSummaryBar() {
    let bar = document.getElementById("selectionSummary");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "selectionSummary";
      bar.className = "selection-summary-bar";
      const card = document.querySelector("#stageTopicSelection .topic-card");
      if (card) {
        const opts = document.getElementById("topicOptions");
        if (opts) card.insertBefore(bar, opts);
        else card.appendChild(bar);
      }
    }
    refreshSummaryBar(bar);
  }

  function refreshSummaryBar(bar) {
    bar = bar || document.getElementById("selectionSummary");
    if (!bar) return;
    const cc = selectedChapters.length, tc = selectedConcepts.length;
    if (cc === 0) {
      bar.innerHTML = '<span class="summary-empty">No items selected yet</span>';
    } else {
      bar.innerHTML = `
        <div class="summary-pill"><span class="pill-label">Chapters</span><span class="pill-value">${cc}</span></div>
        <div class="summary-pill highlight"><span class="pill-label">Concepts</span><span class="pill-value">${tc}</span></div>`;
    }
  }

  /* ── resolve hint → exact catalog key ────────────────────────────────── */
  function resolveToCatalogKey(hint) {
    if (!hint || !fullCatalog) return null;
    // exact match first
    if (fullCatalog[hint]) return hint;
    // case-insensitive match
    const lower = hint.toLowerCase();
    const match = Object.keys(fullCatalog).find(k => k.toLowerCase() === lower);
    if (match) return match;
    // normalize then match
    const normalized = normalizeSubject(hint);
    if (normalized && fullCatalog[normalized]) return normalized;
    // prefix match on catalog keys
    return Object.keys(fullCatalog).find(k => k.toLowerCase().startsWith(lower)) || null;
  }

  /* ── STAGE 1 : subject selection ───────────────────────────────────────── */
  async function initializeSubjectSelection(sessionId, hintSubject) {
    try {
      await initCatalog();

      // Resolve hintSubject to an actual catalog key
      if (hintSubject) {
        const resolved = resolveToCatalogKey(hintSubject);
        console.log("[academic] hintSubject:", hintSubject, "→ resolved:", resolved);
        if (resolved) selectedSubject = resolved;
      }
      if (!selectedSubject) selectedSubject = null;

      const wrap = document.getElementById("subjectOptions");
      const btn  = document.getElementById("btnSubjectNext");
      if (!wrap || !fullCatalog) {
        console.warn("[academic] subjectOptions or catalog missing");
        return;
      }

      wrap.innerHTML = "";
      Object.keys(fullCatalog).forEach(sub => {
        const active = selectedSubject === sub;
        const badge  = active && selectedConcepts.length
          ? `<span class="subject-selection-badge">${selectedConcepts.length} selected</span>` : "";
        const label = document.createElement("label");
        label.className = "subject-option" + (active ? " active" : "");
        label.innerHTML = `
          <input type="radio" name="subject" value="${sub}" ${active ? "checked" : ""}/>
          <span class="subject-radio"></span>
          <div class="subject-info-row">
            <span class="subject-name">${sub}</span>${badge}
          </div>`;
        label.querySelector("input").addEventListener("change", e => {
          const prev = selectedSubject;
          selectedSubject = e.target.value;
          if (prev !== selectedSubject) { selectedChapters = []; selectedConcepts = []; }
          if (btn) btn.disabled = false;
          wrap.querySelectorAll(".subject-option").forEach(o =>
            o.classList.toggle("active", o.querySelector("input").value === selectedSubject));
        });
        wrap.appendChild(label);
      });

      if (btn) {
        btn.disabled = !selectedSubject;
        btn.onclick = () => {
          console.log("[academic] Continue button clicked. selectedSubject:", selectedSubject, "sessionId:", sessionId);
          if (selectedSubject) {
            console.log("[academic] Calling goChapters...");
            goChapters(sessionId);
          } else {
            console.warn("[academic] No subject selected, button should be disabled");
          }
        };
      } else {
        console.warn("[academic] btnSubjectNext not found!");
      }

      console.log("[academic] Subject selection initialized. selectedSubject:", selectedSubject);
    } catch (err) {
      console.error("initializeSubjectSelection:", err);
    }
  }

  /* ── STAGE 2 : chapter selection ───────────────────────────────────────── */
  async function goChapters(sessionId) {
    console.log("[academic] goChapters called with sessionId:", sessionId);
    try {
      const show = window.__stressApp?.showStage;
      console.log("[academic] showStage function:", typeof show);
      if (show) {
        console.log("[academic] Showing topicSelection stage...");
        show("topicSelection");
      } else {
        console.error("[academic] showStage not available!");
      }

      const h2   = document.querySelector("#stageTopicSelection h2");
      const eye  = document.querySelector("#stageTopicSelection .eyebrow");
      const hint = document.getElementById("topicHint");
      if (h2)   h2.textContent   = "Select Chapters";
      if (eye)  eye.textContent  = "Step 2 · Chapters";
      if (hint) hint.textContent = "Pick chapters — their concepts auto-select.";

      ensureSummaryBar();
      await renderChapters(sessionId);
    } catch (e) {
      console.error("goChapters:", e);
      const hint = document.getElementById("topicHint");
      if (hint) hint.textContent = "Error: " + e.message;
    }
  }

  async function renderChapters(sessionId) {
    const box = document.getElementById("topicOptions");
    if (!box) return;
    box.innerHTML = "";

    if (!fullCatalog) await initCatalog();

    // robust match
    if (!selectedSubject || !fullCatalog[selectedSubject]) {
      const keys = Object.keys(fullCatalog || {});
      const m = keys.find(k => k.toLowerCase() === (selectedSubject || "").toLowerCase());
      selectedSubject = m || keys[0] || null;
    }
    if (!fullCatalog || !selectedSubject || !fullCatalog[selectedSubject]) {
      box.innerHTML = '<div class="topic-empty">No chapters found.</div>';
      return;
    }

    Object.keys(fullCatalog[selectedSubject]).forEach(ch => {
      const checked = selectedChapters.includes(ch);
      const lbl = document.createElement("label");
      lbl.className = "topic-option" + (checked ? " selected" : "");
      lbl.innerHTML = `
        <input type="checkbox" value="${encodeURIComponent(ch)}" ${checked ? "checked" : ""}/>
        <span class="topic-checkbox"></span>
        <span class="topic-name">${ch}</span>`;

      lbl.querySelector("input").addEventListener("change", function () {
        if (this.checked) {
          if (!selectedChapters.includes(ch)) selectedChapters.push(ch);
          lbl.classList.add("selected");
          (fullCatalog[selectedSubject][ch] || []).forEach(c => {
            if (!selectedConcepts.some(x => x.chapter === ch && x.concept === c))
              selectedConcepts.push({ chapter: ch, concept: c });
          });
        } else {
          selectedChapters = selectedChapters.filter(x => x !== ch);
          lbl.classList.remove("selected");
          selectedConcepts = selectedConcepts.filter(x => x.chapter !== ch);
        }
        refreshSummaryBar();
        const nb = document.getElementById("btnTopicNext");
        if (nb) nb.disabled = selectedChapters.length === 0;
      });
      box.appendChild(lbl);
    });

    const next = document.getElementById("btnTopicNext");
    const back = document.getElementById("btnTopicBack");
    if (next) {
      next.textContent = "Next: Refine Concepts";
      next.disabled = selectedChapters.length === 0;
      next.onclick = () => goConcepts(sessionId);
    }
    if (back) {
      back.onclick = () => {
        const show = window.__stressApp?.showStage;
        if (show) show("subjectSelection");
        initializeSubjectSelection(sessionId, selectedSubject);
      };
    }
    refreshSummaryBar();
  }

  /* ── STAGE 3 : concept selection ───────────────────────────────────────── */
  function goConcepts(sessionId) {
    const h2  = document.querySelector("#stageTopicSelection h2");
    const eye = document.querySelector("#stageTopicSelection .eyebrow");
    if (h2)  h2.textContent  = "Select Concepts";
    if (eye) eye.textContent = "Step 3 · Concepts";
    renderConcepts(sessionId);
  }

  function renderConcepts(sessionId) {
    const box = document.getElementById("topicOptions");
    if (!box) return;
    box.innerHTML = "";

    selectedChapters.forEach(ch => {
      const concepts = fullCatalog[selectedSubject][ch] || [];
      if (!concepts.length) return;

      const hdr = document.createElement("div");
      hdr.className = "topic-section-label";
      hdr.textContent = ch;
      box.appendChild(hdr);

      concepts.forEach(con => {
        const checked = selectedConcepts.some(x => x.chapter === ch && x.concept === con);
        const lbl = document.createElement("label");
        lbl.className = "topic-option concept-option" + (checked ? " selected" : "");
        lbl.style.marginLeft = "1.5rem";
        lbl.innerHTML = `
          <input type="checkbox" ${checked ? "checked" : ""}/>
          <span class="topic-checkbox"></span>
          <span class="topic-name">${con}</span>`;

        lbl.querySelector("input").addEventListener("change", function () {
          if (this.checked) {
            selectedConcepts.push({ chapter: ch, concept: con });
            lbl.classList.add("selected");
          } else {
            selectedConcepts = selectedConcepts.filter(x => !(x.chapter === ch && x.concept === con));
            lbl.classList.remove("selected");
          }
          refreshSummaryBar();
          const nb = document.getElementById("btnTopicNext");
          if (nb) nb.disabled = selectedConcepts.length === 0;
        });
        box.appendChild(lbl);
      });
    });

    const next = document.getElementById("btnTopicNext");
    const back = document.getElementById("btnTopicBack");
    if (next) {
      next.textContent = "Start Practice";
      next.disabled = selectedConcepts.length === 0;
      next.onclick = () => commitAndGo(sessionId);
    }
    if (back) back.onclick = () => renderChapters(sessionId);
    refreshSummaryBar();
  }

  /* ── commit selection → start test ──────────────────────────────────────── */
  async function commitAndGo(sessionId) {
    try {
      // Send only chapter names as topics for question filtering
      const topics = selectedChapters;
      await postJSON(`/api/session/${sessionId}/meta`, {
        selected_subject: selectedSubject,
        selected_topics: topics,
        selected_chapters: selectedChapters,
        selected_concepts_raw: selectedConcepts,
      });

      // Store meta so loadTestQuestions skips the /debug roundtrip
      if (window.__stressApp?.startQuestionPrefetch) {
        window.__stressApp.startQuestionPrefetch(selectedSubject, selectedChapters);
      }

      // Store test parameters for after fullscreen
      if (window.__stressApp?.setPendingTestStart) {
        window.__stressApp.setPendingTestStart({
          autoSubject: selectedSubject,
          autoTopics: topics
        });
      }

      // Show fullscreen requirement stage
      const show = window.__stressApp?.showStage;
      if (show) show("fullscreen");

    } catch (e) {
      console.error("commitAndGo:", e);
      const hint = document.getElementById("topicHint");
      if (hint) hint.textContent = "Save failed — " + e.message;
    }
  }

  /* ── compat shim for old app.js call ───────────────────────────────────── */
  async function loadTopicsForSubject(subject, sessionId) {
    await initCatalog();
    selectedSubject = normalizeSubject(subject) || subject;
    // map to catalog key
    if (fullCatalog && !fullCatalog[selectedSubject]) {
      const keys = Object.keys(fullCatalog);
      const m = keys.find(k => k.toLowerCase() === (selectedSubject || "").toLowerCase());
      if (m) selectedSubject = m;
      else selectedSubject = keys[0];
    }
    await goChapters(sessionId);
  }

  /* ── public API ────────────────────────────────────────────────────────── */
  window.academicTopics = {
    extractAcademicTopics,
    decideAndStore,
    resetAcademicTopics,
    initializeSubjectSelection,
    loadTopicsForSubject,
    selectedSubject:  () => selectedSubject,
    selectedChapters: () => selectedChapters,
    selectedConcepts: () => selectedConcepts,
  };
})();
