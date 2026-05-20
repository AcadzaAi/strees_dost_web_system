// DOM helpers --------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const stageEls = {
  name: $("stageName"),
  intro: $("stageIntro"),
  loading: $("stageLoading"),
  qa: $("stageQA"),
  subjectSelection: $("stageSubjectSelection"),
  topicSelection: $("stageTopicSelection"),
  devil: $("stageDevil"),
  fullscreen: $("stageFullscreen"),
  popups: $("stagePopups"),
  results: $("stageResults"),
};

const logBox = $("logBox");
const popupConsole = null;
const popupOverlay = null;
const popupQueue = [];
let popupActive = false;
let popupTimer = null;
let popupSuppressionTimer = null;
const recentPopups = new Set();

const loadingTitleEl = $("loadingTitle");
const loadingSubtitleEl = $("loadingSubtitle");
const loadingPhaseEl = $("loadingPhase");
const loadingNoteEl = $("loadingNote");
const loadingEchoEl = $("loadingEcho");
const nameHintEl = $("nameHint");
const introHintEl = $("introHint");
const storyPromptEl = $("storyPrompt");
const hintBox = $("hintBox");
const popupSummary = null;

// Academic topics elements
const subjectOptions = $("subjectOptions");
const topicOptions = $("topicOptions");
const subjectHint = $("subjectHint");
const topicHint = $("topicHint");
const btnSubjectNext = $("btnSubjectNext");
const btnTopicNext = $("btnTopicNext");
const btnTopicBack = $("btnTopicBack");

const hudPanel = $("hudPanel");
const hudToggle = $("hudToggle");
const btnCloseHud = $("btnCloseHud");

const btnStart = $("btnStart");
const btnNameNext = $("btnNameNext");
const btnRecord = $("btnRecord");
const btnAnswer = $("btnAnswer");
const btnSkip = $("btnSkip");
const btnReset = $("btnReset");
const btnRestart = $("btnRestart");
const btnAcceptChallenge = $("btnAcceptChallenge");
const userNameInput = $("userName");
const btnLogout = $("btnLogout");
const userChip = $("userChip");
const hudUserLine = $("hudUserLine");

const answerInput = $("answerInput");
const questionStem = $("questionStem");
const questionOptions = $("questionOptions");
const testCard = $("testCard");
const questionPanel = questionStem?.closest(".question-panel") || null;
const questionBody = questionPanel?.closest(".question-body") || null;
const questionCounter = $("questionCounter");
const questionSubject = $("questionSubject");
const questionTypeSelect = $("questionTypeSelect");
const questionProgress = $("questionProgress");
const mutateBadge = $("mutateBadge");
const integerPanel = $("integerPanel");
const integerInput = $("integerInput");
const btnClearInteger = $("btnClearInteger");
const btnBackspace = $("btnBackspace");
const scoreMeta = $("scoreMeta");
const testHint = $("testHint");
const btnPrevQuestion = $("btnPrevQuestion");
const btnNextQuestion = $("btnNextQuestion");
const btnReloadQuestions = $("btnReloadQuestions");
const btnSubmitQuestion = $("btnSubmitQuestion");
const btnFinishTest = $("btnFinishTest");
const btnReportError = $("btnReportError");
const btnLifeline = $("btnLifeline");
const btnShowSolution = $("btnShowSolution");
const btnSaveQuestion = $("btnSaveQuestion");
const btnSaveQuestionSubject = $("btnSaveQuestionSubject");
const btnSaveQuestionHeader = $("btnSaveQuestionHeader");
const btnZoomQuestion = $("btnZoomQuestion");
const solutionModal = $("solutionModal");
const solutionAnswerLine = $("solutionAnswerLine");
const solutionContent = $("solutionContent");
const btnCloseSolution = $("btnCloseSolution");
const devilTitle = $("devilTitle");
const devilIntro = $("devilIntro");
const devilProblems = $("devilProblems");
const devilDesign = $("devilDesign");
const devilBlueprint = $("devilBlueprint");
const devilChallengeLine = $("devilChallengeLine");
const devilHint = $("devilHint");

// State --------------------------------------------------------------------
let sessionId = null;
let currentDomain = null;
let currentSlot = null;
let socket = null;
let socketInitialized = false;
let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let recordedAudioBlob = null;
let recordingMimeType = "audio/webm";
let testQuestions = [];
let testQuestionIndex = 0;
let selectedOptions = {};
let answeredMap = {};
let pendingTriggerTimeouts = []; // Store pending trigger timeouts to cancel when switching questions
let mutationTimers = [];
let mutationPaused = false;
let isLoadingTestBank = false;
let integerKeypadListenerAttached = false;
let suggestTimer = null;
let loadingTicker = null;
let loadingFrameIndex = 0;
let lastAnswerEcho = "";
let sessionInitialQuery = "";
let questionWarningCopyCache = new Map();
let questionWarningCopyPromises = new Map();
let solutionModalOpen = false;
let pendingAdvanceAfterSubmit = false;
let questionTriggerPlan = null; // Stores trigger plan from backend
const LOCAL_NEW_USER_TRIGGER_NAMES = [
  "TORCHLIGHT_SPOTLIGHT",
  "HARD_FOG",
  "SCREEN_FLIP",
  "ACCURACY_TEST",
  "READING_TEST",
  "HARD_PEER_DOUBT",
  "BILLIARD_BALL",
];
const SOLUTION_GRACE_MS = 1400;

// Cancel all pending trigger timeouts when switching questions
function cancelPendingTriggers() {
  console.log('[cancelPendingTriggers] Cancelling', pendingTriggerTimeouts.length, 'pending triggers');
  pendingTriggerTimeouts.forEach(timeoutId => clearTimeout(timeoutId));
  pendingTriggerTimeouts = [];
  // Also clean up any persistent Q3 flip if still active
  const shell = document.querySelector(".app-shell");
  if (shell && shell.dataset.psyqFlipActive === "1") {
    shell._psyqFlipCleanup?.();
  }
}
const disableStressMode = false;
const stressDebug = true;
const manualStressTriggerMode = false;
const enableDevTriggerPanel =
  manualStressTriggerMode &&
  (window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1");

const DEV_FALLBACK_QUESTIONS = [
  {
    question_id: "dev-fallback-1",
    question_type: "scq",
    subject: "Mathematics",
    chapter: "Algebra",
    difficulty: "Easy",
    level: "EASY",
    question_html: "<p>If 3x + 6 = 21, the value of x is:</p>",
    question_images: [],
    options: [
      { label: "A", text: "3" },
      { label: "B", text: "4" },
      { label: "C", text: "5" },
      { label: "D", text: "6" },
    ],
    correct_answer: "C",
  },
  {
    question_id: "dev-fallback-2",
    question_type: "scq",
    subject: "Physics",
    chapter: "Laws of Motion",
    difficulty: "Easy",
    level: "EASY",
    question_html: "<p>The SI unit of force is:</p>",
    question_images: [],
    options: [
      { label: "A", text: "Newton" },
      { label: "B", text: "Joule" },
      { label: "C", text: "Watt" },
      { label: "D", text: "Pascal" },
    ],
    correct_answer: "A",
  },
  {
    question_id: "dev-fallback-3",
    question_type: "scq",
    subject: "Mathematics",
    chapter: "Advanced Calculus",
    difficulty: "Hard",
    level: "HARD",
    question_html: "<p><strong>HARD QUESTION:</strong> If f(x) = x³ - 6x² + 11x - 6, find all real roots:</p>",
    question_images: [],
    options: [
      { label: "A", text: "x = 1, 2, 3" },
      { label: "B", text: "x = 0, 1, 2" },
      { label: "C", text: "x = -1, 2, 3" },
      { label: "D", text: "x = 1, 3, 5" },
    ],
    correct_answer: "A",
  },
  {
    question_id: "dev-fallback-4",
    question_type: "scq",
    subject: "Mathematics",
    chapter: "Trigonometry",
    difficulty: "Medium",
    level: "MEDIUM",
    question_html: "<p>sin²θ + cos²θ is equal to:</p>",
    question_images: [],
    options: [
      { label: "A", text: "0" },
      { label: "B", text: "1" },
      { label: "C", text: "2" },
      { label: "D", text: "Depends on θ" },
    ],
    correct_answer: "B",
  },
  {
    question_id: "dev-fallback-5",
    question_type: "scq",
    subject: "Physics",
    chapter: "Kinematics",
    difficulty: "Medium",
    level: "MEDIUM",
    question_html: "<p>A body starts from rest with acceleration 2 m/s². Distance in 3 s is:</p>",
    question_images: [],
    options: [
      { label: "A", text: "3 m" },
      { label: "B", text: "6 m" },
      { label: "C", text: "9 m" },
      { label: "D", text: "12 m" },
    ],
    correct_answer: "C",
  },
  {
    question_id: "dev-fallback-6",
    question_type: "scq",
    subject: "Physics",
    chapter: "Quantum Mechanics",
    difficulty: "Hard",
    level: "HARD",
    question_html: "<p><strong>HARD QUESTION:</strong> In the photoelectric effect, if the frequency of incident light is doubled while keeping intensity constant, the maximum kinetic energy of ejected electrons:</p>",
    question_images: [],
    options: [
      { label: "A", text: "Remains the same" },
      { label: "B", text: "Doubles" },
      { label: "C", text: "More than doubles" },
      { label: "D", text: "Becomes half" },
    ],
    correct_answer: "C",
  },
  {
    question_id: "dev-fallback-7",
    question_type: "scq",
    subject: "Mathematics",
    chapter: "Coordinate Geometry",
    difficulty: "Medium",
    level: "MEDIUM",
    question_html: "<p>Distance between points (0,0) and (3,4) is:</p>",
    question_images: [],
    options: [
      { label: "A", text: "4" },
      { label: "B", text: "5" },
      { label: "C", text: "6" },
      { label: "D", text: "7" },
    ],
    correct_answer: "B",
  },
];

const CLIENT_FALLBACK_QUESTIONS = [
  {
    question_id: "client-local-q-1",
    question_type: "scq",
    subject: "Physics",
    difficulty: "Easy",
    question_html: "<p>A body accelerates at 2 m/s^2 for 5 s from rest. Final velocity?</p>",
    options: [
      { label: "A", text: "5 m/s" },
      { label: "B", text: "10 m/s" },
      { label: "C", text: "12 m/s" },
      { label: "D", text: "15 m/s" },
    ],
    correct_answer: "B",
  },
  {
    question_id: "client-local-q-2",
    question_type: "scq",
    subject: "Chemistry",
    difficulty: "Easy",
    question_html: "<p>How many moles are present in 22 g of CO2 (M=44 g/mol)?</p>",
    options: [
      { label: "A", text: "0.25 mol" },
      { label: "B", text: "0.5 mol" },
      { label: "C", text: "1 mol" },
      { label: "D", text: "2 mol" },
    ],
    correct_answer: "B",
  },
  {
    question_id: "client-local-q-3",
    question_type: "scq",
    subject: "Math",
    difficulty: "Easy",
    question_html: "<p>For x^2 - 5x + 6 = 0, sum of roots equals?</p>",
    options: [
      { label: "A", text: "2" },
      { label: "B", text: "3" },
      { label: "C", text: "5" },
      { label: "D", text: "6" },
    ],
    correct_answer: "C",
  },
  {
    question_id: "client-local-q-4",
    question_type: "integer",
    subject: "Physics",
    difficulty: "Medium",
    question_html: "<p>Force 10 N moves object 3 m in same direction. Work (J)?</p>",
    integer_answer: 30,
  },
  {
    question_id: "client-local-q-5",
    question_type: "scq",
    subject: "Biology",
    difficulty: "Easy",
    question_html: "<p>Which organelle is called the powerhouse of the cell?</p>",
    options: [
      { label: "A", text: "Nucleus" },
      { label: "B", text: "Golgi body" },
      { label: "C", text: "Mitochondria" },
      { label: "D", text: "Ribosome" },
    ],
    correct_answer: "C",
  },
  {
    question_id: "client-local-q-6",
    question_type: "scq",
    subject: "Math",
    difficulty: "Easy",
    question_html: "<p>sin 30 degrees equals:</p>",
    options: [
      { label: "A", text: "1/2" },
      { label: "B", text: "sqrt(3)/2" },
      { label: "C", text: "0" },
      { label: "D", text: "1" },
    ],
    correct_answer: "A",
  },
  {
    question_id: "client-local-q-7",
    question_type: "integer",
    subject: "Chemistry",
    difficulty: "Easy",
    question_html: "<p>Electrons in a neutral oxygen atom?</p>",
    integer_answer: 8,
  },
];

async function openDevFallbackQuestionsDirect() {
  try {
    const cloned = DEV_FALLBACK_QUESTIONS.map((q, idx) => ({
      ...q,
      question_index: idx + 1,
      options: Array.isArray(q.options) ? q.options.map((opt) => ({ ...opt })) : [],
    }));
    testQuestions = cloned;
    testQuestionIndex = 0;
    selectedOptions = {};
    answeredMap = {};
    
    try {
      clearMutationTimers();
    } catch (err) {
      console.error('[openDevFallbackQuestionsDirect] clearMutationTimers failed:', err);
    }
    
    // Fetch trigger plan for fallback questions too (non-blocking)
    try {
      await fetchQuestionTriggerPlan();
    } catch (err) {
      console.error('[openDevFallbackQuestionsDirect] Failed to fetch trigger plan:', err);
      // Continue anyway - triggers will use default behavior
    }
    
    setTestHint("Dev mode: Loaded local fallback questions directly.");
    renderTestQuestion();
    showStage("popups");
  } catch (err) {
    console.error('[openDevFallbackQuestionsDirect] Critical error:', err);
    alert('Failed to load fallback questions: ' + err.message);
  }
}

// Utility ------------------------------------------------------------------
function log(...args) {
  if (!logBox) return;
  const line = args
    .map((a) => (typeof a === "string" ? a : JSON.stringify(a)))
    .join(" ");
  logBox.textContent = (logBox.textContent + line + "\n").slice(-15000);
  logBox.scrollTop = logBox.scrollHeight;
}

async function getJSON(url) {
  const res = await fetch(url, { method: "GET", headers: { "Content-Type": "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`);
  return data;
}

async function postJSON(url, body, options) {
  const timeoutMs = Number(options?.timeoutMs || 0);
  const controller =
    timeoutMs > 0 && typeof AbortController !== "undefined"
      ? new AbortController()
      : null;
  let timeoutId = null;
  if (controller && timeoutMs > 0) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      signal: controller?.signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error(`Request timeout after ${timeoutMs}ms`);
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
}

async function deleteJSON(url) {
  const res = await fetch(url, { method: "DELETE", headers: { "Content-Type": "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
}

async function postFormData(url, formData) {
  const res = await fetch(url, {
    method: "POST",
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
}

function showStage(name, message) {
  setMutationPaused(false);
  Object.values(stageEls).forEach((el) => el?.classList.remove("active"));
  const stage = stageEls[name];
  if (stage) stage.classList.add("active");
  if (name === "loading") {
    startLoadingLoop(message);
  } else {
    stopLoadingLoop();
  }
  
  // Notify StressTriggers about stage change
  if (typeof StressTriggers !== 'undefined' && StressTriggers.setStage) {
    StressTriggers.setStage(name);
  }
  
  // Keep viewport at top when switching stages so users see loaders/questions without scrolling
  try {
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    window.scrollTo(0, 0);
  }
}

function setLoadingMessage(message) {
  if (loadingNoteEl) {
    loadingNoteEl.textContent = message || "This takes a moment - your plan is being crafted";
  }
}

const LOADING_FRAMES = [
  {
    phase: "READING",
    title: "Reading what you shared",
    subtitle: "Picking up every signal",
  },
  {
    phase: "MAPPING",
    title: "Mapping your focus pattern",
    subtitle: "Connecting the dots",
  },
  {
    phase: "MATCHING",
    title: "Finding what works for you",
    subtitle: "Pulling from what helps",
  },
  {
    phase: "CRAFTING",
    title: "Shaping your session",
    subtitle: "Almost ready",
  },
];

function startLoadingLoop(message) {
  stopLoadingLoop();
  loadingFrameIndex = 0;
  applyLoadingFrame(loadingFrameIndex);
  setLoadingMessage(message);
  setLoadingEcho();
  loadingTicker = setInterval(() => {
    loadingFrameIndex = (loadingFrameIndex + 1) % LOADING_FRAMES.length;
    applyLoadingFrame(loadingFrameIndex);
  }, 1800);
}

function stopLoadingLoop() {
  if (loadingTicker) {
    clearInterval(loadingTicker);
    loadingTicker = null;
  }
}

function applyLoadingFrame(index) {
  const frame = LOADING_FRAMES[index];
  if (!frame) return;
  if (loadingPhaseEl) loadingPhaseEl.textContent = frame.phase;
  if (loadingTitleEl) loadingTitleEl.textContent = capitalizeSentence(frame.title);
  if (loadingSubtitleEl) loadingSubtitleEl.textContent = capitalizeSentence(frame.subtitle);
}

function capitalizeSentence(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function setLoadingEcho() {
  if (!loadingEchoEl) return;
  const span = loadingEchoEl.querySelector("span");
  if (!span) return;
  const text = getLatestUserStory();
  span.textContent = text || "...";
}

function getLatestUserStory() {
  const initialText = $("initialText")?.value || "";
  const answerText = $("answerInput")?.value || "";
  const combined = (lastAnswerEcho || answerText || initialText).trim();
  if (!combined) return "";
  return combined.length > 120 ? `${combined.slice(0, 117)}...` : combined;
}

function setHint(text) {
  if (hintBox) hintBox.textContent = text || "";
}

function setIntroHint(text) {
  if (!introHintEl) return;
  introHintEl.textContent = text || "";
  if (text) {
    stageEls.intro?.classList.add("shake");
    setTimeout(() => stageEls.intro?.classList.remove("shake"), 400);
  }
}

function setNameHint(text) {
  if (!nameHintEl) return;
  nameHintEl.textContent = text || "";
  if (text) {
    stageEls.name?.classList.add("shake");
    setTimeout(() => stageEls.name?.classList.remove("shake"), 400);
  }
}

function setStoryPrompt(name) {
  if (!storyPromptEl) return;
  const cleanName = (name || "").trim();
  if (!cleanName) {
    storyPromptEl.textContent = "Hey there! 👋";
    return;
  }
  const normalized = toTitleCase(cleanName);
  storyPromptEl.textContent = `Hey ${normalized}! 👋`;
}

function toTitleCase(value) {
  return String(value)
    .toLowerCase()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function setRecordButtonState() {
  if (!btnRecord) return;
  if (mediaRecorder && mediaRecorder.state === "recording") {
    btnRecord.textContent = "■";
    btnRecord.classList.remove("ghost");
    btnRecord.classList.add("primary");
    return;
  }
  btnRecord.textContent = recordedAudioBlob ? "↺" : "🎙";
  btnRecord.classList.remove("primary");
  btnRecord.classList.add("ghost");
}

function setSessionUI(id, domains) {
  sessionId = id;
  window.currentSessionId = id || null;
  $("sessionId").textContent = id || "—";
  $("sessionStatus").textContent = id ? `session: ${id.slice(0, 8)}…` : "session: none";
  $("activeDomains").textContent = domains && domains.length ? domains.join(", ") : "—";
}

function syncUserUI() {
  const u = window.StressDostAuth?.getUser?.();
  console.log('[syncUserUI] User data:', u);
  if (userChip) {
    userChip.textContent = u ? `${u.display_name} · ${String(u.user_id).slice(0, 8)}…` : "";
    userChip.style.display = u ? "inline-flex" : "none";
  }
  if (hudUserLine) {
    if (!u) hudUserLine.textContent = "—";
    else hudUserLine.textContent = `${u.display_name} (${u.user_id})`;
  }
  // Set story prompt with user's name
  if (u && u.display_name) {
    setStoryPrompt(u.display_name);
  }
  // Update session counter
  const sessionCounter = document.getElementById('sessionCounter');
  console.log('[syncUserUI] Session counter element:', sessionCounter);
  if (sessionCounter && u) {
    const completedSessions = u.completed_sessions || 0;
    console.log('[syncUserUI] Completed sessions:', completedSessions);
    sessionCounter.textContent = `Sessions: ${completedSessions}`;
    sessionCounter.style.setProperty('display', 'inline-block', 'important');
  } else if (sessionCounter) {
    sessionCounter.style.display = 'none';
  }
}

function clientUserPayload() {
  const u = window.StressDostAuth?.getUser?.();
  if (!u) return null;
  const out = { user_id: u.user_id, display_name: u.display_name };
  if (u.mood) out.mood = u.mood;
  return out;
}

function updateScoreMeta() {
  const totalAnswered = Object.keys(answeredMap).length;
  const correct = Object.values(answeredMap).filter((v) => v?.correct).length;
  const totalQuestions = testQuestions.length || totalAnswered;
  if (scoreMeta) scoreMeta.textContent = `Score: ${correct}/${totalQuestions || 0}`;
}

function setQuestionUI(data) {
  currentDomain = data.domain || null;
  currentSlot = data.slot || null;
  const totalAsked = Number(
    data?.meta?.total_questions_asked ||
    data?.meta?.question_index ||
    0
  );
  const totalExpected = Number(
    data?.meta?.total_questions ||
    data?.meta?.total_questions_expected ||
    data?.meta?.total_followups ||
    data?.meta?.max_questions ||
    0
  );
  const currentIndex = totalAsked > 0 ? totalAsked : 1;
  const qaCount = $("qaCount");
  if (qaCount) {
    qaCount.textContent = totalExpected > 0 ? `${currentIndex}/${totalExpected}` : `${currentIndex}`;
  }
  const qaProgress = document.querySelector(".qa-progress span");
  if (qaProgress && totalExpected > 0) {
    const pct = Math.min(100, Math.max(0, (currentIndex / totalExpected) * 100));
    qaProgress.style.width = `${pct}%`;
  }

  const qMeta = $("qMeta");
  if (qMeta) {
    qMeta.innerHTML = '<span class="qa-emoji" aria-hidden="true">' +
      '<svg viewBox="0 0 64 64" focusable="false" aria-hidden="true">' +
      '<circle cx="32" cy="32" r="22" />' +
      '<circle cx="32" cy="32" r="8" />' +
      '<path d="M32 10 L44 22 L32 32" />' +
      '<path d="M54 32 L42 44 L32 32" />' +
      '<path d="M32 54 L20 42 L32 32" />' +
      '<path d="M10 32 L20 20 L32 32" />' +
      '<path d="M20 20 L44 22 L32 32" />' +
      '</svg></span><span>FOLLOW-UP QUESTION</span>';
  }
  $("questionText").textContent = data.question || "Your next question will bloom here.";

  // Replay the zoom-in/out entrance animation each time a new follow-up arrives.
  const qaCardEl = document.querySelector("#stageQA .qa-card");
  if (qaCardEl) {
    qaCardEl.classList.remove("qa-card-enter");
    void qaCardEl.offsetWidth;
    qaCardEl.classList.add("qa-card-enter");
  }

  if (btnSkip) {
    btnSkip.hidden = totalAsked < 3;
    btnSkip.disabled = false;
  }
  setHint(data.hint || "");
  answerInput.disabled = false;
  answerInput.focus();
  updateAnswerButtonState();
}

function resetFlow() {
  StressTriggers.onReset();
  // Reset academic topics (raw, autoPickedSubject, autoPickedTopics → null)
  if (sessionId) window.academicTopics?.resetAcademicTopics?.(sessionId);
  sessionId = null;
  currentDomain = null;
  currentSlot = null;
  sessionInitialQuery = "";
  questionWarningCopyCache = new Map();
  questionWarningCopyPromises = new Map();
  clearGhost();
  btnAnswer.disabled = true;
  btnAnswer.hidden = true;
  if (btnSkip) {
    btnSkip.hidden = true;
    btnSkip.disabled = false;
  }
  answerInput.value = "";
  $("initialText").value = "";
  recordedAudioBlob = null;
  recordingMimeType = "audio/webm";
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  mediaRecorder = null;
  audioChunks = [];
  setRecordButtonState();
  setHint("");
  setNameHint("");
  setIntroHint("");
  // Don't clear story prompt - it's set from user profile
  // setStoryPrompt("");
  // Reset test question panel
  testQuestions = [];
  testQuestionIndex = 0;
  selectedOptions = {};
  answeredMap = {};
  clearQuestionStem("Questions will appear here with options.");
  if (questionOptions) questionOptions.innerHTML = "";
  if (questionCounter) questionCounter.textContent = "Q. 1 of 1";
  if (questionSubject) questionSubject.textContent = "ID: —";
  if (questionTypeSelect) questionTypeSelect.options[0].textContent = "Math-Single Type";
  if (questionProgress) questionProgress.style.width = "0%";
  if (mutateBadge) mutateBadge.style.display = "none";
  if (integerPanel) integerPanel.style.display = "none";
  if (devilProblems) devilProblems.innerHTML = "";
  if (devilDesign) devilDesign.innerHTML = "";
  if (devilBlueprint) devilBlueprint.innerHTML = "";
  if (devilHint) devilHint.textContent = "";
  _lifelines = 3;
  updateScoreMeta();
  setTestHint("");
  if (popupSummary) {
    popupSummary.textContent = "We're releasing your personalized pulses now. Watch the center top.";
  }
  if (popupOverlay) popupOverlay.innerHTML = "";
  log("reset_flow");
  setSessionUI(null, null);
  showStage("intro");
}

function summarizeFollowupThemes(followups) {
  const text = (followups || []).map((f) => `${f.answer || ""} ${f.domain || ""} ${f.slot || ""}`).join(" ").toLowerCase();
  const out = [];
  if (/panic|anx|nerv|fear|scared/.test(text)) out.push("panic spikes under pressure");
  if (/procrast|delay|later|tomorrow|avoid/.test(text)) out.push("delay loops before action");
  if (/phone|instagram|youtube|reel|game|chat|social/.test(text)) out.push("digital distraction susceptibility");
  if (/compare|friend|rank|others|competition/.test(text)) out.push("comparison-triggered confidence dips");
  if (/time|late|schedule|rush|deadline/.test(text)) out.push("time-management stress");
  if (/sleep|tired|fatigue|exhaust/.test(text)) out.push("energy inconsistency across sessions");
  if (!out.length) out.push("decision hesitation in uncertain questions");
  return out.slice(0, 4);
}

async function buildDevilBriefPage(passedInitialText, passedHistory) {
  const followups = StressTriggers.getFollowupAnswers ? StressTriggers.getFollowupAnswers() : [];
  const user = window.StressDostAuth?.getUser?.();
  const userName = user?.display_name || "challenger";

  // Use passed initialText first, then fallback to lastAnswerEcho or textarea
  const initialText = passedInitialText || lastAnswerEcho || $("initialText")?.value || "";
  
  // Build followup context from conversation history if StressTriggers followups are empty
  let effectiveFollowups = followups;
  if (!effectiveFollowups.length && Array.isArray(passedHistory) && passedHistory.length) {
    effectiveFollowups = passedHistory
      .filter(h => h.role === "user" || h.answer)
      .map(h => ({
        answer: h.answer || h.content || "",
        domain: h.domain || "",
        slot: h.slot || "",
      }))
      .filter(f => f.answer.trim());
  }
  
  console.log("[buildDevilBriefPage] initialText:", initialText?.substring(0, 60), "followups:", effectiveFollowups.length);

  const planned = {
    trigger_count: 19,
    one_trigger_at_a_time: true,
    ai_driven: true,
    expected_question_count: testQuestions.length || 20,
  };

  let brief = null;
  try {
    brief = await postJSON("/api/triggers/devil-brief", {
      followup_answers: effectiveFollowups,
      initial_text: initialText,
      planned_test: planned,
    }, { timeoutMs: 15000 });
    console.log("[buildDevilBriefPage] Response source:", brief?.source, "core_issue:", brief?.core_issue);
    
    // If backend returned fallback, retry once
    if (brief?.source === "fallback") {
      console.warn("[buildDevilBriefPage] Got fallback response, retrying...");
      const retry = await postJSON("/api/triggers/devil-brief", {
        followup_answers: effectiveFollowups,
        initial_text: initialText,
        planned_test: planned,
      }, { timeoutMs: 15000 });
      if (retry?.source === "ai") {
        brief = retry;
        console.log("[buildDevilBriefPage] Retry succeeded with AI response");
      }
    }
  } catch (err) {
    console.warn("[buildDevilBriefPage] AI call failed:", err);
    brief = null;
  }

  const devilName = brief?.devil_name || "The Focus Breaker";
  const coreIssue = brief?.core_issue || "Unclear focus patterns need measurement";
  const problemPoints = Array.isArray(brief?.problem_points) && brief.problem_points.length
    ? brief.problem_points
    : ["Your attention baseline needs to be established", "Focus endurance under pressure is unknown"];
  const challengeLine = brief?.challenge_line || "Let's see what breaks your concentration first.";

  // Fill HTML
  if (devilTitle) devilTitle.textContent = devilName;
  if (devilIntro) devilIntro.textContent = `I've analyzed your patterns, ${userName}.`;
  if (devilChallengeLine) devilChallengeLine.textContent = challengeLine;

  const insightEl = document.getElementById("devilInsightSummary");
  if (insightEl) insightEl.textContent = coreIssue;

  // Show the "Specifically" section and fill problem points
  const insightSubEl = document.querySelector(".devil-insight-sub");
  if (insightSubEl) insightSubEl.style.display = "block";
  
  if (devilProblems) {
    devilProblems.style.display = "block";
    devilProblems.innerHTML = "";
    problemPoints.slice(0, 2).forEach((line) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="insight-icon">🔥</span> ${escapeHTML(line)}`;
      devilProblems.appendChild(li);
    });
  }

  // Remove warning line - keep it minimal
  const warningEl = document.getElementById("devilWarning");
  if (warningEl) warningEl.style.display = "none";

  // Clean up hidden panels
  if (devilDesign) devilDesign.innerHTML = "";
  if (devilBlueprint) devilBlueprint.innerHTML = "";
  if (devilHint) devilHint.textContent = "";
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setIntroHint("Your browser does not support mic recording.");
    return;
  }
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  recordedAudioBlob = null;
  const preferredMime =
    typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";
  mediaRecorder = preferredMime
    ? new MediaRecorder(mediaStream, { mimeType: preferredMime })
    : new MediaRecorder(mediaStream);
  recordingMimeType = mediaRecorder.mimeType || preferredMime || "audio/webm";

  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      audioChunks.push(event.data);
    }
  });

  mediaRecorder.addEventListener("stop", () => {
    recordedAudioBlob = audioChunks.length
      ? new Blob(audioChunks, { type: recordingMimeType })
      : null;
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }
    setRecordButtonState();
    if (recordedAudioBlob) {
      setIntroHint("Voice captured. Click Launch Session to transcribe and continue.");
    }
  });

  mediaRecorder.start();
  setIntroHint("Recording... click again to stop.");
  setRecordButtonState();
}

function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state !== "recording") return;
  mediaRecorder.stop();
}

function getAudioExtension() {
  if (recordingMimeType.includes("mp4") || recordingMimeType.includes("mpeg")) return "m4a";
  if (recordingMimeType.includes("ogg")) return "ogg";
  if (recordingMimeType.includes("wav")) return "wav";
  return "webm";
}

async function resolveInitialText() {
  const typed = $("initialText").value.trim();
  if (typed) return typed;
  if (!recordedAudioBlob) return "";

  setLoadingMessage("Transcribing your recording...");
  const formData = new FormData();
  formData.append("audio", recordedAudioBlob, `recording.${getAudioExtension()}`);
  const data = await postFormData("/session/transcribe", formData);
  const text = (data.text || "").trim();
  if (text) {
    $("initialText").value = text;
  }
  return text;
}

function clearMutationTimers() {
  mutationTimers.forEach((id) => clearTimeout(id));
  mutationTimers = [];
}

function setMutationPaused(paused) {
  const next = Boolean(paused);
  if (mutationPaused === next) return;
  mutationPaused = next;
  if (mutationPaused) {
    clearMutationTimers();
    log("mutation_paused", "popups_stage_active");
  } else {
    log("mutation_resumed", "popups_stage_inactive");
  }
}

function cloneClientFallbackQuestions() {
  return CLIENT_FALLBACK_QUESTIONS.map((q, idx) => ({
    ...q,
    question_index: idx + 1,
    options: Array.isArray(q.options) ? q.options.map((opt) => ({ ...opt })) : [],
  }));
}

// Stress trigger engine ----------------------------------------------------
const StressTriggers = (() => {
  if (disableStressMode) {
    const resolved = Promise.resolve();
    return {
      setStage: () => {},
      onReset: () => {},
      getFollowupAnswers: () => [],
      onQuestionLoaded: () => {},
      onOptionChange: () => {},
      onOptionClick: () => {},
      onOptionHover: () => {},
      onOptionPointerDown: () => {},
      onOptionPointerUp: () => {},
      beforeSubmitDelay: () => resolved,
      afterSubmit: () => {},
      noteAnswerOutcome: () => {},
      beginExamTimer: () => {},
      onPopupsEntered: () => {},
      requestFeedbackPulse: () => {},
      isScreenBusyForPopup: () => false,
      onQuestionRendered: () => {},
    };
  }

  const reducedMotion = Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const AI_TRIGGER_ENDPOINT = "/api/triggers/recommend";
  const AI_DECISION_MIN_GAP_MS = 700;
  const AI_DECISION_DEBOUNCE_MS = 320;
  const AI_DECISION_TIMEOUT_MS = 8000;
  const AI_DECISION_TIMEOUT_FAST_MS = 5000;
  const AI_DECISION_ERROR_BACKOFF_MS = 2200;
  const TRIGGER_COOLDOWN_FACTOR = 0.35;
  const MIN_COOLDOWN_MS = 1400;
  const FEEDBACK_MIN_INTERVAL_MS = 60000;
  const FEEDBACK_PROMPT_MAX_OPEN_MS = 18000;
  const SCREEN_QUIET_BREAK_MS = 1600;
  const STRESS_BUDGET_MAX = 100;
  const STRESS_BUDGET_MIN_COST = 8;
  const TRIGGER_COST_BY_INTENSITY = { low: 8, medium: 15, high: 25 };
  const active = new Map();
  const cooldownUntil = new Map();
  const activationCounts = new Map();
  const devButtons = new Map();
  let audioContext = null;
  const state = {
    stage: "name",
    examStartedAt: 0,
    examDurationMs: 900000,
    examTimerId: null,
    lifelines: 3,
    questionStartedAt: 0,
    currentQuestionId: "",
    questionDifficulty: "",
    lastInteractionAt: Date.now(),
    clickTimestamps: [],
    answerChangesByQuestion: {},
    lastAnswerLatencyMs: null,
    hoverIntentOnOption: false,
    hoverOptionEl: null,
    isSubmittingAnswer: false,
    lastTriggerName: null,
    lastPhantomMessageIndex: -1,
    lastConfidencePunchIndex: -1,
    lastMiragePunchIndex: -1,
    followupAnswers: [],
    wrongAnswersCount: 0,
    totalSubmissions: 0,
    correctStreak: 0,
    aiDecisionInFlight: false,
    lastAIDecisionAt: 0,
    aiBackoffUntil: 0,
    aiDebounceTimer: null,
    noActionStreak: 0,
    recentTriggerNames: [],
    recentTriggerOutcomes: [],
    queuedTriggerRequest: null,
    lastTriggerActivatedAt: 0,
    lastTriggerEndedAt: 0,
    audioPrimed: false,
    lastAnswerWasCorrect: null,
    stressBudget: STRESS_BUDGET_MAX,
    interactionHesitationMs: 0,
    interactionHesitationStartedAt: 0,
    pointerPressureSamples: [],
    deviceMovementIndex: 0,
    lastAgitationEventAt: 0,
    lastContextSwitchAt: 0,
    lastRapidTapEventAt: 0,
    interruptionLocks: {},
    feedbackLastShownAt: 0,
    feedbackPromptOpen: false,
    feedbackResponseHistory: [],
    feedbackDifficultyPreference: "medium",
    feedbackTopicPreference: "",
    lastFeedbackQuestionType: "",
    feedbackInterestReelTimer: null,
    feedbackInterestHardDeadlineTimer: null,
    feedbackInterestReelDeadlineAt: 0,
    screenQuietUntil: 0,
    newsReelHistory: [],
    lastNewsTopic: "",
    lastNewsImage: "",
    hardQuestionChallenge: null,
    hardQuestionPostSubmitDelayMs: 0,
    optionFeedbackActive: false,
    optionFeedbackQuestionId: "",
    optionFeedbackOverlay: null,
    optionFeedbackLastOption: "",
    // Q6 option feedback interception state
    optionFeedbackInterceptionEnabled: false,
    optionFeedbackInterceptionCount: 0,
    optionFeedbackMaxInterceptions: 2,
    q1PopupShownThisSession: false,
  };

  const FEEDBACK_PROMPT_LIBRARY = {
    stressed: [
      "How are you feeling right now under this pressure?",
      "Quick check: is the stress manageable or heavy right now?",
      "Before next question, how intense is the pressure for you?",
    ],
    anxious: [
      "How is your mind feeling right now: calm or overactive?",
      "Are you feeling clear, shaky, or stuck right now?",
      "Quick pulse: is anxiety low, medium, or high right now?",
    ],
    focused: [
      "You look steady. How do you feel right now?",
      "Quick check-in: still focused, or mentally drifting?",
      "How is your energy right now: stable or fading?",
    ],
    confident: [
      "Nice momentum. How are you feeling now?",
      "Quick pulse: confident, neutral, or unsure right now?",
      "How is your state right now after recent questions?",
    ],
  };

  const FEEDBACK_OPTIONS_BY_MOOD = {
    stressed: ["Stressed", "Overwhelmed", "Calm now", "Need a short pause"],
    anxious: ["Anxious", "Confused", "Okay", "Focused"],
    focused: ["Focused", "Slightly tired", "Distracted", "Confident"],
    confident: ["Confident", "Excited", "Calm", "Need challenge"],
  };

  const FEEDBACK_DIFFICULTY_OPTIONS = ["Easy", "Medium", "Hard"];
  const FEEDBACK_TOPIC_OPTIONS = ["Movies", "News", "Games", "Music", "Sports", "Technology", "Science", "Health", "Other"];

  const OPTION_FEEDBACK_LIBRARY = {
    A: {
      headline: "88% missed this exact question.",
      subhead: "JEE Main 2023 Shift 2 had the exact phrasing. Solution videos all converge on A.",
      coach: "Coaching tells you to memorize this type. It always reduces to A.",
    },
    B: {
      headline: "64% missed this exact question.",
      subhead: "64% of students who solved this got B.",
      coach: "Coaching teachers call this a 'second-read' question. Read it again.",
    },
    C: {
      headline: "79% missed this exact question.",
      subhead: "79% of students who solved this got B.",
      coach: "The data given is more than required. Extra info is the distractor.",
    },
    D: {
      headline: "77% missed this exact question.",
      subhead: "77% of FIITJEE Phase Test rankers chose B in this exact question.",
      coach: "The students who score above 99 percentile know this pattern cold.",
    },
  };

  const INTEREST_TOPIC_MAP = {
    movies: "movies",
    movie: "movies",
    news: "world",
    world: "world",
    games: "games",
    game: "games",
    gaming: "games",
    music: "music",
    sports: "sports",
    sport: "sports",
    technology: "technology",
    tech: "technology",
    science: "science",
    health: "health",
    other: "world",
  };

  function mapFeedbackTopicToReelTopic(value) {
    const key = String(value || "").trim().toLowerCase();
    if (!key) return "";
    return INTEREST_TOPIC_MAP[key] || "";
  }

  function applyFeedbackIntensityBias(baseIntensity) {
    const order = ["low", "medium", "high"];
    const current = String(baseIntensity || "medium").toLowerCase();
    const baseIdx = Math.max(0, order.indexOf(current));
    const pref = String(state.feedbackDifficultyPreference || "medium").toLowerCase();
    let delta = 0;
    if (pref === "hard") delta = 1;
    else if (pref === "easy") delta = -1;
    const nextIdx = Math.max(0, Math.min(order.length - 1, baseIdx + delta));
    return order[nextIdx];
  }

  function clearInterestReelSchedule() {
    if (state.feedbackInterestReelTimer) {
      clearTimeout(state.feedbackInterestReelTimer);
      state.feedbackInterestReelTimer = null;
    }
    if (state.feedbackInterestHardDeadlineTimer) {
      clearTimeout(state.feedbackInterestHardDeadlineTimer);
      state.feedbackInterestHardDeadlineTimer = null;
    }
    state.feedbackInterestReelDeadlineAt = 0;
  }

  function scheduleInterestReelTrigger(preferredTopic) {
    void preferredTopic;
    clearInterestReelSchedule();
  }

  function buildFeedbackSurvey(mood, reason, promptOverride) {
    const moodPrompt = String(promptOverride || "").trim() || selectFeedbackPrompt(mood);
    const surveys = [
      {
        kind: "mood",
        eyebrow: "Quick check-in",
        prompt: moodPrompt,
        options: FEEDBACK_OPTIONS_BY_MOOD[mood] || FEEDBACK_OPTIONS_BY_MOOD.focused,
      },
      {
        kind: "difficulty",
        eyebrow: "Difficulty tuning",
        prompt: "How does the test feel right now?",
        options: FEEDBACK_DIFFICULTY_OPTIONS,
      },
      {
        kind: "topic",
        eyebrow: "Content preference",
        prompt: "Which topic are you most interested in right now?",
        options: FEEDBACK_TOPIC_OPTIONS,
      },
    ];

    const filtered = surveys.filter((item) => item.kind !== state.lastFeedbackQuestionType);
    const pool = filtered.length ? filtered : surveys;

    // Ask topic/difficulty slightly more often after entering test to personalize quickly.
    if ((reason === "question_rendered" || reason === "enter_popups") && Math.random() < 0.65) {
      const preferredKinds = pool.filter((item) => item.kind === "topic" || item.kind === "difficulty");
      if (preferredKinds.length) {
        return preferredKinds[Math.floor(Math.random() * preferredKinds.length)];
      }
    }

    return pool[Math.floor(Math.random() * pool.length)];
  }

  const triggerConfig = {
    optionShuffle: { conflicts: [], cooldown: [18000, 26000] },
    phantomCompetitor: { conflicts: [], cooldown: [18000, 30000] },
    stressTimer: { conflicts: [], cooldown: [20000, 30000] },
    confidenceBreaker: { conflicts: [], cooldown: [15000, 22000] },
    focusHandSignal: { conflicts: ["blackout", "fakeCrashScreen", "blurAttack"], cooldown: [12000, 20000] },
    focusReadGate: { conflicts: ["blackout", "fakeCrashScreen", "blurAttack"], cooldown: [15000, 22000] },
    premiumImagePopup: { conflicts: ["blackout", "fakeCrashScreen", "blurAttack"], cooldown: [14000, 22000] },
    optionFeedbackPopups: { conflicts: [], cooldown: [12000, 20000] },
    mirageHighlight: { conflicts: [], cooldown: [15000, 22000] },
    blurAttack: { conflicts: [], cooldown: [16000, 24000], idleOnly: true },
    screenFlip: { conflicts: ["colorInversion", "blurAttack", "heartbeatVibration"], cooldown: [20000, 30000] },
    colorInversion: { conflicts: ["screenFlip", "blurAttack", "heartbeatVibration"], cooldown: [19000, 29000] },
    heartbeatVibration: { conflicts: [], cooldown: [18000, 26000] },
    waveDistortion: { conflicts: ["screenFlip"], cooldown: [18000, 26000] },
    fakeMentorCount: { conflicts: [], cooldown: [20000, 32000] },
    chaosBackground: { conflicts: ["blackout"], cooldown: [22000, 32000] },
    shepardTone: { conflicts: ["spatialTicking"], cooldown: [25000, 36000] },
    spatialTicking: { conflicts: ["shepardTone"], cooldown: [22000, 34000] },
    fakeLowBattery: { conflicts: ["fakeCrashScreen", "blackout"], cooldown: [22000, 32000] },
    fakeCrashScreen: { conflicts: ["fakeLowBattery", "blackout"], cooldown: [26000, 38000] },
    blackout: { conflicts: ["fakeLowBattery", "fakeCrashScreen", "chaosBackground"], cooldown: [24000, 36000] },
    hesitationHeatmap: { conflicts: [], cooldown: [18000, 26000] },
    torchlightSpotlight: { conflicts: ["blackout", "fakeCrashScreen", "blurAttack"], cooldown: [18000, 28000] },
    difficultyCheckPrompt: { conflicts: ["blackout", "fakeCrashScreen", "blurAttack"], cooldown: [18000, 30000] },
    boucingQuestion: { conflicts: ["blackout", "fakeCrashScreen"], cooldown: [24000, 36000] },
    // Question-level triggers for Focus Zones test
    hardFog: { conflicts: ["blurAttack"], cooldown: [18000, 26000] },
    accuracyTest: { conflicts: [], cooldown: [16000, 24000] },
    readingTest: { conflicts: [], cooldown: [16000, 24000] },
    hardPeerDoubt: { conflicts: ["phantomCompetitor"], cooldown: [18000, 28000] },
    billiardBall: { conflicts: [], cooldown: [16000, 24000] },
  };

  const ENABLED_TRIGGERS = new Set([
    "optionShuffle",
    "mirageHighlight",
    "screenFlip",
    "heartbeatVibration",
    "torchlightSpotlight",
    "difficultyCheckPrompt",
    "boucingQuestion",
    "optionFeedbackPopups",
    "focusHandSignal",
    "focusReadGate",
    "premiumImagePopup",
    // Question-level triggers for Focus Zones test
    "hardFog",
    "accuracyTest",
    "readingTest",
    "hardPeerDoubt",
    "billiardBall",
  ]);

  function isTriggerEnabled(name) {
    return ENABLED_TRIGGERS.has(name);
  }

  function debugLog(kind, detail) {
    if (!stressDebug) return;
    log(`stress_${kind}`, detail || "");
  }

  function stableHash(text) {
    let hash = 0;
    const src = String(text || "");
    for (let i = 0; i < src.length; i += 1) {
      hash = (hash * 31 + src.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  function stableRange(name, min, max) {
    const count = (activationCounts.get(name) || 0) + 1;
    const key = `${sessionId || "anon"}|${state.currentQuestionId}|${name}|${count}`;
    const hash = stableHash(key);
    const span = Math.max(1, max - min + 1);
    return min + (hash % span);
  }

  function getPlatform() {
    const ua = (navigator.userAgent || "").toLowerCase();
    return ua.includes("android") ? "android" : "web";
  }

  function getElapsedSeconds() {
    if (!state.examStartedAt) return 0;
    return Math.max(0, Math.floor((Date.now() - state.examStartedAt) / 1000));
  }

  function phaseRank(phase) {
    const ranks = {
      baseline: 0,
      escalation: 1,
      crucible: 2,
      final_sprint: 3,
    };
    return ranks[String(phase || "baseline")] ?? 0;
  }

  function phaseByRank(rank) {
    if (rank >= 3) return "final_sprint";
    if (rank >= 2) return "crucible";
    if (rank >= 1) return "escalation";
    return "baseline";
  }

  function getTestPhase() {
    const elapsed = getElapsedSeconds();
    const elapsedPhase =
      elapsed <= 90
        ? "baseline"
        : elapsed <= 300
          ? "escalation"
          : elapsed <= 600
            ? "crucible"
            : "final_sprint";

    // Fast-answering users can advance phases by progress, not only wall-clock time.
    const submissions = Number(state.totalSubmissions || 0);
    const progressPhase =
      submissions <= 2
        ? "baseline"
        : submissions <= 8
          ? "escalation"
          : submissions <= 16
            ? "crucible"
            : "final_sprint";

    return phaseByRank(Math.max(phaseRank(elapsedPhase), phaseRank(progressPhase)));
  }

  function clampBudget(value) {
    return Math.max(0, Math.min(STRESS_BUDGET_MAX, Math.round(Number(value) || 0)));
  }

  function addBudget(points) {
    state.stressBudget = clampBudget(state.stressBudget + Number(points || 0));
  }

  function consumeBudgetForIntensity(intensity) {
    const cost = TRIGGER_COST_BY_INTENSITY[String(intensity || "medium").toLowerCase()] || TRIGGER_COST_BY_INTENSITY.medium;
    addBudget(-cost);
    return cost;
  }

  function getRecentAccuracy() {
    const rows = Object.values(answeredMap || {});
    if (!rows.length) return 0.5;
    const correct = rows.filter((row) => Boolean(row?.correct)).length;
    return Math.max(0, Math.min(1, correct / rows.length));
  }

  function getAvgTouchPressure() {
    const samples = state.pointerPressureSamples;
    if (!samples.length) return null;
    const sum = samples.reduce((acc, val) => acc + Number(val || 0), 0);
    return Math.max(0, Math.min(1, sum / samples.length));
  }

  function capturePointerPressure(evt) {
    const pressure = Number(evt?.pressure);
    if (!Number.isFinite(pressure)) return;
    if (pressure <= 0) return;
    state.pointerPressureSamples.push(pressure);
    if (state.pointerPressureSamples.length > 25) {
      state.pointerPressureSamples = state.pointerPressureSamples.slice(-25);
    }
  }

  function updateDeviceMovement(magnitude) {
    if (!Number.isFinite(magnitude)) return;
    const clamped = Math.max(0, Math.min(10, magnitude));
    state.deviceMovementIndex = Math.round((state.deviceMovementIndex * 0.75) + (clamped * 0.25));
  }

  function getAppShell() {
    return document.querySelector(".app-shell");
  }

  function getTestCard() {
    return document.getElementById("testCard");
  }

  function isInterruptionActive() {
    return Object.keys(state.interruptionLocks || {}).length > 0;
  }

  function acquireInterruptionLock(source) {
    const key = String(source || "interruption");
    state.interruptionLocks[key] = (state.interruptionLocks[key] || 0) + 1;

    if (state.aiDebounceTimer) {
      clearTimeout(state.aiDebounceTimer);
      state.aiDebounceTimer = null;
    }
    state.queuedTriggerRequest = null;
    deactivateAllTriggers();

    if (popupTimer) {
      clearTimeout(popupTimer);
      popupTimer = null;
    }
    popupActive = false;
    if (popupOverlay) popupOverlay.innerHTML = "";
  }

  function releaseInterruptionLock(source) {
    const key = String(source || "interruption");
    const current = Number(state.interruptionLocks[key] || 0);
    if (current <= 1) delete state.interruptionLocks[key];
    else state.interruptionLocks[key] = current - 1;

    if (!isInterruptionActive() && state.stage === "popups") {
      state.screenQuietUntil = Date.now() + SCREEN_QUIET_BREAK_MS;
      processPopupQueue();
    }
  }

  function isInQuietBreak() {
    return Date.now() < Number(state.screenQuietUntil || 0);
  }

  function isScreenBusyForPopup() {
    return isInterruptionActive() || active.size > 0 || isInQuietBreak();
  }

  function getOrCreateAudioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioContext || audioContext.state === "closed") {
      audioContext = new Ctx();
    }
    return audioContext;
  }

  async function resumeAudioContextIfNeeded() {
    const ctx = getOrCreateAudioContext();
    if (!ctx) return null;
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch (e) {
        debugLog("audio_resume_failed", e?.message || String(e));
      }
    }
    if (ctx.state === "running") {
      state.audioPrimed = true;
    }
    return ctx;
  }

  function primeAudioContext() {
    // Must run from real user interaction handlers to satisfy autoplay policies.
    resumeAudioContextIfNeeded().catch((e) => {
      debugLog("audio_prime_failed", e?.message || String(e));
    });
  }

  function mountDevilTopBanner(lines) {
    // Disabled in production - no devil banners shown
    const banner = document.createElement("div");
    banner.style.display = "none";
    return banner;
  }

  function refreshDevButtonState(name) {
    const btn = devButtons.get(name);
    if (!btn) return;
    btn.classList.toggle("is-active", isTriggerActive(name));
  }

  function clearIdleVisuals() {
    // No idle-only cleanup required at the moment.
  }

  function setStage(name) {
    state.stage = name;
    if (name !== "popups") {
      clearInterestReelSchedule();
      deactivateAllTriggers();
    }
  }

  function markInteraction(kind, eventData) {
    const now = Date.now();
    state.lastInteractionAt = now;
    if (kind === "pointerdown") {
      capturePointerPressure(eventData);
    }
    if (kind === "click") {
      state.clickTimestamps.push(now);
      const cutoff = now - 1000;
      state.clickTimestamps = state.clickTimestamps.filter((ts) => ts >= cutoff);
      if (state.clickTimestamps.length >= 7 && now - state.lastRapidTapEventAt > 9000) {
        state.lastRapidTapEventAt = now;
        requestTriggerFromAI("high_tap_intensity", {
          click_frequency: state.clickTimestamps.length,
        });
      }
    }
    if (kind === "scroll" || kind === "click" || kind === "keydown") {
      clearIdleVisuals();
    }
    if (kind === "click" || kind === "keydown" || kind === "pointerdown") {
      primeAudioContext();
    }
  }

  function timeRemainingMs() {
    if (!state.examStartedAt || state.examStartedAt <= 0) return state.examDurationMs;
    const elapsed = Date.now() - state.examStartedAt;
    const remaining = state.examDurationMs - elapsed;
    return Math.max(0, remaining);
  }
  
  function timeUsedMs() {
    if (!state.examStartedAt || state.examStartedAt <= 0) return 0;
    const elapsed = Date.now() - state.examStartedAt;
    // Cap at exam duration to prevent going over
    return Math.min(elapsed, state.examDurationMs);
  }

  function currentUserState() {
    const now = Date.now();
    const qid = state.currentQuestionId || "";
    return {
      timeOnQuestionMs: state.questionStartedAt ? now - state.questionStartedAt : 0,
      idleMs: now - state.lastInteractionAt,
      answerChangeCount: Number(state.answerChangesByQuestion[qid] || 0),
      clickFrequency: state.clickTimestamps.length,
      hoverIntentOnOption: Boolean(state.hoverIntentOnOption),
      answerLatencyMs: state.lastAnswerLatencyMs == null ? Number.POSITIVE_INFINITY : state.lastAnswerLatencyMs,
      timeRemainingMs: timeRemainingMs(),
      questionDifficulty: state.questionDifficulty || "",
      isSubmittingAnswer: Boolean(state.isSubmittingAnswer),
    };
  }

  function canActivateTrigger(name, context) {
    if (!isTriggerEnabled(name)) return { ok: false, reason: "disabled" };
    const force = Boolean(context?.force);
    if (disableStressMode) return { ok: false, reason: "disabled" };
    
    // HARD BLOCK: Never activate triggers when test is over
    if (state.stage === "results") return { ok: false, reason: "test-ended" };
    if (typeof isTestActive !== 'undefined' && !isTestActive) return { ok: false, reason: "test-inactive" };
    
    // When force is true (question-level triggers), bypass most checks
    if (force) {
      // Only check if already active or max active reached
      if (active.has(name)) return { ok: false, reason: "active" };
      if (active.size >= 1) return { ok: false, reason: "max-active" };
      return { ok: true };
    }
    
    // Normal checks for AI-triggered events
    if (state.stage !== "popups") return { ok: false, reason: "stage" };
    if (isInterruptionActive()) return { ok: false, reason: "interruption" };
    if (isInQuietBreak()) return { ok: false, reason: "quiet-break" };
    if (active.has(name)) return { ok: false, reason: "active" };
    if (state.lastTriggerName === name) return { ok: false, reason: "repeat" };
    if (active.size >= 1) return { ok: false, reason: "max-active" };
    const until = cooldownUntil.get(name) || 0;
    if (Date.now() < until) return { ok: false, reason: "cooldown" };
    const config = triggerConfig[name] || { conflicts: [] };
    if ((config.conflicts || []).some((other) => active.has(other))) {
      return { ok: false, reason: "conflict" };
    }
    if (reducedMotion && [
      "phantomCompetitor",
      "heartbeatVibration",
      "blurAttack",
      "screenFlip",
      "colorInversion",
      "waveDistortion",
      "chaosBackground",
      "blackout",
      "hesitationHeatmap",
      "torchlightSpotlight",
      "boucingQuestion",
    ].includes(name)) {
      return { ok: false, reason: "reduced-motion" };
    }
    return { ok: true };
  }

  function setCooldown(name) {
    const cfg = triggerConfig[name] || { cooldown: [15000, 30000] };
    const [minMs, maxMs] = cfg.cooldown || [15000, 30000];
    const rawCooldown = stableRange(name, minMs, maxMs);
    const cooldown = Math.max(MIN_COOLDOWN_MS, Math.floor(rawCooldown * TRIGGER_COOLDOWN_FACTOR));
    cooldownUntil.set(name, Date.now() + cooldown);
  }

  function estimateConfidence(userState) {
    const changeCount = Number(userState?.answerChangeCount || 0);
    const idleMs = Number(userState?.idleMs || 0);
    const idlePenalty = Math.min(0.4, idleMs / 30000);
    const changePenalty = Math.min(0.45, changeCount * 0.12);
    const confidence = 0.85 - idlePenalty - changePenalty;
    return Math.max(0, Math.min(1, confidence));
  }

  function snapshotFeedbackMetrics(userState) {
    const curr = userState || currentUserState();
    return {
      time_spent: Math.max(0, Math.floor(Number(curr.timeOnQuestionMs || 0))),
      confidence: estimateConfidence(curr),
      accuracy: Boolean(state.lastAnswerWasCorrect),
    };
  }

  function enqueueTriggerOutcome(outcome) {
    if (!outcome || !outcome.trigger) return;
    state.recentTriggerOutcomes.push(outcome);
    if (state.recentTriggerOutcomes.length > 24) {
      state.recentTriggerOutcomes = state.recentTriggerOutcomes.slice(-24);
    }
  }

  function persistTriggerOutcome(outcome) {
    if (!sessionId || !outcome || !outcome.trigger) return;
    postJSON(`/session/${sessionId}/trigger-feedback`, outcome).catch((err) => {
      debugLog("feedback_persist_error", err?.message || String(err));
    });
  }

  function registerTrigger(name, cleanupFn, durationMs, context) {
    const timers = [];
    if (durationMs > 0) {
      timers.push(
        setTimeout(() => {
          deactivateTrigger(name);
        }, durationMs)
      );
    }
    active.set(name, {
      cleanupFn,
      timers,
      activatedAt: Date.now(),
      feedback: {
        intensity: String(context?.intensity || "low").toLowerCase(),
        pre_metrics: snapshotFeedbackMetrics(context?.userState),
      },
    });
    state.lastTriggerActivatedAt = Date.now();
    state.lastTriggerName = name;
    state.recentTriggerNames.push(name);
    if (state.recentTriggerNames.length > 12) {
      state.recentTriggerNames = state.recentTriggerNames.slice(-12);
    }
    setCooldown(name);
    activationCounts.set(name, (activationCounts.get(name) || 0) + 1);
    const consumedBudget = consumeBudgetForIntensity(context?.intensity || "medium");
    refreshDevButtonState(name);
    logPopupEvent({
      event: "trigger_activated",
      trigger: name,
      at: new Date().toISOString(),
      duration_ms: durationMs,
      reason: String(context?.reason || ""),
      intensity: String(context?.intensity || "low"),
      budget_spent: consumedBudget,
      budget_after: state.stressBudget,
    });
    log("trigger_activated", {
      trigger: name,
      at: new Date().toISOString(),
      duration_ms: durationMs,
      reason: String(context?.reason || ""),
      intensity: String(context?.intensity || "low"),
      budget_spent: consumedBudget,
      budget_after: state.stressBudget,
    });
    debugLog("activated", name);
  }

  function deactivateTrigger(name) {
    const entry = active.get(name);
    if (!entry) return;
    (entry.timers || []).forEach((timerId) => clearTimeout(timerId));
    try {
      entry.cleanupFn?.();
    } catch (e) {
      debugLog("cleanup_error", `${name}:${e?.message || String(e)}`);
    }
    active.delete(name);
    state.lastTriggerEndedAt = Date.now();
    state.screenQuietUntil = Date.now() + SCREEN_QUIET_BREAK_MS;

    const outcome = {
      trigger: name,
      intensity: entry?.feedback?.intensity || "low",
      timestamp: Date.now(),
      pre_metrics: entry?.feedback?.pre_metrics || snapshotFeedbackMetrics(),
      post_metrics: snapshotFeedbackMetrics(),
    };
    enqueueTriggerOutcome(outcome);
    persistTriggerOutcome(outcome);

    logPopupEvent({
      event: "trigger_deactivated",
      trigger: name,
      at: new Date().toISOString(),
      outcome,
    });
    log("trigger_deactivated", {
      trigger: name,
      at: new Date().toISOString(),
      outcome,
    });

    refreshDevButtonState(name);
    debugLog("ended", name);

    if (state.queuedTriggerRequest && active.size === 0 && state.stage === "popups") {
      const queued = state.queuedTriggerRequest;
      state.queuedTriggerRequest = null;
      setTimeout(() => {
        requestTriggerFromAI("queued_followup", {
          queued_event: queued.eventType,
          from_trigger: name,
          ...(queued.extra || {}),
        });
      }, 180);
    }
  }

  function deactivateAllTriggers() {
    [...active.keys()].forEach((name) => deactivateTrigger(name));
  }

  function isTriggerActive(name) {
    return active.has(name);
  }

  function triggerOptionShuffle() {
    const q = testQuestions[testQuestionIndex];
    if (!q || (q.question_type || "").toLowerCase() !== "scq" || !questionOptions) return null;
    const questionId = q.question_id;
    const totalCycles = 3;
    const warmupMs = 180;
    const reorderDurationMs = stableRange("optionShuffle_reorder", 620, 760);
    const pauseAfterEachMs = stableRange("optionShuffle_pause", 260, 340);
    const cycleStepMs = reorderDurationMs + pauseAfterEachMs;
    let lastOrder = [];
    questionOptions.classList.add("stress-option-shuffle");

    const quotes = [
      "I shuffled the obvious. Find truth, not pattern.",
      "Memory of position is a trap. Read again.",
      "Fast eyes lose. Calm eyes win.",
      "If order controls you, I already won.",
    ];
    const quote = quotes[stableRange("optionShuffle_quote", 0, quotes.length - 1)];
    const topBanner = mountDevilTopBanner({
      title: "Devil Shuffle",
      lead: "I moved your options when your focus blinked.",
      challenge: "Choose by logic, not by where it used to be.",
      taunt: quote,
    });

    const ephemeralNodes = [];

    function pushEphemeral(node) {
      if (!node) return;
      ephemeralNodes.push(node);
      return node;
    }

    function nextOrder(nodes) {
      const base = [...nodes];
      for (let i = base.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [base[i], base[j]] = [base[j], base[i]];
      }
      const currentSig = nodes.map((node) => node.querySelector("input")?.value || "?").join("|");
      const nextSig = base.map((node) => node.querySelector("input")?.value || "?").join("|");
      if (nextSig === currentSig && base.length > 1) {
        [base[0], base[1]] = [base[1], base[0]];
      }
      const finalSig = base.map((node) => node.querySelector("input")?.value || "?").join("|");
      if (finalSig === lastOrder.join("|") && base.length > 2) {
        [base[1], base[2]] = [base[2], base[1]];
      }
      lastOrder = base.map((node) => node.querySelector("input")?.value || "?");
      return base;
    }

    function animateReorder(nodes) {
      const beforeRects = new Map();
      nodes.forEach((node) => {
        beforeRects.set(node, node.getBoundingClientRect());
      });

      const reordered = nextOrder(nodes);
      reordered.forEach((entry) => questionOptions.appendChild(entry));

      const orderedNodes = Array.from(questionOptions.querySelectorAll("label.option"));
      orderedNodes.forEach((node, idx) => {
        const before = beforeRects.get(node);
        if (!before) return;
        const after = node.getBoundingClientRect();
        const dx = before.left - after.left;
        const dy = before.top - after.top;
        if (!dx && !dy) return;
        const tilt = (idx % 2 === 0 ? 1 : -1) * (2.5 + (idx % 3));
        const settleX = dx * 0.28;
        const settleY = dy * 0.28;
        node.animate(
          [
            {
              transform: `translate(${dx}px, ${dy}px) scale(0.96) rotate(${tilt}deg)`,
              filter: "blur(1.6px) saturate(1.28)",
            },
            {
              transform: `translate(${settleX}px, ${settleY}px) scale(1.05) rotate(${tilt * -0.35}deg)`,
              filter: "blur(0.45px) saturate(1.15)",
              offset: 0.45,
            },
            {
              transform: "translate(0, 0) scale(1) rotate(0deg)",
              filter: "blur(0px) saturate(1)",
            },
          ],
          {
            duration: reorderDurationMs,
            easing: "cubic-bezier(0.22, 0.78, 0.24, 1)",
            fill: "both",
            delay: idx * 14,
          }
        );
      });
    }

    function pulseEachOption(nodes) {
      nodes.forEach((node, idx) => {
        const ring = document.createElement("span");
        ring.className = "stress-option-ring";
        ring.style.setProperty("--ring-delay", `${idx * 42}ms`);
        ring.style.setProperty("--ring-size", `${40 + (idx % 3) * 8}px`);
        ring.style.setProperty("--ring-alpha", `${0.62 - (idx % 3) * 0.08}`);
        node.appendChild(ring);
        pushEphemeral(ring);
      });
    }

    const timeoutIds = [];
    const selected = selectedOptions[questionId] || "";
    for (let cycle = 0; cycle < totalCycles; cycle += 1) {
      const cycleDelay = warmupMs + cycle * cycleStepMs;
      const cycleTimer = setTimeout(() => {
        const cycleNodes = Array.from(questionOptions.querySelectorAll("label.option"));
        if (cycleNodes.length < 2) return;
        animateReorder(cycleNodes);
        pulseEachOption(cycleNodes);
        cycleNodes.forEach((node) => {
          node.classList.remove("stress-shuffle-flash");
        });
        requestAnimationFrame(() => {
          cycleNodes.forEach((node) => node.classList.add("stress-shuffle-flash"));
        });
        if (selected) {
          const input = questionOptions.querySelector(`input[value="${selected}"]`);
          if (input) input.checked = true;
        }
      }, cycleDelay);
      timeoutIds.push(cycleTimer);
    }

    const totalDurationMs = warmupMs + totalCycles * cycleStepMs;
    return {
      durationMs: totalDurationMs,
      cleanup: () => {
        timeoutIds.forEach((id) => clearTimeout(id));
        questionOptions.classList.remove("stress-option-shuffle");
        questionOptions.querySelectorAll(".stress-shuffle-flash").forEach((node) => node.classList.remove("stress-shuffle-flash"));
        ephemeralNodes.forEach((node) => node.remove());
        topBanner.remove();
      },
    };
  }

  function triggerPhantomCompetitor() {
    const host = getTestCard();
    if (!host) return null;
    const statusSteps = [
      "⚡ 3 people just moved ahead of you",
      "🔥 Others are clearing this faster — you're still here",
      "🚨 You're falling behind the current pace",
      "👀 Most have already locked an answer",
      "⚡ Someone just overtook you — gap increasing",
    ];
    let pickedIndex = stableRange("phantomCompetitor_copy", 0, statusSteps.length - 1);
    if (pickedIndex === state.lastPhantomMessageIndex) {
      pickedIndex = (pickedIndex + 1) % statusSteps.length;
    }
    state.lastPhantomMessageIndex = pickedIndex;
    const pickedMessage = statusSteps[pickedIndex];
    const quotes = [
      "Pressure from others is noise. But can you filter it?",
      "Race panic is my favorite shortcut to mistakes.",
      "They are ahead. Are you still thinking clearly?",
      "Speed envy breaks focus faster than fear.",
    ];
    const quote = quotes[stableRange("phantomCompetitor_quote", 0, quotes.length - 1)];
    const topBanner = mountDevilTopBanner({
      title: "Devil Crowd",
      lead: "Look around. Everyone seems to be moving faster than you.",
      challenge: "Can you hold your pace without chasing panic?",
      taunt: quote,
    });

    const banner = document.createElement("div");
    banner.className = "stress-competitor-banner";
    banner.innerHTML = `
      <span class="pulse"></span>
      <span class="message">${escapeHTML(pickedMessage)}</span>
    `;

    const head = host.querySelector(".test-head");
    if (head) host.insertBefore(banner, head);
    else host.prepend(banner);

    return {
      durationMs: stableRange("phantomCompetitor_duration", 5000, 8000),
      cleanup: () => {
        banner.remove();
        topBanner.remove();
      },
    };
  }

  function triggerStressTimer() {
    const durationMs = stableRange("stressTimer_duration", 10000, 15000);
    const quotes = [
      "Time noise is bait. Precision is the weapon.",
      "The clock screams loudest when your plan is weak.",
      "Beat me by staying methodical, not frantic.",
      "A rushed mind burns seconds faster than any timer.",
    ];
    const quote = quotes[stableRange("stressTimer_quote", 0, quotes.length - 1)];
    const topBanner = mountDevilTopBanner({
      title: "Devil Timer",
      lead: "I tightened the clock around your decision making.",
      challenge: "Answer under pressure. Can you stay exact?",
      taunt: quote,
    });

    const overlay = document.createElement("div");
    overlay.className = "stress-timer-overlay is-dramatic";
    overlay.style.setProperty("--stress-timer-duration", `${durationMs}ms`);
    let fakeCount = 60;
    overlay.innerHTML = `
      <div class="title">Time Compression</div>
      <div class="count">${fakeCount}s</div>
      <div class="stress-meter"><span style="width:100%"></span></div>
    `;
    document.body.appendChild(overlay);
    const tickId = setInterval(() => {
      fakeCount = Math.max(0, fakeCount - 1);
      const countEl = overlay.querySelector(".count");
      if (countEl) countEl.textContent = `${fakeCount}s`;
      const meter = overlay.querySelector(".stress-meter span");
      if (meter) meter.style.width = `${Math.max(0, Math.min(100, (fakeCount / 60) * 100))}%`;
    }, 280);
    return {
      durationMs,
      cleanup: () => {
        clearInterval(tickId);
        overlay.remove();
        topBanner.remove();
      },
    };
  }

  function isHardDifficulty(value) {
    const text = String(value || "").trim().toLowerCase();
    return text === "hard" || text === "h" || text.includes("hard");
  }

  function showHardQuestionFullScreen(kind) {
    const overlay = document.createElement("div");
    overlay.className = `hard-question-fullscreen ${kind === "fail" || kind === "fail-wrong" ? "is-fail" : "is-intro"}`;
    
    if (kind === "intro") {
      overlay.innerHTML = `
        <div class="hard-question-center">
          <div class="hard-question-icon">⚡</div>
          <div class="hard-question-eyebrow">HARD QUESTION AHEAD</div>
          <div class="hard-question-title">You have 30 seconds.</div>
          <div class="hard-question-accent">And a trap.</div>
          <div class="hard-question-box">
            <div class="hard-question-box-icon">🕷️</div>
            <div class="hard-question-box-title">Something's going to happen.</div>
            <div class="hard-question-box-sub">We're not telling you what.</div>
            <div class="hard-question-box-foot">Figure it out. Answer anyway.</div>
          </div>
          <div class="hard-question-footnote">Starting in a moment...</div>
        </div>
      `;
    } else if (kind === "fail-wrong") {
      // Wrong answer fail screen with shaky skull
      overlay.innerHTML = `
        <div class="hard-question-center">
          <div class="hard-question-icon shake-skull">💀</div>
          <div class="hard-question-eyebrow">HARD QUESTION · FAILED</div>
          <div class="hard-question-title">That was the make-or-break moment.</div>
          <div class="hard-question-box is-fail-box">
            <div class="hard-question-box-sub">You broke.</div>
          </div>
          <div class="hard-question-footnote">Next question in 3s</div>
        </div>
      `;
    } else {
      // Timeout fail screen (30 seconds expired)
      overlay.innerHTML = `
        <div class="hard-question-center">
          <div class="hard-question-icon">💀</div>
          <div class="hard-question-eyebrow">HARD QUESTION · FAILED</div>
          <div class="hard-question-title">30 seconds are gone.</div>
          <div class="hard-question-box is-fail-box">
            <div class="hard-question-box-sub">That question could have lifted you 500 ranks.</div>
          </div>
          <div class="hard-question-footnote">Next question in 3s</div>
        </div>
      `;
    }
    document.body.appendChild(overlay);
    return overlay;
  }

  function clearHardQuestionChallenge() {
    const info = state.hardQuestionChallenge;
    if (!info) return;
    if (info.tickId) clearInterval(info.tickId);
    if (info.regenRafId) cancelAnimationFrame(info.regenRafId);
    if (info.resizeHandler) {
      window.removeEventListener("resize", info.resizeHandler);
      window.removeEventListener("orientationchange", info.resizeHandler);
    }
    if (info.scratchHandlers) {
      window.removeEventListener("pointerdown", info.scratchHandlers.onPointerDown);
      window.removeEventListener("pointermove", info.scratchHandlers.onPointerMove);
      window.removeEventListener("pointerup", info.scratchHandlers.onPointerUp);
      window.removeEventListener("pointercancel", info.scratchHandlers.onPointerUp);
    }
    info.rubLayer?.remove();
    info.introOverlay?.remove();
    info.failOverlay?.remove();
    const timerEl = document.getElementById("questionTimer");
    if (timerEl) {
      timerEl.classList.remove("hard-question-countdown");
      // Reset timer display to normal exam timer
      const remainingMs = timeRemainingMs();
      const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      timerEl.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    state.hardQuestionChallenge = null;
    state.hardQuestionPostSubmitDelayMs = 0;
  }

  function activateHardQuestionChallenge(question) {
    if (!questionBody || !question?.question_id || !isHardDifficulty(question?.difficulty)) return;
    clearHardQuestionChallenge();

    const challenge = {
      questionId: String(question.question_id),
      deadlineAt: 0,
      tickId: null,
      regenRafId: null,
      introOverlay: showHardQuestionFullScreen("intro"),
      failOverlay: null,
      rubLayer: null,
      canvas: null,
      ctx: null,
      resizeHandler: null,
      resolved: false,
      scratchHandlers: null,
    };
    state.hardQuestionChallenge = challenge;

    setTimeout(() => {
      if (!state.hardQuestionChallenge || state.hardQuestionChallenge.questionId !== challenge.questionId) return;
      challenge.introOverlay?.remove();
      challenge.introOverlay = null;
      
      // Show the question now that intro overlay is dismissed
      if (questionStem) questionStem.style.visibility = 'visible';
      if (questionOptions) questionOptions.style.visibility = 'visible';
      
      challenge.deadlineAt = Date.now() + 30000;

      const timerEl = document.getElementById("questionTimer");
      if (timerEl) timerEl.classList.add("hard-question-countdown");

      const layer = document.createElement("div");
      layer.className = "hard-question-rub-layer";
      const canvas = document.createElement("canvas");
      layer.appendChild(canvas);
      document.body.appendChild(layer);
      challenge.rubLayer = layer;
      challenge.canvas = canvas;
      challenge.ctx = canvas.getContext("2d");

      const syncLayer = () => {
        if (!challenge.rubLayer || !questionBody) return;
        const rect = questionBody.getBoundingClientRect();
        challenge.rubLayer.style.left = `${Math.round(rect.left)}px`;
        challenge.rubLayer.style.top = `${Math.round(rect.top)}px`;
        challenge.rubLayer.style.width = `${Math.round(rect.width)}px`;
        challenge.rubLayer.style.height = `${Math.round(rect.height)}px`;
        canvas.width = Math.max(1, Math.round(rect.width * window.devicePixelRatio));
        canvas.height = Math.max(1, Math.round(rect.height * window.devicePixelRatio));
        canvas.style.width = `${Math.round(rect.width)}px`;
        canvas.style.height = `${Math.round(rect.height)}px`;
        if (challenge.ctx) {
          challenge.ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
          challenge.ctx.globalCompositeOperation = "source-over";
          challenge.ctx.filter = "blur(1.5px)";
          challenge.ctx.fillStyle = "rgba(236, 240, 248, 0.86)";
          challenge.ctx.fillRect(0, 0, rect.width, rect.height);
          challenge.ctx.filter = "none";
        }
      };
      syncLayer();
      challenge.resizeHandler = () => syncLayer();
      window.addEventListener("resize", challenge.resizeHandler);
      window.addEventListener("orientationchange", challenge.resizeHandler);

      let scratching = false;
      let lastScratchAt = 0;
      const isPointInsideLayer = (evt) => {
        if (!challenge.rubLayer) return false;
        const rect = challenge.rubLayer.getBoundingClientRect();
        const x = evt.clientX;
        const y = evt.clientY;
        return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
      };
      const scratchAt = (evt) => {
        if (!challenge.ctx || !challenge.rubLayer) return;
        const rect = challenge.rubLayer.getBoundingClientRect();
        const x = evt.clientX - rect.left;
        const y = evt.clientY - rect.top;
        const pressure = Math.max(0.2, Math.min(1, Number(evt.pressure || 0.35)));
        const radius = 24 + pressure * 24;
        challenge.ctx.globalCompositeOperation = "destination-out";
        const gradient = challenge.ctx.createRadialGradient(x, y, 0, x, y, radius);
        gradient.addColorStop(0, "rgba(0, 0, 0, 1)");
        gradient.addColorStop(0.6, "rgba(0, 0, 0, 0.85)");
        gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
        challenge.ctx.fillStyle = gradient;
        challenge.ctx.beginPath();
        challenge.ctx.arc(x, y, radius, 0, Math.PI * 2);
        challenge.ctx.fill();
        lastScratchAt = Date.now();
      };
      const onPointerDown = (evt) => {
        if (!isPointInsideLayer(evt)) return;
        scratching = true;
        scratchAt(evt);
      };
      const onPointerMove = (evt) => {
        if (!isPointInsideLayer(evt)) return;
        if (!scratching && evt.pointerType !== "mouse") return;
        scratchAt(evt);
      };
      const onPointerUp = () => {
        scratching = false;
      };
      window.addEventListener("pointerdown", onPointerDown, { passive: true });
      window.addEventListener("pointermove", onPointerMove, { passive: true });
      window.addEventListener("pointerup", onPointerUp, { passive: true });
      window.addEventListener("pointercancel", onPointerUp, { passive: true });
      challenge.scratchHandlers = { onPointerDown, onPointerMove, onPointerUp };

      const regen = () => {
        if (!challenge.ctx || !challenge.rubLayer) return;
        const rect = challenge.rubLayer.getBoundingClientRect();
        const sinceScratchMs = Math.max(0, Date.now() - lastScratchAt);
        const alpha = sinceScratchMs < 1200 ? 0.004 : 0.012;
        challenge.ctx.globalCompositeOperation = "source-over";
        challenge.ctx.fillStyle = `rgba(236, 240, 248, ${alpha})`;
        challenge.ctx.fillRect(0, 0, rect.width, rect.height);
        challenge.regenRafId = requestAnimationFrame(regen);
      };
      challenge.regenRafId = requestAnimationFrame(regen);

      challenge.tickId = setInterval(() => {
        if (!state.hardQuestionChallenge || state.hardQuestionChallenge.questionId !== challenge.questionId) return;
        const remainingMs = Math.max(0, challenge.deadlineAt - Date.now());
        // Timer display is now handled by startExamClock
        if (remainingMs > 0) return;
        clearInterval(challenge.tickId);
        challenge.tickId = null;
        if (challenge.resolved) return;
        challenge.resolved = true;
        const q = testQuestions[testQuestionIndex];
        if (q && q.question_id === challenge.questionId) {
          const picked = selectedOptions[q.question_id];
          const correctAnswer = q.correct_answer || q.correct_answers;
          const primaryCorrectLabel = Array.isArray(correctAnswer)
            ? normalizeAnswerLabel(correctAnswer[0])
            : normalizeAnswerLabel(correctAnswer);
          answeredMap[q.question_id] = {
            selected: picked || "",
            correct: false,
            correctLabel: primaryCorrectLabel,
          };
          if (_lifelines > 0) _lifelines -= 1;
          updateScoreMeta();
          updateLifelineState();
          renderResultStateForCurrentQuestion();
          setTestHint("Time up on hard question.");
        }
        challenge.failOverlay = showHardQuestionFullScreen("fail");
        state.hardQuestionPostSubmitDelayMs = 3200;
        setTimeout(() => {
          challenge.failOverlay?.remove();
          challenge.failOverlay = null;
          clearHardQuestionChallenge();
          advanceAfterSubmit();
        }, 3200);
      }, 120);
    }, 2100);
  }

  function triggerConfidenceBreaker() {
    const punchLines = [
      "You cannot beat the devil with guesses.",
      "Devil reads panic. Panic reads wrong.",
      "You blinked. Devil didn't.",
      "The devil wins when focus breaks.",
      "Beat the question, not your own nerves.",
    ];
    let punchIndex = Math.floor(Math.random() * punchLines.length);
    if (punchLines.length > 1 && punchIndex === state.lastConfidencePunchIndex) {
      punchIndex = (punchIndex + 1 + Math.floor(Math.random() * (punchLines.length - 1))) % punchLines.length;
    }
    state.lastConfidencePunchIndex = punchIndex;
    const punchLine = punchLines[punchIndex];

    const overlay = document.createElement("div");
    overlay.className = "stress-fail-overlay";
    overlay.innerHTML = `
      <div class="stress-fail-popup" role="dialog" aria-modal="true" aria-label="Test failed popup">
        <button type="button" class="stress-fail-close" aria-label="Close fail popup">×</button>
        <div class="stress-fail-emoji" aria-hidden="true">😈</div>
        <div class="stress-fail-main">Devil catched you</div>
        <div class="stress-fail-title">Wrong answer locked. Test failed.</div>
        <div class="stress-fail-sub">${escapeHTML(punchLine)}</div>
      </div>
    `;

    const closeBtn = overlay.querySelector(".stress-fail-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        deactivateTrigger("confidenceBreaker");
      });
    }

    document.body.appendChild(overlay);
    return {
      durationMs: stableRange("confidenceBreaker_duration", 8000, 12000),
      cleanup: () => overlay.remove(),
    };
  }

  function triggerFocusHandSignal() {
    const overlay = document.createElement("div");
    overlay.className = "stress-focus-hand-overlay";
    overlay.innerHTML = `
      <div class="stress-focus-hand-center">
        <div class="stress-focus-rings" aria-hidden="true">
          <span class="focus-ring ring-a"></span>
          <span class="focus-ring ring-b"></span>
          <span class="focus-ring ring-c"></span>
        </div>
        <div class="stress-focus-hand" aria-hidden="true">👉</div>
        <div class="stress-focus-text">
          <div class="focus-eyebrow">YOU NEED TO</div>
          <div class="focus-main">FOCUS</div>
          <div class="focus-sub">on this question</div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return {
      durationMs: stableRange("focusHandSignal_duration", 3200, 5200),
      cleanup: () => overlay.remove(),
    };
  }

  function extractQuestionKeywords(text) {
    const stop = new Set([
      "the", "and", "for", "from", "that", "with", "this", "which", "what", "when",
      "then", "than", "into", "over", "only", "most", "least", "find", "solve",
      "given", "each", "does", "your", "their", "they", "them", "where", "there",
      "these", "those", "will", "would", "could", "should", "true", "false",
      "correct", "wrong", "option", "following", "statement", "value",
    ]);
    const tokens = String(text || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .split(" ")
      .filter(Boolean);
    let words = tokens.filter((t) => t.length >= 4 && !stop.has(t));
    if (!words.length) words = tokens.filter((t) => t.length >= 3);
    const freq = new Map();
    words.forEach((t) => freq.set(t, (freq.get(t) || 0) + 1));
    return [...freq.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 6)
      .map(([t]) => t);
  }

  function isRecallValid(stemText, inputText) {
    const raw = String(inputText || "").trim();
    
    // Minimum length check - at least 10 characters
    if (raw.length < 10) {
      console.log('[isRecallValid] Too short:', raw.length, 'chars');
      return false;
    }
    
    // Tokenize input
    const inputTokens = raw
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .split(" ")
      .filter(Boolean);
    
    if (!inputTokens.length) {
      console.log('[isRecallValid] No valid tokens');
      return false;
    }
    
    const inputSet = new Set(inputTokens);
    
    // Extract keywords from question
    const keywords = extractQuestionKeywords(stemText);
    console.log('[isRecallValid] Question keywords:', keywords);
    
    // Count matching keywords
    const matches = keywords.filter((t) => inputSet.has(t)).length;
    console.log('[isRecallValid] Keyword matches:', matches, '/', keywords.length);
    
    // More lenient threshold: 25% of keywords OR at least 2 keywords
    const minMatches = Math.max(1, Math.ceil(keywords.length * 0.25));
    
    // Check for numbers in the question
    const numbers = String(stemText || "").match(/\b\d+(?:\.\d+)?\b/g) || [];
    const hasNumber = numbers.some((n) => raw.includes(n));
    console.log('[isRecallValid] Has number match:', hasNumber, numbers);
    
    // Accept if:
    // 1. Matches enough keywords
    // 2. Has a number from the question AND reasonable length (15+ chars)
    // 3. Very long answer (40+ chars) showing effort
    const isValid = matches >= minMatches || 
                    (hasNumber && raw.length >= 15) ||
                    raw.length >= 40;
    
    console.log('[isRecallValid] Result:', isValid, '(matches:', matches, 'minMatches:', minMatches, 'length:', raw.length, ')');
    return isValid;
  }

  function triggerFocusReadGate() {
    const ctx = getActiveQuestionContext();
    if (!ctx.question || !ctx.stemText) return null;
    
    console.log('[triggerFocusReadGate] Starting with question:', ctx.stemText);
    
    const overlay = document.createElement("div");
    overlay.className = "stress-read-gate";
    overlay.dataset.step = "1";
    overlay.innerHTML = `
      <div class="read-gate-card" data-step="1">
        <div class="read-gate-lock">
          <span class="lock-icon" aria-hidden="true">🔒</span>
        </div>
        <div class="read-gate-eyebrow">QUESTION LOCKED</div>
        <div class="read-gate-title">Did you read it?</div>
        <button type="button" class="btn primary read-gate-btn" data-action="unlock">🔓 Unlock</button>
      </div>
      <div class="read-gate-card" data-step="2">
        <div class="read-gate-dot" aria-hidden="true"></div>
        <div class="read-gate-eyebrow">PROVE YOU READ IT</div>
        <div class="read-gate-title">What was the question saying?</div>
        <div class="read-gate-sub">If you read it, you can describe it.</div>
        <textarea class="read-gate-input" placeholder="In your own words — what was the question asking?"></textarea>
        <button type="button" class="btn primary read-gate-btn" data-action="verify">Unlock the Question</button>
        <div class="read-gate-divider"><span>or</span></div>
        <button type="button" class="btn ghost read-gate-btn read-gate-ghost" data-action="giveup">I gave up</button>
        <div class="read-gate-foot">No going back.</div>
      </div>
    `;
    document.body.appendChild(overlay);

    const stepInput = overlay.querySelector(".read-gate-input");
    let isProcessing = false; // Flag to prevent multiple clicks
    
    const showStep = (step) => {
      overlay.dataset.step = String(step);
      if (step === 2) stepInput?.focus();
    };

    const closeGate = () => {
      console.log('[triggerFocusReadGate] Closing gate and removing overlay');
      overlay.remove();
      deactivateTrigger("focusReadGate");
    };

    // Show roast message for 4.5 seconds then unlock
    const showRoastAndUnlock = (message) => {
      if (isProcessing) {
        console.log('[triggerFocusReadGate] Already processing, ignoring duplicate click');
        return;
      }
      isProcessing = true;
      
      console.log('[triggerFocusReadGate] Showing roast:', message);
      
      // Hide the input overlay first
      overlay.style.display = 'none';
      
      const roastOverlay = document.createElement('div');
      roastOverlay.className = 'stress-difficulty-check-overlay';
      roastOverlay.style.zIndex = '10003';
      roastOverlay.innerHTML = `
        <div class="binary-card" style="max-width: 420px; padding: 28px 24px;">
          <div class="binary-question" style="font-size: 20px; font-weight: 600; line-height: 1.4; color: #f8fafc;">${message}</div>
        </div>
      `;
      document.body.appendChild(roastOverlay);
      
      console.log('[triggerFocusReadGate] Roast overlay appended to body');
      
      setTimeout(() => {
        console.log('[triggerFocusReadGate] Roast complete, unlocking question');
        roastOverlay.remove();
        closeGate();
      }, 4500);
    };

    const unlockBtn = overlay.querySelector('[data-action="unlock"]');
    const verifyBtn = overlay.querySelector('[data-action="verify"]');
    const giveupBtn = overlay.querySelector('[data-action="giveup"]');

    if (unlockBtn) {
      unlockBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log('[triggerFocusReadGate] Unlock button clicked');
        showStep(2);
      });
    }
    
    if (verifyBtn) {
      verifyBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        if (isProcessing) {
          console.log('[triggerFocusReadGate] Already processing, ignoring click');
          return;
        }
        
        const value = String(stepInput?.value || "").trim();
        console.log('[triggerFocusReadGate] Verify clicked, input:', value);
        
        if (isRecallValid(ctx.stemText, value)) {
          console.log('[triggerFocusReadGate] Answer valid, showing success roast');
          showRoastAndUnlock("Impressive recall. But reading isn't the hard part — answering correctly is. 📖");
        } else {
          console.log('[triggerFocusReadGate] Answer invalid, showing failure roast');
          showRoastAndUnlock("That's not even close. Were you actually reading, or just staring? 👀");
        }
      });
    }
    
    if (giveupBtn) {
      giveupBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        if (isProcessing) {
          console.log('[triggerFocusReadGate] Already processing, ignoring click');
          return;
        }
        
        console.log('[triggerFocusReadGate] Give up button clicked');
        showRoastAndUnlock("At least you're honest about your lack of focus. That's... something. 🤷");
      });
    }

    return {
      durationMs: 0,
      cleanup: () => {
        console.log('[triggerFocusReadGate] Cleanup called');
        overlay.remove();
      },
    };
  }

  const PREMIUM_IMAGE_LIBRARY = [
    {
      tone: "wrong",
      title: "WRONG ANSWER",
      headline: "Your JEE rank just dropped 10,000 spots",
      sub: "Focus. Or someone else will take what you're working for.",
      question: "Can you make it to the top IITs?",
      image: `
        <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="facepalm">
          <defs>
            <radialGradient id="g1" cx="40%" cy="35%" r="70%">
              <stop offset="0%" stop-color="#FDE68A"/>
              <stop offset="100%" stop-color="#F59E0B"/>
            </radialGradient>
          </defs>
          <circle cx="80" cy="80" r="58" fill="url(#g1)"/>
          <rect x="52" y="58" width="70" height="18" rx="9" fill="#111827" opacity="0.3"/>
          <circle cx="64" cy="82" r="6" fill="#1F2937"/>
          <circle cx="98" cy="82" r="6" fill="#1F2937"/>
          <path d="M60 112c10 10 30 10 40 0" stroke="#1F2937" stroke-width="8" stroke-linecap="round"/>
          <path d="M40 44l56 24" stroke="#F97316" stroke-width="16" stroke-linecap="round"/>
        </svg>
      `.trim(),
    },
    {
      tone: "wrong",
      title: "WRONG ANSWER",
      headline: "This is not it chief 😐",
      sub: "Do you even think this way you're gonna get into the top colleges?",
      question: "Can you achieve rank under 1000?",
      image: `
        <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="neutral">
          <defs>
            <radialGradient id="g2" cx="40%" cy="35%" r="70%">
              <stop offset="0%" stop-color="#FFE29A"/>
              <stop offset="100%" stop-color="#FBBF24"/>
            </radialGradient>
          </defs>
          <circle cx="80" cy="80" r="58" fill="url(#g2)"/>
          <circle cx="60" cy="78" r="7" fill="#111827"/>
          <circle cx="100" cy="78" r="7" fill="#111827"/>
          <path d="M58 110h44" stroke="#111827" stroke-width="8" stroke-linecap="round"/>
        </svg>
      `.trim(),
    },
    {
      tone: "wrong",
      title: "WRONG ANSWER",
      headline: "That's a costly slip",
      sub: "Top scorers are still reading the stem twice.",
      question: "Can you stay in the race?",
      image: `
        <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="melt">
          <defs>
            <radialGradient id="g3" cx="40%" cy="35%" r="70%">
              <stop offset="0%" stop-color="#FDE68A"/>
              <stop offset="100%" stop-color="#F59E0B"/>
            </radialGradient>
          </defs>
          <path d="M80 18c-30 0-54 24-54 54 0 28 20 52 46 58 22 6 52 2 62-10 12-14 0-30-16-34 20-6 36-26 36-48 0-30-24-54-74-54z" fill="url(#g3)"/>
          <circle cx="60" cy="70" r="7" fill="#111827"/>
          <circle cx="98" cy="70" r="7" fill="#111827"/>
          <path d="M58 98c12 10 34 10 44 0" stroke="#111827" stroke-width="8" stroke-linecap="round"/>
        </svg>
      `.trim(),
    },
  ];

  function triggerPremiumImagePopup() {
    const card = PREMIUM_IMAGE_LIBRARY[Math.floor(Math.random() * PREMIUM_IMAGE_LIBRARY.length)];
    const overlay = document.createElement("div");
    overlay.className = "stress-premium-overlay";
    overlay.innerHTML = `
      <div class="premium-card">
        <div class="premium-image" aria-hidden="true">${card.image}</div>
        <div class="premium-eyebrow">${escapeHTML(card.title)}</div>
        <div class="premium-headline">${escapeHTML(card.headline)}</div>
        <div class="premium-sub">${escapeHTML(card.sub)}</div>
        <div class="premium-question">${escapeHTML(card.question)}</div>
        <div class="premium-actions">
          <button type="button" class="premium-btn ghost" data-action="no">I Cannot 😔</button>
          <button type="button" class="premium-btn primary" data-action="yes">I Can 💪</button>
        </div>
        <div class="premium-foot">Auto-continuing in 3s...</div>
      </div>
    `;
    const close = () => deactivateTrigger("premiumImagePopup");
    overlay.addEventListener("click", (evt) => {
      if (evt.target === overlay) close();
    });
    overlay.querySelector('[data-action="no"]')?.addEventListener("click", close);
    overlay.querySelector('[data-action="yes"]')?.addEventListener("click", close);
    document.body.appendChild(overlay);
    const foot = overlay.querySelector(".premium-foot");
    let remaining = 3;
    const tick = () => {
      if (!foot) return;
      foot.textContent = `Auto-continuing in ${remaining}s...`;
    };
    tick();
    const intervalId = setInterval(() => {
      remaining = Math.max(0, remaining - 1);
      tick();
      if (remaining <= 0) close();
    }, 1000);
    const autoTimer = setTimeout(() => close(), 3000);
    return {
      durationMs: 0,
      cleanup: () => {
        clearTimeout(autoTimer);
        clearInterval(intervalId);
        overlay.remove();
      },
    };
  }

  function ensureOptionFeedbackOverlay() {
    if (state.optionFeedbackOverlay && state.optionFeedbackOverlay.isConnected) {
      return state.optionFeedbackOverlay;
    }
    const overlay = document.createElement("div");
    overlay.className = "confirm-modal option-feedback-modal";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML = `
      <div class="confirm-card option-feedback-card">
        <div class="option-feedback-x" aria-hidden="true">×</div>
        <div class="option-feedback-pill" data-role="headline"></div>
        <div class="option-feedback-main" data-role="subhead"></div>
        <div class="option-feedback-tip">
          <span class="tip-icon" aria-hidden="true">💡</span>
          <span data-role="coach"></span>
        </div>
        <div class="confirm-actions">
          <button type="button" class="btn ghost small option-feedback-recheck-btn" data-role="recheck" style="color: #1A202C; border-color: #CBD5E0; background: rgba(255, 255, 255, 0.9);">Recheck</button>
          <button type="button" class="btn primary small" data-role="lock">Lock Answer</button>
        </div>
      </div>
    `;
    overlay.addEventListener("click", (evt) => {
      if (evt.target === overlay) closeOptionFeedbackPopup();
    });
    const recheckBtn = overlay.querySelector('[data-role="recheck"]');
    recheckBtn?.addEventListener("click", () => closeOptionFeedbackPopup());
    const lockBtn = overlay.querySelector('[data-role="lock"]');
    lockBtn?.addEventListener("click", () => {
      closeOptionFeedbackPopup();
      submitCurrentQuestion();
    });
    document.body.appendChild(overlay);
    state.optionFeedbackOverlay = overlay;
    return overlay;
  }

  function closeOptionFeedbackPopup() {
    if (state.optionFeedbackOverlay) state.optionFeedbackOverlay.remove();
    state.optionFeedbackOverlay = null;
  }

  function maybeShowOptionFeedbackPopup(questionId, optionLabel) {
    if (!state.optionFeedbackActive) return;
    if (!questionId || !optionLabel) return;
    if (String(questionId) !== String(state.optionFeedbackQuestionId || "")) return;
    const label = String(optionLabel || "").trim().toUpperCase();
    if (!label) return;
    state.optionFeedbackLastOption = label;
    const payload = OPTION_FEEDBACK_LIBRARY[label] || OPTION_FEEDBACK_LIBRARY.A;
    const overlay = ensureOptionFeedbackOverlay();
    const headline = overlay.querySelector('[data-role="headline"]');
    const subhead = overlay.querySelector('[data-role="subhead"]');
    const coach = overlay.querySelector('[data-role="coach"]');
    if (headline) headline.textContent = payload.headline;
    if (subhead) subhead.textContent = payload.subhead;
    if (coach) coach.textContent = payload.coach;
  }

  function triggerOptionFeedbackPopups() {
    if (!state.currentQuestionId) return null;
    state.optionFeedbackActive = true;
    state.optionFeedbackQuestionId = String(state.currentQuestionId || "");
    state.optionFeedbackLastOption = "";
    return {
      durationMs: 0,
      cleanup: () => {
        state.optionFeedbackActive = false;
        state.optionFeedbackQuestionId = "";
        state.optionFeedbackLastOption = "";
        closeOptionFeedbackPopup();
      },
    };
  }

  function triggerMirageHighlight() {
    if (!questionOptions) return null;
    const allOptions = Array.from(questionOptions.querySelectorAll("label.option"));
    if (!allOptions.length) return null;
    const targetIndex = stableRange("mirageHighlight_target", 0, allOptions.length - 1);
    const target = allOptions[targetIndex];
    if (!target) return null;

    const punchLines = [
      "Chaos picks favorites. This could be your lucky click.",
      "Devil whispers: this one smells like a right answer.",
      "I lit this option for you. Try it if you dare.",
      "When logic shakes, this one may still stand.",
      "Take the hint. Devil rarely repeats himself.",
    ];
    let punchIndex = stableRange("mirageHighlight_punch", 0, punchLines.length - 1);
    if (punchLines.length > 1 && punchIndex === state.lastMiragePunchIndex) {
      punchIndex = (punchIndex + 1) % punchLines.length;
    }
    state.lastMiragePunchIndex = punchIndex;

    const cloud = document.createElement("div");
    cloud.className = "stress-devil-cloud";
    cloud.setAttribute("role", "status");
    cloud.setAttribute("aria-live", "polite");
    cloud.innerHTML = `
      <div class="stress-devil-avatar" aria-hidden="true">😈</div>
      <div class="stress-devil-bubble">
        <strong>Devil says</strong>
        <span>This option may be correct.</span>
        <em>${escapeHTML(punchLines[punchIndex])}</em>
      </div>
    `;

    target.classList.add("stress-mirage");
    target.appendChild(cloud);
    return {
      durationMs: stableRange("mirageHighlight_duration", 2200, 3400),
      cleanup: () => {
        target.classList.remove("stress-mirage");
        cloud.remove();
      },
    };
  }

  function triggerBlurAttack() {
    const taunts = [
      "Why can't you see? You're already losing. 😂",
      "Devil can control your vision. Keep up if you can. 😂",
      "Blurred focus, blurred score. Are you still in this? 😂",
      "Vision fading, pressure rising. Beat it if you dare. 😂",
    ];
    const taunt = taunts[stableRange("blurAttack_taunt", 0, taunts.length - 1)];
    const topBanner = mountDevilTopBanner({
      title: "Vision Hijack",
      lead: "I blurred your sight to break your rhythm.",
      challenge: "Can you solve it when clarity starts fading?",
      taunt,
    });

    const layer = document.createElement("div");
    layer.className = "stress-vignette";
    document.body.appendChild(layer);
    document.body.classList.add("stress-blur-attack");
    return {
      durationMs: 5000,
      cleanup: () => {
        document.body.classList.remove("stress-blur-attack");
        layer.remove();
        topBanner.remove();
      },
    };
  }

  function triggerTorchlightSpotlight(ctx) {
    if (!questionBody || !state.currentQuestionId) return null;
    const qid = String(state.currentQuestionId || "");
    let rect = questionBody.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;

    const host = document.createElement("div");
    host.className = "stress-torchlight-mask";
    document.body.appendChild(host);

    const defaultTaunts = [
      "Read in fragments. Decide under pressure.",
      "Only a sliver at a time — stop whining.",
      "Chase the beam before it moves again.",
      "Full view? You didn't earn that.",
    ];
    const taunts = Array.isArray(ctx?.taunts) && ctx.taunts.length ? ctx.taunts : defaultTaunts;
    const taunt = String(ctx?.spotlightTaunt || "").trim()
      || taunts[stableRange("torchlightSpotlight_taunt", 0, taunts.length - 1)];
    const topBanner = mountDevilTopBanner({
      title: String(ctx?.spotlightTitle || "Narrow beam"),
      lead: String(ctx?.spotlightLead || "Most of the question stays dark."),
      challenge: String(ctx?.spotlightChallenge || "Follow the light. Answer anyway."),
      taunt,
    });

    let captionEl = null;
    const captionText = String(ctx?.caption || ctx?.hintLine || "").trim();
    if (captionText) {
      captionEl = document.createElement("div");
      captionEl.className = "stress-torchlight-caption";
      captionEl.textContent = captionText;
      document.body.appendChild(captionEl);
    }

    let rafId = null;
    let monitorTimer = null;
    let resizeObserver = null;
    let pendingLayoutSync = false;
    let currentX = Math.max(80, rect.width * 0.5);
    let currentY = Math.max(80, rect.height * 0.35);
    let fromX = currentX;
    let fromY = currentY;
    let targetX = currentX;
    let targetY = currentY;
    let segmentStartedAt = 0;
    let segmentDuration = 1400;
    const innerMargin = 28;
    const baseRadiusPx = Math.max(165, Math.min(280, Math.round(Math.min(rect.width, rect.height) * 0.48)));
    let routeStep = 0;
    host.style.setProperty("--torch-radius", `${baseRadiusPx}px`);

    function syncMaskToQuestionBox() {
      rect = questionBody.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      host.style.left = `${Math.round(rect.left)}px`;
      host.style.top = `${Math.round(rect.top)}px`;
      host.style.width = `${Math.round(rect.width)}px`;
      host.style.height = `${Math.round(rect.height)}px`;
      currentX = clamp(currentX, innerMargin, Math.max(innerMargin + 1, rect.width - innerMargin));
      currentY = clamp(currentY, innerMargin, Math.max(innerMargin + 1, rect.height - innerMargin));
      fromX = clamp(fromX, innerMargin, Math.max(innerMargin + 1, rect.width - innerMargin));
      fromY = clamp(fromY, innerMargin, Math.max(innerMargin + 1, rect.height - innerMargin));
      targetX = clamp(targetX, innerMargin, Math.max(innerMargin + 1, rect.width - innerMargin));
      targetY = clamp(targetY, innerMargin, Math.max(innerMargin + 1, rect.height - innerMargin));
      host.style.setProperty("--torch-x", `${Math.round(currentX)}px`);
      host.style.setProperty("--torch-y", `${Math.round(currentY)}px`);
    }

    function queueLayoutSync() {
      if (pendingLayoutSync) return;
      pendingLayoutSync = true;
      requestAnimationFrame(() => {
        pendingLayoutSync = false;
        syncMaskToQuestionBox();
      });
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function centerWithinHost(nodeRect) {
      const minX = innerMargin;
      const maxX = Math.max(minX + 1, rect.width - innerMargin);
      const minY = innerMargin;
      const maxY = Math.max(minY + 1, rect.height - innerMargin);
      const x = nodeRect.left - rect.left + (nodeRect.width * 0.5);
      const y = nodeRect.top - rect.top + (nodeRect.height * 0.5);
      return {
        x: clamp(x, minX, maxX),
        y: clamp(y, minY, maxY),
      };
    }

    function buildFocusAnchors() {
      let stemAnchors = [];
      const optionAnchors = [];
      let selectedAnchor = null;
      let submitAnchor = null;
      let integerAnchor = null;
      const stemRect = questionStem?.getBoundingClientRect();
      if (stemRect && stemRect.width > 10 && stemRect.height > 10) {
        const toAnchor = (xRatio, yRatio, radiusMult = 1.22, travelMs = [900, 1500]) => {
          const px = stemRect.left - rect.left + (stemRect.width * xRatio);
          const py = stemRect.top - rect.top + (stemRect.height * yRatio);
          return {
            x: clamp(px, innerMargin, Math.max(innerMargin + 1, rect.width - innerMargin)),
            y: clamp(py, innerMargin, Math.max(innerMargin + 1, rect.height - innerMargin)),
            radiusMult,
            travelMs,
          };
        };

        // Sweep the question as a line/region (includes top-left corner).
        stemAnchors = [
          toAnchor(0.05, 0.12, 1.26, [1000, 1700]), // top-left
          toAnchor(0.35, 0.14, 1.24, [900, 1500]),  // upper-left/center
          toAnchor(0.68, 0.14, 1.24, [900, 1500]),  // upper-right/center
          toAnchor(0.94, 0.16, 1.22, [900, 1500]),  // top-right
          toAnchor(0.08, 0.48, 1.2, [1000, 1600]),  // mid-left for long questions
          toAnchor(0.52, 0.52, 1.18, [1000, 1600]), // center body line
        ];
      }

      const optionNodes = Array.from(questionOptions?.querySelectorAll("label.option") || []);
      optionNodes.slice(0, 6).forEach((node) => {
        const nodeRect = node.getBoundingClientRect();
        if (nodeRect.width < 10 || nodeRect.height < 10) return;
        const c = centerWithinHost(nodeRect);
        optionAnchors.push({ x: c.x, y: c.y, radiusMult: 1.04, travelMs: [900, 1500] });
      });

      const selectedLabel = String(selectedOptions[qid] || "").trim();
      if (selectedLabel) {
        const selectedNode = questionOptions
          ?.querySelector(`label.option input[value="${selectedLabel}"]`)
          ?.closest("label.option");
        const selectedRect = selectedNode?.getBoundingClientRect();
        if (selectedRect && selectedRect.width > 10 && selectedRect.height > 10) {
          const c = centerWithinHost(selectedRect);
          selectedAnchor = { x: c.x, y: c.y, radiusMult: 1.1, travelMs: [900, 1300] };
        }
      }

      const submitRect = btnSubmitQuestion?.getBoundingClientRect();
      if (submitRect && submitRect.width > 10 && submitRect.height > 10) {
        const c = centerWithinHost(submitRect);
        submitAnchor = { x: c.x, y: c.y, radiusMult: 1.0, travelMs: [1000, 1500] };
      }

      const integerVisible = integerPanel && !integerPanel.hidden && getComputedStyle(integerPanel).display !== "none";
      if (integerVisible) {
        const intRect = integerPanel.getBoundingClientRect();
        if (intRect.width > 10 && intRect.height > 10) {
          const c = centerWithinHost(intRect);
          integerAnchor = { x: c.x, y: c.y, radiusMult: 1.18, travelMs: [1100, 1700] };
        }
      }

      const fallbackAnchor = {
          x: clamp(rect.width * 0.5, innerMargin, Math.max(innerMargin + 1, rect.width - innerMargin)),
          y: clamp(rect.height * 0.38, innerMargin, Math.max(innerMargin + 1, rect.height - innerMargin)),
          radiusMult: 1.1,
          travelMs: [1000, 1700],
        };

      return {
        stemAnchors,
        optionAnchors,
        selectedAnchor,
        submitAnchor,
        integerAnchor,
        fallbackAnchor,
      };
    }

    function pickAnchor() {
      const focus = buildFocusAnchors();
      const stemSweep = (focus.stemAnchors && focus.stemAnchors.length)
        ? focus.stemAnchors
        : [focus.fallbackAnchor];
      const stemPrimary = stemSweep[0] || focus.fallbackAnchor;
      const options = focus.optionAnchors || [];
      const route = [];

      if (focus.integerAnchor) {
        route.push(...stemSweep, focus.integerAnchor, stemPrimary);
        if (focus.selectedAnchor) route.push(focus.selectedAnchor);
        if (focus.submitAnchor) route.push(stemPrimary, focus.submitAnchor);
      } else {
        route.push(...stemSweep);
        if (options[0]) route.push(options[0]);
        if (options[1]) route.push(options[1]);
        route.push(stemPrimary);
        if (stemSweep[2]) route.push(stemSweep[2]);
        if (stemSweep[4]) route.push(stemSweep[4]);
        if (options[2]) route.push(options[2]);
        if (options[3]) route.push(options[3]);
        if (focus.selectedAnchor) route.push(stemPrimary, focus.selectedAnchor);
        if (focus.submitAnchor) route.push(stemPrimary, focus.submitAnchor);
      }

      const finalRoute = route.filter(Boolean);
      if (!finalRoute.length) return focus.fallbackAnchor;
      const anchor = finalRoute[routeStep % finalRoute.length];
      routeStep += 1;
      return anchor;
    }

    function chooseTarget(ts, force = false) {
      if (!force && segmentStartedAt && ts - segmentStartedAt < segmentDuration) return;
      const anchor = pickAnchor();
      if (!anchor) return;
      fromX = currentX;
      fromY = currentY;
      targetX = anchor.x;
      targetY = anchor.y;
      const minTravel = Number(anchor.travelMs?.[0] || 1000);
      const maxTravel = Number(anchor.travelMs?.[1] || 1700);
      segmentDuration = minTravel + Math.floor(Math.random() * Math.max(1, maxTravel - minTravel + 1));
      segmentStartedAt = ts || performance.now();
      const adaptiveRadius = clamp(
        Math.round(baseRadiusPx * Number(anchor.radiusMult || 1)),
        Math.max(145, Math.round(baseRadiusPx * 0.9)),
        Math.round(baseRadiusPx * 1.45)
      );
      host.style.setProperty("--torch-radius", `${adaptiveRadius}px`);
    }

    function tick(ts) {
      if ((routeStep % 30) === 0) {
        syncMaskToQuestionBox();
      }
      chooseTarget(ts, false);
      const elapsed = Math.max(0, ts - segmentStartedAt);
      const progress = clamp(elapsed / Math.max(1, segmentDuration), 0, 1);
      // Smooth "readable" glide: quick settle at start, slower near destination.
      const eased = 1 - ((1 - progress) ** 3);
      currentX = fromX + ((targetX - fromX) * eased);
      currentY = fromY + ((targetY - fromY) * eased);

      host.style.setProperty("--torch-x", `${Math.round(currentX)}px`);
      host.style.setProperty("--torch-y", `${Math.round(currentY)}px`);

      if (progress >= 1) {
        chooseTarget(ts, true);
      }
      rafId = requestAnimationFrame(tick);
    }

    syncMaskToQuestionBox();
    chooseTarget(performance.now(), true);
    rafId = requestAnimationFrame(tick);
    window.addEventListener("resize", queueLayoutSync);
    window.addEventListener("orientationchange", queueLayoutSync);
    document.addEventListener("fullscreenchange", queueLayoutSync);
    if (typeof ResizeObserver === "function") {
      resizeObserver = new ResizeObserver(() => queueLayoutSync());
      resizeObserver.observe(questionBody);
    }

    monitorTimer = setInterval(() => {
      const movedToAnotherQuestion = String(state.currentQuestionId || "") !== qid;
      // Removed hasAnswer check - torchlight should continue even if option is selected
      if (movedToAnotherQuestion) {
        deactivateTrigger("torchlightSpotlight");
      }
    }, 180);

    return {
      durationMs: 0,
      cleanup: () => {
        if (rafId) cancelAnimationFrame(rafId);
        if (monitorTimer) clearInterval(monitorTimer);
        window.removeEventListener("resize", queueLayoutSync);
        window.removeEventListener("orientationchange", queueLayoutSync);
        document.removeEventListener("fullscreenchange", queueLayoutSync);
        if (resizeObserver) resizeObserver.disconnect();
        host.remove();
        topBanner.remove();
        if (captionEl) captionEl.remove();
      },
    };
  }

  function triggerHeartbeatVibration() {
    const shell = getAppShell();
    const lines = [
      "Keep your head steady. Panic is my playground.",
      "If your pulse leads, your logic follows it off a cliff.",
      "Breathe. Then answer. Speed without control is mine.",
      "A faster heart is fine. A rushed mind is fatal.",
    ];
    const taunt = lines[stableRange("heartbeatVibration_line", 0, lines.length - 1)];
    const banner = mountDevilTopBanner({
      title: "Devil Notice",
      lead: "Devil noticed that your heartbeat has increased a bit.",
      challenge: "Let's test your strength... can you answer beating that much faster?",
      taunt,
    });

    const focusFog = document.createElement("div");
    focusFog.className = "stress-heartbeat-focus";

    document.body.appendChild(focusFog);
    document.body.appendChild(banner);
    shell?.classList.add("stress-heartbeat");
    if (navigator.vibrate) {
      try {
        navigator.vibrate([130, 50, 150, 50, 170, 70, 130]);
      } catch (e) {
        // no-op
      }
    }
    return {
      durationMs: stableRange("heartbeatVibration_duration", 6500, 11000),
      cleanup: () => {
        shell?.classList.remove("stress-heartbeat");
        focusFog.remove();
        banner.remove();
      },
    };
  }

  // ── AI Student Companion Card (shown before Q1 torchlightSpotlight) ───────
  // Uses the same hard-question-fullscreen pattern — one single screen,
  // insight + stat (when relevant) combined, minimal layout.

  async function showCompanionCard(onComplete, prefetchedData) {
    // Prevent double-trigger with global activation guard
    if (showCompanionCard._active) {
      console.warn("[showCompanionCard] Already active, skipping duplicate call");
      return;
    }
    // Block if test has ended
    if (state.stage === "results" || !isTestActive) {
      console.log("[showCompanionCard] Blocked — test ended");
      if (onComplete) onComplete();
      return;
    }
    showCompanionCard._active = true;

    const studentName = window.StressDostAuth?.getUser?.()?.display_name || "";
    const initialText = lastAnswerEcho || $("initialText")?.value || "";
    const followupAnswers = (state.followupAnswers || []).slice(-4);

    console.log("[showCompanionCard] Starting — initialText:", initialText.substring(0, 50));

    // Scene → background gradient (mirrors hard-question-fullscreen palette)
    const SCENE_BG = {
      habit_insight: "radial-gradient(circle at 50% 30%, rgba(120,53,15,0.55), rgba(0,0,0,0.96) 68%), linear-gradient(180deg,rgba(2,8,23,0.98),rgba(0,0,0,0.98))",
      focus_insight: "radial-gradient(circle at 50% 30%, rgba(14,60,110,0.5), rgba(0,0,0,0.95) 68%), linear-gradient(180deg,rgba(2,8,23,0.98),rgba(0,0,0,0.98))",
      motivation:    "radial-gradient(circle at 50% 30%, rgba(127,29,29,0.5), rgba(0,0,0,0.95) 68%), linear-gradient(180deg,rgba(8,4,8,0.98),rgba(0,0,0,0.98))",
      productivity:  "radial-gradient(circle at 50% 30%, rgba(6,78,59,0.45), rgba(0,0,0,0.95) 68%), linear-gradient(180deg,rgba(2,8,23,0.98),rgba(0,0,0,0.98))",
      quick_concept: "radial-gradient(circle at 50% 30%, rgba(14,60,110,0.5), rgba(0,0,0,0.95) 68%), linear-gradient(180deg,rgba(2,8,23,0.98),rgba(0,0,0,0.98))",
      casual_chat:   "radial-gradient(circle at 50% 30%, rgba(49,46,129,0.45), rgba(0,0,0,0.95) 68%), linear-gradient(180deg,rgba(2,8,23,0.98),rgba(0,0,0,0.98))",
    };

    // Scene → eyebrow accent colour
    const SCENE_COLOR = {
      habit_insight: "rgba(251,191,36,0.95)",
      focus_insight: "rgba(167,139,250,0.95)",
      motivation:    "rgba(248,113,113,0.95)",
      productivity:  "rgba(52,211,153,0.95)",
      quick_concept: "rgba(96,165,250,0.95)",
      casual_chat:   "rgba(167,139,250,0.95)",
    };

    // Show fullscreen overlay with loading dots (always shows for 1s minimum)
    const overlay = document.createElement("div");
    overlay.className = "hard-question-fullscreen is-intro";
    overlay.style.cssText = "position:fixed;inset:0;z-index:9998;display:flex;align-items:center;justify-content:center;background:#000;";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML = `
      <div style="display:flex;gap:10px;align-items:center;">
        <span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.4);animation:cmpDot 1.2s ease infinite;"></span>
        <span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.4);animation:cmpDot 1.2s ease 0.2s infinite;"></span>
        <span style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.4);animation:cmpDot 1.2s ease 0.4s infinite;"></span>
      </div>
      <style>@keyframes cmpDot{0%,80%,100%{opacity:0.25;transform:scale(0.8);}40%{opacity:1;transform:scale(1.3);}}</style>
    `;
    document.body.appendChild(overlay);

    // Use prefetched data or fetch fresh
    let data = (prefetchedData && prefetchedData.scene) ? prefetchedData : null;
    if (!data) {
      try {
        const resp = await fetch("/api/triggers/companion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: initialText,
            student_name: studentName,
            initial_text: initialText,
            followup_answers: followupAnswers,
          }),
          signal: AbortSignal.timeout(4000),
        });
        if (resp.ok) {
          data = await resp.json();
          console.log("[showCompanionCard] AI response — scene:", data.scene, "source:", data.source);
        } else {
          console.warn("[showCompanionCard] API error:", resp.status);
        }
      } catch (err) {
        console.warn("[showCompanionCard] Fetch failed:", err.message);
      }
    } else {
      console.log("[showCompanionCard] Using prefetched data — scene:", data.scene);
    }

    // Always show loading dots for at least 1 second (feels intentional, not laggy)
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Fallback
    if (!data || !data.scene) {
      console.log("[showCompanionCard] Using fallback response");
      data = {
        scene: "focus_insight", icon: "🎯", label: "THE NUMBERS",
        lines: ["1.36% selection rate. Same syllabus for everyone. The only variable is how you spend the next 4 hours."],
        fact: "Students who cut phone time by 2 hrs/day improved mock scores by 18-22%.",
        question: null,
        stat_card: null,
      };
    }

    const bg    = SCENE_BG[data.scene]    || SCENE_BG.focus_insight;
    const color = SCENE_COLOR[data.scene] || SCENE_COLOR.focus_insight;
    overlay.style.background = "#000";

    // Premium emoji per scene (not generic AI emojis)
    const SCENE_EMOJI = {
      habit_insight: "◉",
      focus_insight: "◈",
      motivation: "↯",
      productivity: "⬡",
      quick_concept: "△",
      casual_chat: "○",
    };
    const sceneEmoji = SCENE_EMOJI[data.scene] || "◉";

    // Main line and fact
    const mainLine = (data.lines && data.lines[0]) ? escapeHTML(String(data.lines[0])) : "";
    const factLine = data.fact ? escapeHTML(String(data.fact)) : "";
    const sc = data.stat_card;

    // Build stat section
    const statHTML = sc ? `
      <div class="cmp-f2" style="opacity:0;transform:translateY(6px);margin-top:28px;width:100%;max-width:400px;text-align:left;">
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px;">
          <span style="font-size:44px;font-weight:800;color:#fff;letter-spacing:-1.5px;line-height:1;">${escapeHTML(String(sc.value))}</span>
          <span style="font-size:14px;color:rgba(255,255,255,0.45);text-transform:uppercase;letter-spacing:0.1em;font-weight:600;">${escapeHTML(String(sc.headline))}</span>
        </div>
        <div style="font-size:16px;color:rgba(255,255,255,0.55);line-height:1.5;margin-bottom:10px;font-weight:500;">${escapeHTML(String(sc.subtext || ""))}</div>
        <div style="font-size:16px;color:${color};line-height:1.5;font-weight:600;">${escapeHTML(String(sc.mirror || ""))}</div>
        ${sc.source ? `<div style="font-size:11px;color:rgba(255,255,255,0.25);margin-top:12px;letter-spacing:0.12em;text-transform:uppercase;font-weight:500;">— ${escapeHTML(String(sc.source))}</div>` : ""}
      </div>` : "";

    // Render
    overlay.innerHTML = `
      <div style="
        display:flex;flex-direction:column;align-items:center;justify-content:center;
        text-align:center;padding:44px 24px;max-width:480px;width:100%;
        opacity:0;transition:opacity 0.3s ease;
      " id="cmpContent">
        
        <div style="font-size:42px;color:${color};margin-bottom:28px;opacity:0.7;line-height:1;">${sceneEmoji}</div>
        
        <div style="font-size:14px;letter-spacing:0.22em;text-transform:uppercase;color:${color};font-weight:700;margin-bottom:28px;">${escapeHTML(String(data.label || "INSIGHT"))}</div>
        
        ${mainLine ? `<div class="cmp-f1" style="
          font-size:26px;font-weight:600;color:rgba(255,255,255,0.92);
          line-height:1.6;margin-bottom:22px;
          opacity:0;transform:translateY(6px);
        ">${mainLine}</div>` : ""}
        
        ${factLine && !sc ? `<div class="cmp-f2" style="
          font-size:18px;color:${color};font-weight:600;
          line-height:1.6;
          opacity:0;transform:translateY(6px);
        ">${factLine}</div>` : ""}
        
        ${statHTML}
        
        <button id="cmpFsBtn" type="button" class="cmp-f3" style="
          margin-top:40px;padding:16px 36px;
          background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
          border-radius:8px;color:rgba(255,255,255,0.7);
          font-size:16px;font-weight:600;cursor:pointer;
          transition:all 0.2s;letter-spacing:0.02em;
          opacity:0;transform:translateY(6px);
        " onmouseover="this.style.background='rgba(255,255,255,0.09)';this.style.color='rgba(255,255,255,0.95)'"
           onmouseout="this.style.background='rgba(255,255,255,0.05)';this.style.color='rgba(255,255,255,0.7)'"
        >Continue</button>
      </div>
    `;

    // Smooth reveal
    requestAnimationFrame(() => {
      const content = overlay.querySelector("#cmpContent");
      if (content) content.style.opacity = "1";
      
      setTimeout(() => {
        const el = overlay.querySelector(".cmp-f1");
        if (el) { el.style.transition = "opacity 0.35s ease, transform 0.35s ease"; el.style.opacity = "1"; el.style.transform = "translateY(0)"; }
      }, 100);
      
      setTimeout(() => {
        const el = overlay.querySelector(".cmp-f2");
        if (el) { el.style.transition = "opacity 0.35s ease, transform 0.35s ease"; el.style.opacity = "1"; el.style.transform = "translateY(0)"; }
      }, 250);
      
      setTimeout(() => {
        const el = overlay.querySelector(".cmp-f3");
        if (el) { el.style.transition = "opacity 0.35s ease, transform 0.35s ease"; el.style.opacity = "1"; el.style.transform = "translateY(0)"; }
      }, 400);
    });

    // Dismiss handler with double-trigger protection
    let dismissed = false;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      clearTimeout(autoTimer);
      showCompanionCard._active = false; // Release global lock
      
      console.log("[showCompanionCard] Dismissing, calling onComplete");
      overlay.style.opacity = "0";
      overlay.style.transition = "opacity 280ms ease";
      setTimeout(() => { 
        overlay.remove(); 
        if (onComplete) onComplete(); 
      }, 300);
    };

    // Auto-dismiss after 15s (reduced from 20s for better pacing)
    const autoTimer = setTimeout(dismiss, 15000);

    // Button click listener
    const btn = overlay.querySelector("#cmpFsBtn");
    if (btn) btn.addEventListener("click", dismiss);
  }

  // ── Personalized "You Said This" Quiz (shown before Q3 screenFlip) ────────

  /**
   * Extract the single most emotionally resonant keyword from the user's
   * initial text + follow-up answers, then return a reflection sentence and
   * a psychologically connected yes/no question.
   */
  function buildPersonalizedQuizPrompt() {
    const initialRaw = lastAnswerEcho || $("initialText")?.value || "";
    const followups  = (state.followupAnswers || []).map(f => f.answer || "").join(" ");
    const combined   = (initialRaw + " " + followups).toLowerCase();

    // Keyword → personalized topic + prompt copy
    const patterns = [
      {
        words: ["stress", "stressed", "pressure", "overwhelm"],
        topic: "stress and pressure",
        reflection: "You mentioned pressure can disrupt your focus in key moments.",
        question:   "Do you want to check how that pressure is affecting your current accuracy?",
      },
      {
        words: ["instagram", "reel", "reels", "distract", "distraction", "phone", "scroll", "notification"],
        topic: "Instagram reels and phone distractions",
        reflection: "I know you get distracted by Instagram reels.",
        question:   "Top IITs like IIT Bombay and IIT Kharagpur are not for people who keep feeding distractions 📉. They are for deep focus, discipline, and consistency every day 🔥. Still want to test your real accuracy now?",
      },
      {
        words: ["focus", "concentrate", "concentration", "attention"],
        topic: "focus consistency",
        reflection: "You mentioned maintaining focus is difficult when the stakes rise.",
        question:   "Should we test how this affects your question accuracy right now?",
      },
      {
        words: ["overthink", "overthinking", "mind", "thought", "mental"],
        topic: "overthinking",
        reflection: "You mentioned overthinking slows your decision speed under pressure.",
        question:   "Do you want to test whether this is reducing your accuracy today?",
      },
      {
        words: ["tired", "fatigue", "sleep", "exhausted", "drain"],
        topic: "mental fatigue",
        reflection: "You said mental fatigue can reduce clarity while solving questions.",
        question:   "Do you want to check how this is affecting your current performance?",
      },
      {
        words: ["miss", "detail", "mistake", "error", "overlook"],
        topic: "missing details",
        reflection: "You mentioned you sometimes miss small details while solving.",
        question:   "Should we test if this is currently affecting your score accuracy?",
      },
      {
        words: ["exam", "test", "paper", "deadline", "marks", "score"],
        topic: "exam pressure",
        reflection: "You mentioned exam pressure sometimes clouds your judgement.",
        question:   "Do you want to test how much this pressure impacts your accuracy now?",
      },
    ];

    for (const p of patterns) {
      if (p.words.some(w => combined.includes(w))) {
        return { topic: p.topic, reflection: p.reflection, question: p.question, sourceText: combined };
      }
    }

    // Generic fallback
    return {
      topic: "focus and distractions",
      reflection: "You mentioned focus challenges can affect your consistency.",
      question:   "Do you want to test how this is affecting your accuracy right now?",
      sourceText: combined,
    };
  }

  function inferDistractionSeverity(text, followupCount) {
    const src = String(text || "").toLowerCase();
    const heavySignals = [
      "all day", "whole day", "every time", "cannot stop", "can't stop", "addicted",
      "reels", "instagram", "shorts", "binge", "hours", "late night", "procrastinate",
    ];
    const mediumSignals = [
      "distract", "distraction", "phone", "scroll", "notification", "waste time",
      "delay", "postpone", "break focus", "lose focus",
    ];

    let score = 0;
    heavySignals.forEach((k) => { if (src.includes(k)) score += 2; });
    mediumSignals.forEach((k) => { if (src.includes(k)) score += 1; });
    score += Math.min(3, Number(followupCount || 0));

    if (score >= 10) return "brutal";
    if (score >= 6) return "hard";
    return "medium";
  }

  function summarizeDistractionTopic(rawAnswer, fallbackTopic) {
    const src = String(rawAnswer || "").toLowerCase();
    if (!src) return String(fallbackTopic || "distractions");
    if (src.includes("instagram") || src.includes("reel")) return "Instagram reels";
    if (src.includes("youtube") || src.includes("shorts")) return "YouTube shorts";
    if (src.includes("whatsapp") || src.includes("chat")) return "chat notifications";
    if (src.includes("game")) return "mobile gaming";
    if (src.includes("sleep") || src.includes("late night")) return "late-night screen time";
    if (src.includes("phone") || src.includes("scroll")) return "phone scrolling";
    return String(fallbackTopic || "distractions");
  }

  function getSessionInitialQuery() {
    return String(sessionInitialQuery || $("initialText")?.value || "").trim();
  }

  function extractLiteralPopupTopic(rawInitial, rawFollowup, fallbackTopic) {
    const clean = (value) =>
      String(value || "")
        .replace(/\s+/g, " ")
        .replace(/^[,.;:\-\s]+|[,.;:\-\s]+$/g, "")
        .trim();

    const candidates = [rawInitial, rawFollowup]
      .map(clean)
      .filter(Boolean);

    for (const candidate of candidates) {
      const words = candidate.split(/\s+/).filter(Boolean);
      if (words.length >= 1 && words.length <= 8 && candidate.length <= 80) {
        return candidate;
      }
    }

    return clean(fallbackTopic) || "distractions";
  }

  /**
   * Show the full personalized quiz overlay.
   * Calls onComplete() after the user dismisses the response popup.
   */
  function buildQ1WarningCopy() {
    const rawInitial = getSessionInitialQuery();
    const initialSnippet = rawInitial
      .split(/\s+/)
      .slice(0, 12)
      .join(" ");
    const subjectLine = summarizeDistractionTopic(rawInitial, rawInitial || "distractions");
    const severity = inferDistractionSeverity(rawInitial, 0);
    const literalTopic = extractLiteralPopupTopic(initialSnippet, "", subjectLine);
    const topicLead = literalTopic ? `"${literalTopic}"` : subjectLine;
    const reelRoast = /reel|instagram|shorts|scroll|phone/i.test(`${rawInitial} ${literalTopic} ${subjectLine}`);
    const lines = {
      medium: reelRoast
        ? `${topicLead} already has more grip on your attention than this paper does.`
        : `${topicLead} is already crowding the space where your focus should have been.`,
      hard: reelRoast
        ? `${topicLead} keeps getting fed, and your discipline keeps showing up hungry.`
        : `${topicLead} walked into the test before your discipline did, and it shows.`,
      brutal: reelRoast
        ? `${topicLead} is not harmless entertainment. It is the leak in your discipline, and this paper will expose it fast.`
        : `${topicLead} already owns part of your mind. Leave it there and your rank will get punished honestly.`,
    };
    const subs = {
      medium: `The stem is on screen, but ${topicLead} is still getting the better seat in your head.`,
      hard: `A stronger student would have left ${topicLead} outside the hall. You brought it in and called it harmless.`,
      brutal: `If ${topicLead} still feels bigger than the question stem, the score will read exactly like your priorities.`,
    };
    return {
      headline: lines[severity] || lines.medium,
      sub: subs[severity] || subs.medium,
    };
  }

  function getQuestionWarningInputs(questionNumber) {
    const initialText = getSessionInitialQuery();
    const followupAnswers = Array.isArray(state.followupAnswers)
      ? state.followupAnswers
          .slice(0, 2)
          .map((item) => String(item?.answer || "").trim())
          .filter(Boolean)
      : [];
    const contextParts = questionNumber <= 2
      ? [initialText]
      : [initialText, ...followupAnswers];
    return {
      initialText,
      followupAnswers,
      contextParts: contextParts.filter(Boolean),
      combinedContext: contextParts.filter(Boolean).join(" | "),
    };
  }

  function getQuestionWarningPresentation(questionNumber) {
    const map = {
      1: { label: "Reality check", icon: "🚨" },
      2: { label: "Damage report", icon: "💀" },
      3: { label: "Pattern exposed", icon: "😈" },
      4: { label: "Focus decay", icon: "🩸" },
      5: { label: "No hiding", icon: "🔥" },
      6: { label: "Weakness spotted", icon: "☠️" },
      7: { label: "Final blow", icon: "👁️" },
    };
    return map[questionNumber] || map[1];
  }

  function getQuestionWarningCacheKey(questionNumber) {
    const normalizedQuestionNumber = Number(questionNumber || 1);
    const { initialText, followupAnswers } = getQuestionWarningInputs(normalizedQuestionNumber);
    return JSON.stringify({
      questionNumber: normalizedQuestionNumber,
      initialText,
      followupAnswers,
    });
  }

  function extractNamedPersonFromText(rawText) {
    const text = String(rawText || "").trim();
    if (!text) return "";
    const cleaned = text
      .replace(/\b(?:reels?|shorts?|movies?|movie|videos?|video|songs?|edits?|photos?|pics?|images?|and|with|of|about|on|watching|watch)\b/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleaned) return "";
    const parts = cleaned.split(/\s+/).filter(Boolean);
    if (parts.length >= 1 && parts.length <= 4) {
      return parts.join(" ");
    }
    return "";
  }

  function detectMediaCue(rawText) {
    const text = String(rawText || "").toLowerCase();
    if (/\breels?\b|\bshorts?\b/.test(text)) return "reels";
    if (/\bmovies?\b|\bmovie\b/.test(text)) return "movies";
    if (/\bedits?\b/.test(text)) return "edits";
    if (/\bvideos?\b|\bvideo\b/.test(text)) return "videos";
    return "";
  }

  function buildQuestionWarningFallbackCopy(questionNumber) {
    const { initialText, followupAnswers, contextParts } = getQuestionWarningInputs(questionNumber);
    const baseSource = contextParts.join(" | ") || initialText || "your distraction";
    const fallbackTopic = summarizeDistractionTopic(baseSource, initialText || "your distraction");
    const literalTopic = extractLiteralPopupTopic(
      questionNumber <= 2 ? initialText : contextParts.join(", "),
      questionNumber <= 2 ? "" : followupAnswers.join(", "),
      fallbackTopic
    );
    const topicLead = literalTopic ? `"${literalTopic}"` : fallbackTopic;
    const second = followupAnswers[0] ? `"${followupAnswers[0]}"` : "the same weakness";
    const third = followupAnswers[1] ? `"${followupAnswers[1]}"` : "the excuse you keep feeding";
    const personName = extractNamedPersonFromText(initialText);
    const mediaCue = detectMediaCue(initialText);

    if (personName) {
      const personCopyMap = {
        1: {
          headline: `${personName} is moving ahead in life. You're still giving away attention like it costs you nothing.`,
          sub: "",
        },
        2: {
          headline: `${personName} does not know you exist, but your focus is still working harder for ${personName} than for you.`,
          sub: "",
        },
        3: {
          headline: `${personName}, ${second}, and now ${third} make it look like distraction is not the problem. You are.`,
          sub: "",
        },
        4: {
          headline: `${personName} got the attention, ${second} kept it alive, and ${third} made the weakness obvious to anyone watching.`,
          sub: "",
        },
        5: {
          headline: `At this point ${personName} is just the surface. ${second} and ${third} are the real reason your focus keeps folding.`,
          sub: "",
        },
        6: {
          headline: `${personName}, ${second}, and ${third} together make your priorities look embarrassingly easy to read.`,
          sub: "",
        },
        7: {
          headline: `${personName} was the bait. ${second} lowered your guard. ${third} finished the job and left your focus looking cheap.`,
          sub: "",
        },
      };

      if (mediaCue === "reels" && questionNumber <= 2) {
        personCopyMap[1].headline = `${personName} is building a career while you sit here feeding reels and calling it harmless.`;
        personCopyMap[2].headline = `${personName} does not know you exist. The reels still get your time, and your own work gets whatever is left.`;
      }
      if (mediaCue === "movies" && questionNumber <= 2) {
        personCopyMap[1].headline = `${personName} keeps moving forward. You keep sitting still and calling it entertainment.`;
        personCopyMap[2].headline = `${personName} is not ruining your focus. You're the one choosing fantasy over your own work again.`;
      }

      return personCopyMap[questionNumber] || personCopyMap[1];
    }

    const copyMap = {
      1: {
        headline: `${topicLead} is already getting more of your attention than the question in front of you.`,
        sub: "",
      },
      2: {
        headline: `${topicLead} looks small until you notice how easily it keeps pulling you away from your own life.`,
        sub: "",
      },
      3: {
        headline: `${topicLead}, ${second}, and ${third} together make this look less like bad luck and more like your usual pattern.`,
        sub: "",
      },
      4: {
        headline: `${topicLead} got your attention, ${second} kept it there, and ${third} made the habit obvious.`,
        sub: "",
      },
      5: {
        headline: `${topicLead} is the distraction, ${second} is the excuse, and ${third} is what happens when you stop guarding your time.`,
        sub: "",
      },
      6: {
        headline: `${topicLead}, ${second}, and ${third} together make your weak spot look embarrassingly easy to predict.`,
        sub: "",
      },
      7: {
        headline: `${topicLead} took your attention, ${second} lowered your guard, and ${third} finished what was left of your focus.`,
        sub: "",
      },
    };

    return copyMap[questionNumber] || copyMap[1];
  }

  function normalizeQ1WarningResponse(raw, fallbackCopy) {
    const fallback = fallbackCopy || buildQ1WarningCopy();
    const headline = String(raw?.headline || "").replace(/\s+/g, " ").trim();
    const sub = String(raw?.sub || "").replace(/\s+/g, " ").trim();
    if (!headline || !sub) return fallback;
    return { headline, sub };
  }

  function normalizeQuestionWarningResponse(raw, fallbackCopy) {
    const fallback = fallbackCopy || buildQuestionWarningFallbackCopy(1);
    const headline = String(raw?.headline || "").replace(/\s+/g, " ").trim();
    const sub = String(raw?.sub || "").replace(/\s+/g, " ").trim();
    if (!headline) return fallback;
    return { headline, sub };
  }

  async function fetchQ1WarningCopy() {
    return fetchQuestionWarningCopy(1);
  }

  async function fetchQuestionWarningCopy(questionNumber) {
    const normalizedQuestionNumber = Number(questionNumber || 1);
    const fallbackCopy = buildQuestionWarningFallbackCopy(normalizedQuestionNumber);
    const { initialText, followupAnswers } = getQuestionWarningInputs(normalizedQuestionNumber);
    if (!initialText) return fallbackCopy;

    const cacheKey = getQuestionWarningCacheKey(normalizedQuestionNumber);

    if (questionWarningCopyCache.has(cacheKey)) {
      return questionWarningCopyCache.get(cacheKey);
    }

    if (questionWarningCopyPromises.has(cacheKey)) {
      return questionWarningCopyPromises.get(cacheKey);
    }

    const promise = postJSON(
      "/api/triggers/question-warning-copy",
      {
        question_number: normalizedQuestionNumber,
        initial_text: initialText,
        followup_answers: followupAnswers,
      },
      { timeoutMs: 6000 }
    )
      .then((data) => {
        const copy = normalizeQuestionWarningResponse(data, fallbackCopy);
        questionWarningCopyCache.set(cacheKey, copy);
        return copy;
      })
      .catch(() => fallbackCopy)
      .finally(() => {
        questionWarningCopyPromises.delete(cacheKey);
      });

    questionWarningCopyPromises.set(cacheKey, promise);
    return promise;
  }

  async function prefetchQuestionWarningCopies() {
    const initialText = getSessionInitialQuery();
    if (!initialText) return [];
    const jobs = [];
    for (let qNum = 1; qNum <= 7; qNum += 1) {
      jobs.push(fetchQuestionWarningCopy(qNum));
    }
    return Promise.allSettled(jobs);
  }

  function buildQ2PopupCopy() {
    const { topic, sourceText } = buildPersonalizedQuizPrompt();
    const firstFollowupAnswer = String(state.followupAnswers?.[0]?.answer || "").trim();
    const subjectLine = summarizeDistractionTopic(firstFollowupAnswer, topic);
    const severity = inferDistractionSeverity(
      sourceText || "",
      Array.isArray(state.followupAnswers) ? state.followupAnswers.length : 0
    );
    const lines = {
      medium: `Keep this lifestyle — IIT Bombay and IIT Kharagpur aren't reserving seats for ${subjectLine} addicts.`,
      hard: `You won't waltz into IIT KGP or IIT Bombay with this focus. Those campuses chew up disciplined kids — you're still owned by ${subjectLine}.`,
      brutal: `Dream IIT Kharagpur / IIT Bombay all you want. With ${subjectLine} steering your day, you're dead weight in that race — not competition.`,
    };
    const subs = {
      medium: `You're of no use to that dream until habits change. Answer honestly — then a crawling torch owns the question.`,
      hard: `Rank doesn't care about your campus fantasy while ${subjectLine} runs your day. Say yes or no — then the narrow beam hits.`,
      brutal: `Not "almost IIT." Nowhere near that grind. Pick below — partial sight next, same as your half-attention habits.`,
    };
    const { question: personalizedQuestion } = buildPersonalizedQuizPrompt();
    const focusQuestion = /focus|accuracy|test/i.test(String(personalizedQuestion || ""))
      ? personalizedQuestion
      : "Do you want to test your focus and accuracy right now?";
    return {
      headline: lines[severity] || lines.medium,
      sub: subs[severity] || subs.medium,
      focusQuestion,
      subjectLine,
    };
  }

  function dismissPsyqOverlay(overlay, onComplete) {
    overlay.classList.remove("psyq-overlay--visible");
    const dismissMs = overlay?.classList?.contains("psyq-overlay--warning-slow") ? 2200 : 280;
    setTimeout(() => {
      overlay.remove();
      onComplete?.();
    }, dismissMs);
  }

  function showQuestionWarningPopup(questionNumber, onComplete) {
    const qNum = Number(questionNumber || 1);
    const fallbackCopy = buildQuestionWarningFallbackCopy(qNum);
    const cacheKey = getQuestionWarningCacheKey(qNum);
    const resolvedCopy = questionWarningCopyCache.get(cacheKey) || fallbackCopy;

    document.querySelectorAll(".psyq-overlay[data-question-warning='1']").forEach((el) => el.remove());

    const overlay = document.createElement("div");
    overlay.className = "psyq-overlay psyq-overlay--warning-slow";
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("data-question-warning", "1");
    overlay.setAttribute("data-question-number", String(qNum));

    overlay.innerHTML = `
      <div class="psyq-card psyq-card--warning psyq-card--warning-slow psyq-card--minimal" id="psyqCard">
        <button class="psyq-close psyq-close--minimal" id="psyqClose" type="button" aria-label="Close popup">×</button>
        <p class="psyq-reflection" id="psyqReflection"></p>
      </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("psyq-overlay--visible"));

    const reflEl = overlay.querySelector("#psyqReflection");
    const closeBtn = overlay.querySelector("#psyqClose");

    if (reflEl) reflEl.textContent = resolvedCopy.headline || fallbackCopy.headline;

    closeBtn?.addEventListener("click", () => dismissPsyqOverlay(overlay, onComplete));
  }

  function showPersonalizedQuiz(onComplete, opts = {}) {
    const { topic, reflection, question, sourceText } = buildPersonalizedQuizPrompt();
    const mode = opts.mode === "q1" ? "q1" : opts.mode === "q2" ? "q2" : "q3";
    const isCompactCard = mode === "q1";
    const q2Copy = mode === "q2" ? buildQ2PopupCopy() : null;
    const heading = mode === "q1" ? "Reality check" : mode === "q2" ? "Campus fantasy" : "Focus check";
    const firstFollowupAnswer = String(state.followupAnswers?.[0]?.answer || "").trim();
    const severity = inferDistractionSeverity(
      `${sourceText || ""} ${firstFollowupAnswer}`,
      Array.isArray(state.followupAnswers) ? state.followupAnswers.length : 0
    );
    const subjectLine = summarizeDistractionTopic(firstFollowupAnswer, topic);
    const compactCopy = mode === "q1" ? buildQ1WarningCopy() : null;
    const cardIcon = mode === "q1" ? "🚨" : mode === "q2" ? "💀" : "🧠";

    const overlay = document.createElement("div");
    overlay.className = `psyq-overlay${isCompactCard ? " psyq-overlay--warning-slow" : ""}`;
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("role", "dialog");

    overlay.innerHTML = `
      <div class="psyq-card${isCompactCard ? " psyq-card--warning psyq-card--warning-slow" : ""}" id="psyqCard">
        <div class="psyq-header">
          <span class="psyq-icon">${cardIcon}</span>
          <span class="psyq-label">${escapeHTML(heading)}</span>
          ${isCompactCard
            ? `<button class="psyq-close" id="psyqClose" type="button" aria-label="Close popup">×</button>`
            : ``}
        </div>
        <p class="psyq-reflection" id="psyqReflection"></p>
        <div class="psyq-divider"></div>
        <p class="psyq-question" id="psyqQuestion" style="opacity:0;transition:opacity 400ms ease;"></p>
        ${isCompactCard
          ? ``
          : `<div class="psyq-actions" id="psyqActions" style="opacity:0;pointer-events:none;transition:opacity 350ms ease;">
          <button class="psyq-btn psyq-btn-yes" id="psyqYes" type="button">Yes</button>
          <button class="psyq-btn psyq-btn-no"  id="psyqNo"  type="button">No</button>
        </div>`}
      </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("psyq-overlay--visible"));

    const card       = overlay.querySelector("#psyqCard");
    const reflEl     = overlay.querySelector("#psyqReflection");
    const questionEl = overlay.querySelector("#psyqQuestion");
    const actionsEl  = overlay.querySelector("#psyqActions");
    const yesBtn     = overlay.querySelector("#psyqYes");
    const noBtn      = overlay.querySelector("#psyqNo");
    const closeBtn = overlay.querySelector("#psyqClose");

    const introLine = isCompactCard
      ? compactCopy.headline
      : `${reflection} ${subjectLine} killing focus — prove it or tap through.`;

    if (isCompactCard) {
      if (mode === "q1") {
        const existing = document.querySelector(".psyq-overlay[data-warning-only='1']");
        if (existing) existing.remove();
        overlay.setAttribute("data-warning-only", "1");
      }
      reflEl.textContent = introLine;
      questionEl.style.opacity = "1";
      questionEl.textContent = compactCopy.sub;
      if (mode === "q1") {
        void fetchQ1WarningCopy().then((aiCopy) => {
          if (!document.body.contains(overlay) || !aiCopy) return;
          reflEl.textContent = aiCopy.headline || compactCopy.headline;
          questionEl.textContent = aiCopy.sub || compactCopy.sub;
        });
      }
      closeBtn?.addEventListener("click", () => dismissPsyqOverlay(overlay, onComplete));
      return;
    }

    function showResponse(isYes) {
      const yes = overlay.querySelector("#psyqYes");
      const no = overlay.querySelector("#psyqNo");
      if (yes) yes.disabled = true;
      if (no) no.disabled = true;

      const icon  = isYes ? "😒" : "🙄";
      const title = isYes ? "Sure you are." : "Denial won't save your rank.";
      const body  = isYes
        ? "Talk is cheap. The torch test starts next — let's see if you mean it."
        : "No doesn't pause this. The beam still hits — enjoy half-blind reading.";
      const cta   = isYes ? "Whatever — continue" : "Fine — continue";

      card.innerHTML = `
        <div class="psyq-response">
          <div class="psyq-response-icon">${icon}</div>
          <p class="psyq-response-title">${title}</p>
          <p class="psyq-response-body">${body}</p>
          <button class="psyq-btn psyq-btn-cta" id="psyqCta" type="button">${cta}</button>
        </div>
      `;
      card.classList.add("psyq-card--response");

      overlay.querySelector("#psyqCta").addEventListener("click", () => dismissPsyqOverlay(overlay, onComplete));
    }

    // Q2: roast in card → then highlighted question + Yes/No (same card, no Continue)
    if (q2Copy) {
      const divider = overlay.querySelector(".psyq-divider");
      reflEl.textContent = q2Copy.headline;
      reflEl.style.minHeight = "0";

      const subEl = document.createElement("p");
      subEl.className = "psyq-subline";
      subEl.textContent = q2Copy.sub;
      if (divider) divider.insertAdjacentElement("afterend", subEl);

      questionEl.style.display = "none";
      questionEl.style.opacity = "0";
      if (actionsEl) {
        actionsEl.style.opacity = "0";
        actionsEl.style.pointerEvents = "none";
      }

      const revealFocusId = setTimeout(() => {
        if (!document.body.contains(overlay)) return;
        questionEl.style.display = "";
        questionEl.style.opacity = "1";
        questionEl.className = "psyq-question psyq-question--highlight";
        questionEl.textContent = q2Copy.focusQuestion;
        if (actionsEl) {
          actionsEl.style.opacity = "1";
          actionsEl.style.pointerEvents = "auto";
        }
        overlay.querySelector("#psyqYes")?.addEventListener("click", () => showResponse(true));
        overlay.querySelector("#psyqNo")?.addEventListener("click", () => showResponse(false));
      }, 2600);
      pendingTriggerTimeouts.push(revealFocusId);
      return;
    }

    // Typewriter for interactive mode (fallback)
    let charIdx = 0;
    const typeInterval = setInterval(() => {
      reflEl.textContent = introLine.slice(0, ++charIdx);
      if (charIdx >= introLine.length) {
        clearInterval(typeInterval);
        setTimeout(() => {
          questionEl.style.opacity = "1";
          questionEl.textContent   = question;
          setTimeout(() => {
            if (actionsEl) {
              actionsEl.style.opacity = "1";
              actionsEl.style.pointerEvents = "auto";
            }
          }, 280);
        }, 500);
      }
    }, 26);

    yesBtn?.addEventListener("click", () => showResponse(true));
    noBtn?.addEventListener("click",  () => showResponse(false));
  }

  /** Q2: short irritating popup, then hard-fog (difficulty check → hard question). */
  function runQ2HardFogSequence(questionNumber) {
    if (questionStem) questionStem.style.visibility = "hidden";
    if (questionOptions) questionOptions.style.visibility = "hidden";
    if (state.feedbackPromptOpen) {
      state.feedbackPromptOpen = false;
      releaseInterruptionLock("feedback");
    }
    const difficultyCheckResult = activateTrigger("difficultyCheckPrompt", {
      userState: currentUserState(),
      force: true,
      reason: `question_trigger:Q${questionNumber}:pre_sequence`,
      questionNumber,
    });
    if (!difficultyCheckResult) {
      const fallbackId = setTimeout(() => {
        const q = testQuestions[testQuestionIndex];
        if (!q || testQuestionIndex + 1 !== questionNumber) return;
        activateHardQuestionChallenge({ ...q, difficulty: "hard" });
      }, 2500);
      pendingTriggerTimeouts.push(fallbackId);
      return;
    }
    const waitForDifficultyCheck = setInterval(() => {
      if (!isTriggerActive("difficultyCheckPrompt")) {
        clearInterval(waitForDifficultyCheck);
        const afterId = setTimeout(() => {
          const q = testQuestions[testQuestionIndex];
          if (!q || testQuestionIndex + 1 !== questionNumber) return;
          activateHardQuestionChallenge({ ...q, difficulty: "hard" });
        }, 2500);
        pendingTriggerTimeouts.push(afterId);
      }
    }, 100);
  }

  function runQ2PopupFlow(questionNumber) {
    let flowStarted = false;
    const startFlow = () => {
      if (flowStarted) return;
      if (testQuestionIndex + 1 !== questionNumber) return;
      flowStarted = true;
      window.removeEventListener("scroll", onScroll);
      showPersonalizedQuiz(() => {
        if (testQuestionIndex + 1 !== questionNumber) return;
        const q2 = buildQ2PopupCopy();
        const subj = q2.subjectLine || "distractions";
        activateTrigger("torchlightSpotlight", {
          userState: currentUserState(),
          force: true,
          reason: `question_trigger:Q${questionNumber}:torchlight_after_popup`,
          intensity: "medium",
          questionNumber,
          caption: `Can't see the full question? Good. Chase the beam.`,
          spotlightTitle: "Narrow beam",
          spotlightLead: `${subj} won't solve itself in the dark.`,
          spotlightChallenge: "Track the light. Pick an answer anyway.",
          spotlightTaunt: "One patch lit. Rest hidden. Stop sulking.",
          taunts: [
            "Light moves. Your focus should too.",
            "Half-blind read — that's the point.",
            "Still scrolling in your head? Pathetic.",
            "Beam's on the stem. Eyes up.",
          ],
        });
      }, { mode: "q2" });
    };
    const onScroll = () => startFlow();
    window.addEventListener("scroll", onScroll, { passive: true });
    const timeoutId = setTimeout(startFlow, 8000);
    const cleanupId = setTimeout(() => window.removeEventListener("scroll", onScroll), 12000);
    pendingTriggerTimeouts.push(timeoutId);
    pendingTriggerTimeouts.push(cleanupId);
  }

  // ── End Personalized Quiz ─────────────────────────────────────────────────

  function triggerScreenFlip(ctx) {
    const shell = getAppShell();
    if (!shell) return null;
    
    // Get parameters from context
    const flipCycles = ctx?.flipCycles || 5; // Default 5 cycles
    const flipDuration = ctx?.flipDuration || 5000; // Default 5s flipped
    const waitDuration = ctx?.waitDuration || 5000; // Default 5s wait
    const permanentFinalState = ctx?.permanentFinalState !== false; // Default true
    
    console.log(`[triggerScreenFlip] Starting ${flipCycles} flip cycles`);
    console.log(`[triggerScreenFlip] Flip duration: ${flipDuration}ms, Wait duration: ${waitDuration}ms`);
    console.log(`[triggerScreenFlip] Permanent final state: ${permanentFinalState}`);
    
    const taunts = [
      "Orientation is comfort. I just took it.",
      "When the world turns, only discipline stays upright.",
      "Panic flips first. Mind flips next.",
      "Your focus should not depend on direction.",
    ];
    const taunt = taunts[stableRange("screenFlip_taunt", 0, taunts.length - 1)];
    const banner = mountDevilTopBanner({
      title: "Devil Flip",
      lead: "I turned your screen against you.",
      challenge: `Answer now. ${flipCycles} flips incoming.`,
      taunt,
    });

    let currentCycle = 0;
    let isFlipped = false;
    let cycleTimeoutId = null;
    let isCancelled = false;
    
    const performFlipCycle = () => {
      if (isCancelled) return;
      
      currentCycle++;
      console.log(`[triggerScreenFlip] Cycle ${currentCycle}/${flipCycles} - Flipping screen`);
      
      // Flip the screen
      shell.classList.add("stress-screen-flip");
      isFlipped = true;
      
      // Stay flipped for flipDuration
      cycleTimeoutId = setTimeout(() => {
        if (isCancelled) return;
        
        // Check if this is the last cycle
        if (currentCycle >= flipCycles) {
          // Last cycle - keep flipped permanently if permanentFinalState is true
          if (permanentFinalState) {
            console.log(`[triggerScreenFlip] Final cycle ${currentCycle}/${flipCycles} - Staying flipped permanently`);
            // Don't flip back, leave it flipped
          } else {
            console.log(`[triggerScreenFlip] Final cycle ${currentCycle}/${flipCycles} - Flipping back`);
            shell.classList.remove("stress-screen-flip");
            isFlipped = false;
          }
        } else {
          // Not the last cycle - flip back
          console.log(`[triggerScreenFlip] Cycle ${currentCycle}/${flipCycles} - Flipping back`);
          shell.classList.remove("stress-screen-flip");
          isFlipped = false;
          
          // Wait for waitDuration before next flip
          cycleTimeoutId = setTimeout(() => {
            if (isCancelled) return;
            performFlipCycle(); // Start next cycle
          }, waitDuration);
        }
      }, flipDuration);
    };
    
    // Start the first flip cycle
    performFlipCycle();
    
    // Calculate total duration: (flipDuration + waitDuration) * (cycles - 1) + flipDuration
    // Last cycle doesn't have a wait period
    const totalDuration = (flipDuration + waitDuration) * (flipCycles - 1) + flipDuration;
    
    return {
      durationMs: totalDuration,
      cleanup: () => {
        console.log(`[triggerScreenFlip] Cleanup called`);
        isCancelled = true;
        if (cycleTimeoutId) {
          clearTimeout(cycleTimeoutId);
        }
        // Only remove flip if not permanent or if we're cleaning up mid-cycle
        if (!permanentFinalState || currentCycle < flipCycles) {
          shell.classList.remove("stress-screen-flip");
        }
        banner.remove();
      },
    };
  }

  function triggerColorInversion() {
    const taunts = [
      "Light, dark, it does not matter when your mind is steady.",
      "Colors changed. Logic did not.",
      "Visual shock is easy. Stable focus is rare.",
      "Let your eyes panic. Keep your reasoning cold.",
    ];
    const taunt = taunts[stableRange("colorInversion_taunt", 0, taunts.length - 1)];
    const banner = mountDevilTopBanner({
      title: "Devil Inversion",
      lead: "I inverted your world in one blink.",
      challenge: "Now answer. Can you think clearly in this chaos?",
      taunt,
    });

    document.body.classList.add("stress-color-inversion");
    return {
      durationMs: stableRange("colorInversion_duration", 2600, 4200),
      cleanup: () => {
        document.body.classList.remove("stress-color-inversion");
        banner.remove();
      },
    };
  }

  function triggerWaveDistortion() {
    const shell = getAppShell();
    if (!shell) return null;
    const quotes = [
      "Read through the sway, not through panic.",
      "If lines move, your logic should not.",
      "Steady eyes beat unstable motion.",
      "Waves are visual. Mistakes are permanent.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Wave",
      lead: "I bent your screen into a moving tide.",
      challenge: "Can you read with discipline while the page drifts?",
      taunt: quotes[stableRange("waveDistortion_quote", 0, quotes.length - 1)],
    });

    const waveLayer = document.createElement("div");
    waveLayer.className = "stress-wave-sheet";
    const rowCount = 6;
    for (let i = 0; i < rowCount; i += 1) {
      const row = document.createElement("span");
      row.className = "wave-row";
      const top = (i * 100) / rowCount;
      const amp = stableRange(`waveDistortion_rowAmp_${i}`, 14, 30);
      const dir = i % 2 === 0 ? 1 : -1;
      row.style.setProperty("--top", `${top.toFixed(2)}%`);
      row.style.setProperty("--h", `${(100 / rowCount + 1.2).toFixed(2)}%`);
      row.style.setProperty("--dur", `${stableRange(`waveDistortion_rowDur_${i}`, 2200, 3600)}ms`);
      row.style.setProperty("--delay", `${stableRange(`waveDistortion_rowDelay_${i}`, 0, 600)}ms`);
      row.style.setProperty("--from-x", `${-amp * dir}px`);
      row.style.setProperty("--mid-x", `${amp * dir}px`);
      row.style.setProperty("--near-x", `${Math.round(amp * 0.35 * dir)}px`);
      row.style.setProperty("--tilt", `${(dir * 0.8).toFixed(2)}deg`);
      row.style.setProperty("--texture-dur", `${stableRange(`waveDistortion_textureDur_${i}`, 1200, 2300)}ms`);
      row.style.setProperty("--heave", `${stableRange(`waveDistortion_heave_${i}`, 2, 5)}px`);
      row.style.setProperty("--heave-dur", `${stableRange(`waveDistortion_heaveDur_${i}`, 2200, 4200)}ms`);
      waveLayer.appendChild(row);
    }

    const fishCount = 10;
    for (let i = 0; i < fishCount; i += 1) {
      const fish = document.createElement("span");
      const leftToRight = i % 2 === 0;
      fish.className = `wave-fish ${leftToRight ? "dir-ltr" : "dir-rtl"}`;
      fish.style.setProperty("--y", `${stableRange(`waveDistortion_fishY_${i}`, 18, 78)}%`);
      fish.style.setProperty("--size", `${stableRange(`waveDistortion_fishSize_${i}`, 16, 30)}px`);
      fish.style.setProperty("--dur", `${stableRange(`waveDistortion_fishDur_${i}`, 4200, 9200)}ms`);
      fish.style.setProperty("--delay", `${stableRange(`waveDistortion_fishDelay_${i}`, 0, 1400)}ms`);
      fish.style.setProperty("--bob", `${stableRange(`waveDistortion_fishBob_${i}`, 6, 16)}px`);
      fish.style.setProperty("--start-x", leftToRight ? "-12%" : "108%");
      fish.style.setProperty("--mid-x", leftToRight ? "52%" : "48%");
      fish.style.setProperty("--end-x", leftToRight ? "108%" : "-12%");
      fish.style.setProperty("--flip", leftToRight ? "1" : "-1");
      waveLayer.appendChild(fish);
    }

    const grassCount = 18;
    for (let i = 0; i < grassCount; i += 1) {
      const grass = document.createElement("span");
      grass.className = "wave-grass";
      grass.style.setProperty("--x", `${stableRange(`waveDistortion_grassX_${i}`, 2, 98)}%`);
      grass.style.setProperty("--h", `${stableRange(`waveDistortion_grassH_${i}`, 24, 72)}px`);
      grass.style.setProperty("--w", `${stableRange(`waveDistortion_grassW_${i}`, 3, 8)}px`);
      grass.style.setProperty("--dur", `${stableRange(`waveDistortion_grassDur_${i}`, 1800, 3600)}ms`);
      grass.style.setProperty("--delay", `${stableRange(`waveDistortion_grassDelay_${i}`, 0, 1600)}ms`);
      grass.style.setProperty("--bend", `${stableRange(`waveDistortion_grassBend_${i}`, 6, 18)}deg`);
      waveLayer.appendChild(grass);
    }

    const crabCount = 5;
    for (let i = 0; i < crabCount; i += 1) {
      const crab = document.createElement("span");
      crab.className = "wave-crab";
      crab.textContent = "🦀";
      const leftToRight = i % 2 === 0;
      crab.style.setProperty("--x", `${stableRange(`waveDistortion_crabX_${i}`, 10, 90)}%`);
      crab.style.setProperty("--y", `${stableRange(`waveDistortion_crabY_${i}`, 84, 96)}%`);
      crab.style.setProperty("--dur", `${stableRange(`waveDistortion_crabDur_${i}`, 2600, 6200)}ms`);
      crab.style.setProperty("--delay", `${stableRange(`waveDistortion_crabDelay_${i}`, 0, 1800)}ms`);
      crab.style.setProperty("--travel", `${stableRange(`waveDistortion_crabTravel_${i}`, 8, 24)}px`);
      crab.style.setProperty("--flip", leftToRight ? "1" : "-1");
      waveLayer.appendChild(crab);
    }

    const bubbleCount = 22;
    for (let i = 0; i < bubbleCount; i += 1) {
      const bubble = document.createElement("span");
      bubble.className = "wave-bubble";
      bubble.style.setProperty("--x", `${stableRange(`waveDistortion_bubbleX_${i}`, 4, 96)}%`);
      bubble.style.setProperty("--size", `${stableRange(`waveDistortion_bubbleSize_${i}`, 4, 14)}px`);
      bubble.style.setProperty("--dur", `${stableRange(`waveDistortion_bubbleDur_${i}`, 1800, 4600)}ms`);
      bubble.style.setProperty("--delay", `${stableRange(`waveDistortion_bubbleDelay_${i}`, 0, 2600)}ms`);
      bubble.style.setProperty("--rise", `${stableRange(`waveDistortion_bubbleRise_${i}`, 26, 72)}px`);
      bubble.style.setProperty("--sway", `${stableRange(`waveDistortion_bubbleSway_${i}`, 3, 16)}px`);
      waveLayer.appendChild(bubble);
    }

    document.body.appendChild(waveLayer);
    shell.classList.add("stress-wave-distortion");
    return {
      durationMs: stableRange("waveDistortion_duration", 4200, 6800),
      cleanup: () => {
        waveLayer.remove();
        shell.classList.remove("stress-wave-distortion");
        topBanner.remove();
      },
    };
  }

  function triggerFakeMentorCount() {
    const quotes = [
      "Eyes are on you. Noise is optional.",
      "Mentors watching. You still owe clean thinking.",
      "Audience pressure is my favorite distraction.",
      "Being watched changes nothing. Your method matters.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Audience",
      lead: "Mentors are watching this attempt in real time.",
      challenge: "Can you ignore the crowd and stay exact?",
      taunt: quotes[stableRange("fakeMentorCount_quote", 0, quotes.length - 1)],
    });

    const card = document.createElement("div");
    card.className = "stress-mentor-watch";
    let count = stableRange("fakeMentorCount_seed", 18, 43);
    card.innerHTML = `
      <div class="label">Mentors Watching</div>
      <div class="count">${count}</div>
      <div class="sub">Live observer panel connected</div>
    `;
    document.body.appendChild(card);

    const tick = setInterval(() => {
      const delta = stableRange("fakeMentorCount_delta", -1, 3);
      count = Math.max(7, count + delta);
      const countEl = card.querySelector(".count");
      if (countEl) countEl.textContent = String(count);
    }, 900);

    return {
      durationMs: stableRange("fakeMentorCount_duration", 6200, 9800),
      cleanup: () => {
        clearInterval(tick);
        card.remove();
        topBanner.remove();
      },
    };
  }

  function triggerChaosBackground() {
    const quotes = [
      "Background noise is the oldest trap in focus work.",
      "Ignore the art. Read the stem.",
      "If visuals lead you, reason will lag.",
      "The scene moves. The answer does not.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Fractals",
      lead: "I turned your background into elegant chaos.",
      challenge: "Can your attention stay locked on the question?",
      taunt: quotes[stableRange("chaosBackground_quote", 0, quotes.length - 1)],
    });

    const layer = document.createElement("div");
    layer.className = "stress-chaos-bg-layer";

    const glyphs = ["?", "!", "#", "∿", "≈", "⊗", "◇", "△", "⊕", "☍", "⚠", "✶"];
    const rand = (min, max) => min + Math.random() * (max - min);

    for (let i = 0; i < 22; i += 1) {
      const shard = document.createElement("span");
      shard.className = "chaos-shard";
      shard.textContent = glyphs[Math.floor(rand(0, glyphs.length))];
      shard.style.setProperty("--x", `${rand(4, 96).toFixed(2)}%`);
      shard.style.setProperty("--y", `${rand(6, 94).toFixed(2)}%`);
      shard.style.setProperty("--dur", `${rand(1800, 4600).toFixed(0)}ms`);
      shard.style.setProperty("--delay", `${rand(0, 1200).toFixed(0)}ms`);
      shard.style.setProperty("--drift-x", `${rand(-26, 26).toFixed(1)}px`);
      shard.style.setProperty("--drift-y", `${rand(-30, 30).toFixed(1)}px`);
      shard.style.setProperty("--rot", `${rand(-34, 34).toFixed(1)}deg`);
      shard.style.setProperty("--size", `${rand(12, 28).toFixed(0)}px`);
      layer.appendChild(shard);
    }

    for (let i = 0; i < 8; i += 1) {
      const orb = document.createElement("span");
      orb.className = "chaos-orb";
      orb.style.setProperty("--x", `${rand(6, 94).toFixed(2)}%`);
      orb.style.setProperty("--y", `${rand(8, 92).toFixed(2)}%`);
      orb.style.setProperty("--dur", `${rand(2600, 5200).toFixed(0)}ms`);
      orb.style.setProperty("--delay", `${rand(0, 1300).toFixed(0)}ms`);
      orb.style.setProperty("--drift-x", `${rand(-44, 44).toFixed(1)}px`);
      orb.style.setProperty("--drift-y", `${rand(-28, 28).toFixed(1)}px`);
      orb.style.setProperty("--size", `${rand(54, 140).toFixed(0)}px`);
      layer.appendChild(orb);
    }

    document.body.appendChild(layer);
    document.body.classList.add("stress-chaos-bg");

    const burstTimer = setInterval(() => {
      const shard = document.createElement("span");
      shard.className = "chaos-shard burst";
      shard.textContent = glyphs[Math.floor(rand(0, glyphs.length))];
      shard.style.setProperty("--x", `${rand(8, 92).toFixed(2)}%`);
      shard.style.setProperty("--y", `${rand(8, 92).toFixed(2)}%`);
      shard.style.setProperty("--dur", `${rand(1200, 2200).toFixed(0)}ms`);
      shard.style.setProperty("--delay", "0ms");
      shard.style.setProperty("--drift-x", `${rand(-34, 34).toFixed(1)}px`);
      shard.style.setProperty("--drift-y", `${rand(-34, 34).toFixed(1)}px`);
      shard.style.setProperty("--rot", `${rand(-70, 70).toFixed(1)}deg`);
      shard.style.setProperty("--size", `${rand(16, 30).toFixed(0)}px`);
      layer.appendChild(shard);
      setTimeout(() => shard.remove(), 2500);
    }, 520);

    return {
      durationMs: stableRange("chaosBackground_duration", 7000, 12000),
      cleanup: () => {
        clearInterval(burstTimer);
        document.body.classList.remove("stress-chaos-bg");
        layer.remove();
        topBanner.remove();
      },
    };
  }

  function triggerShepardTone() {
    const quotes = [
      "Listen closely: tension rises without release.",
      "The tone climbs. Keep your reasoning grounded.",
      "Endless rise, no landing. Classic focus break.",
      "Your ears panic first. Your mind follows.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Tone",
      lead: "I started a rising tension tone in your ears.",
      challenge: "Can you solve while pressure keeps climbing?",
      taunt: quotes[stableRange("shepardTone_quote", 0, quotes.length - 1)],
    });

    let shepardAudio = null;
    let stopped = false;

    const shepardFile = "freesound_community-mixed-rising-and-falling-shepard-tone-83747.mp3";
    const shepardSources = [
      new URL(`/static/${shepardFile}`, window.location.href).toString(),
      new URL(`static/${shepardFile}`, window.location.href).toString(),
      new URL(shepardFile, window.location.href).toString(),
    ];

    (async () => {
      for (const src of shepardSources) {
        if (stopped) return;
        try {
          const candidate = new Audio(src);
          candidate.loop = true;
          candidate.preload = "auto";
          candidate.volume = 1;
          const playPromise = candidate.play();
          if (playPromise && typeof playPromise.then === "function") {
            await playPromise;
          }
          if (stopped) {
            candidate.pause();
            candidate.currentTime = 0;
            return;
          }
          shepardAudio = candidate;
          return;
        } catch (err) {
          debugLog("audio_unavailable", `shepardTone:mp3_source_failed:${src}:${String(err)}`);
        }
      }
      debugLog("audio_unavailable", "shepardTone:mp3_all_sources_failed");
    })();

    return {
      durationMs: stableRange("shepardTone_duration", 8000, 13000),
      cleanup: () => {
        stopped = true;
        try {
          if (shepardAudio) {
            shepardAudio.pause();
            shepardAudio.currentTime = 0;
            shepardAudio.src = "";
            shepardAudio.load();
          }
        } catch (e) {
          // no-op
        }
        topBanner.remove();
      },
    };
  }

  function triggerSpatialTicking() {
    const quotes = [
      "Tick left. Tick right. Where is your focus now?",
      "The clock circles you. Keep the answer centered.",
      "Directional time noise breaks reading rhythm.",
      "Follow the question, not the sound path.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Clock",
      lead: "I moved ticking sound around your head.",
      challenge: "Can you hold focus while time hunts from both sides?",
      taunt: quotes[stableRange("spatialTicking_quote", 0, quotes.length - 1)],
    });

    topBanner.classList.add("is-clock-ticking");
    const bubble = topBanner.querySelector(".bubble");
    if (bubble) {
      const clock = document.createElement("span");
      clock.className = "devil-ticking-clock";
      clock.innerHTML = `<span class="face"></span><span class="hand"></span><span class="dot"></span>`;
      bubble.appendChild(clock);
    }

    let tickTimer = null;
    let stopped = false;

    resumeAudioContextIfNeeded().then((ctx) => {
      if (!ctx || stopped) return;
      let step = 0;
      tickTimer = setInterval(() => {
        if (stopped) return;
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const pan = typeof ctx.createStereoPanner === "function" ? ctx.createStereoPanner() : null;
        osc.type = "square";
        osc.frequency.value = 950;
        gain.gain.value = 0.0001;
        const p = Math.sin(step * 0.72);
        step += 1;
        if (pan) {
          pan.pan.value = p;
          osc.connect(gain);
          gain.connect(pan);
          pan.connect(ctx.destination);
        } else {
          osc.connect(gain);
          gain.connect(ctx.destination);
        }
        gain.gain.exponentialRampToValueAtTime(0.03, now + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
        osc.start(now);
        osc.stop(now + 0.1);
      }, 320);
    });

    return {
      durationMs: stableRange("spatialTicking_duration", 7000, 12000),
      cleanup: () => {
        stopped = true;
        if (tickTimer) clearInterval(tickTimer);
        topBanner.remove();
      },
    };
  }

  function triggerFakeLowBattery() {
    const quotes = [
      "Power fear is fake. Mistakes are real.",
      "The battery warning is bait. Ignore and solve.",
      "Low power message. High pressure judgment.",
      "Urgency popups are my easiest traps.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Battery",
      lead: "I injected a system battery warning into your exam.",
      challenge: "Can you ignore fake urgency and stay accurate?",
      taunt: quotes[stableRange("fakeLowBattery_quote", 0, quotes.length - 1)],
    });

    const card = document.createElement("div");
    card.className = "stress-center-alert win11 low-battery";
    card.innerHTML = `
      <div class="win11-titlebar">
        <span class="app-dot" aria-hidden="true"></span>
        <span class="title">System Notification</span>
        <span class="window-actions" aria-hidden="true">— □ ×</span>
      </div>
      <div class="win11-body">
        <div class="alert-icon">🔋</div>
        <div class="content">
          <div class="alert-title">Battery Critically Low</div>
          <div class="alert-sub">3% remaining. Connect charger to prevent unexpected shutdown.</div>
          <div class="diag-line">Power service: <strong>ACPI_BAT_MONITOR</strong></div>
          <div class="diag-line">Diagnostic code: <strong>PWR-0x8A21</strong></div>
        </div>
      </div>
      <div class="win11-footer">
        <button type="button">Open Power Settings</button>
        <button type="button">Remind me later</button>
      </div>
    `;
    document.body.appendChild(card);
    return {
      durationMs: stableRange("fakeLowBattery_duration", 4200, 7200),
      cleanup: () => {
        card.remove();
        topBanner.remove();
      },
    };
  }

  function triggerFakeCrashScreen() {
    const quotes = [
      "A fake crash should not crash your focus.",
      "System panic is theater. Solve anyway.",
      "Error screens are noise until proven real.",
      "Can your composure outlive this fake failure?",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Crash",
      lead: "I staged a fake Windows diagnostic crash panel.",
      challenge: "Can you recover composure faster than the shock?",
      taunt: quotes[stableRange("fakeCrashScreen_quote", 0, quotes.length - 1)],
    });

    const card = document.createElement("div");
    card.className = "stress-center-alert win11 fake-crash";
    card.innerHTML = `
      <div class="win11-titlebar">
        <span class="app-dot" aria-hidden="true"></span>
        <span class="title">Windows Diagnostic Host</span>
        <span class="window-actions" aria-hidden="true">— □ ×</span>
      </div>
      <div class="win11-body">
        <div class="alert-icon">⚠️</div>
        <div class="content">
          <div class="alert-title">System UI Unresponsive</div>
          <div class="alert-sub">Collecting diagnostics and attempting recovery.</div>
          <div class="diag-line">Fault module: <strong>UIRenderer.dll</strong></div>
          <div class="diag-line">Exception code: <strong>0xC0000409</strong></div>
          <div class="diag-line">Session trace: <strong>WDH-${stableRange("fakeCrashScreen_trace", 1200, 9999)}</strong></div>
        </div>
      </div>
      <div class="win11-footer">
        <button type="button">Run Diagnostics</button>
        <button type="button">Close Program</button>
      </div>
    `;
    document.body.appendChild(card);
    return {
      durationMs: stableRange("fakeCrashScreen_duration", 3200, 5600),
      cleanup: () => {
        card.remove();
        topBanner.remove();
      },
    };
  }

  function triggerBlackout() {
    const quotes = [
      "Darkness tests memory and composure.",
      "When vision disappears, panic appears.",
      "Temporary blackout. Permanent consequences.",
      "Can your focus survive zero visibility?",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Blackout",
      lead: "Devil hacked your system and cut your display feed.",
      challenge: "Can you recover instantly when the screen returns?",
      taunt: quotes[stableRange("blackout_quote", 0, quotes.length - 1)],
    });

    const layer = document.createElement("div");
    layer.className = "stress-blackout";
    document.body.appendChild(layer);
    return {
      durationMs: stableRange("blackout_duration", 1200, 2400),
      cleanup: () => {
        layer.remove();
        topBanner.remove();
      },
    };
  }

  function triggerHesitationHeatmap() {
    const quotes = [
      "Your cursor betrays every hesitation.",
      "Indecision leaves a visible trail.",
      "I mapped your doubt in real time.",
      "Trails of hesitation, footprints of panic.",
    ];
    const topBanner = mountDevilTopBanner({
      title: "Devil Heatmap",
      lead: "I am visualizing every hesitation you make.",
      challenge: "Can you choose decisively while doubt is exposed?",
      taunt: quotes[stableRange("hesitationHeatmap_quote", 0, quotes.length - 1)],
    });

    const layer = document.createElement("div");
    layer.className = "stress-hesitation-layer";
    document.body.appendChild(layer);

    let lastMoveAt = 0;
    const spawnDot = (x, y, hot) => {
      const dot = document.createElement("span");
      dot.className = `trace ${hot ? "hot" : ""}`;
      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;
      layer.appendChild(dot);
      setTimeout(() => dot.remove(), hot ? 1400 : 900);
    };

    const onMove = (evt) => {
      const now = Date.now();
      if (now - lastMoveAt < 55) return;
      lastMoveAt = now;
      spawnDot(evt.clientX, evt.clientY, false);
    };

    const onClick = (evt) => {
      spawnDot(evt.clientX, evt.clientY, true);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("click", onClick, { passive: true });

    return {
      durationMs: stableRange("hesitationHeatmap_duration", 7000, 12000),
      cleanup: () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("click", onClick);
        layer.remove();
        topBanner.remove();
      },
    };
  }

  function triggerBollywoodReelTrap() {
    return null;
  }

  function triggerBouncingQuestion() {
    if (!state.currentQuestionId) return null;
    const movingEl = getTestCard() || questionBody;
    if (!movingEl) return null;

    const targetQuestionId = String(state.currentQuestionId || "");
    const startRect = movingEl.getBoundingClientRect();
    if (!startRect.width || !startRect.height) return null;

    const intro = document.createElement("div");
    intro.className = "stress-bounce-intro";
    intro.setAttribute("role", "dialog");
    intro.setAttribute("aria-live", "polite");
    intro.innerHTML = `
      <div class="stress-bounce-intro-card">
        <div class="stress-bounce-ball-wrap" aria-hidden="true">
          <div class="stress-bounce-ball">8</div>
        </div>
        <div class="stress-bounce-eyebrow">CHALLENGE FOR U</div>
        <h3>Topper-level trap. Can you track and solve?</h3>
        <div class="stress-bounce-focus-text">Watch the ball. Read the question. Both. At once.</div>
        <p>Starting in a moment...</p>
      </div>
    `;
    document.body.appendChild(intro);

    const focusTrail = document.createElement("div");
    focusTrail.className = "stress-bounce-focus-trail";
    document.body.appendChild(focusTrail);

    const savedStyle = {
      position: movingEl.style.position || "",
      left: movingEl.style.left || "",
      top: movingEl.style.top || "",
      width: movingEl.style.width || "",
      zIndex: movingEl.style.zIndex || "",
      margin: movingEl.style.margin || "",
      transform: movingEl.style.transform || "",
      pointerEvents: movingEl.style.pointerEvents || "",
      maxWidth: movingEl.style.maxWidth || "",
      boxSizing: movingEl.style.boxSizing || "",
      willChange: movingEl.style.willChange || "",
    };

    const placeholder = document.createElement("div");
    placeholder.className = "stress-bounce-placeholder";
    placeholder.style.height = `${Math.ceil(startRect.height)}px`;
    movingEl.parentNode?.insertBefore(placeholder, movingEl);

    let posX = startRect.left;
    let posY = startRect.top;
    let velX = 4.5;
    let velY = 4.2;
    const bounceRetention = 0.96;
    const minSpeed = 4.2;
    const maxSpeed = 7.5;
    const steerStrength = 0.18;
    const arriveDistance = 10;
    const motionScale = 0.9;
    const motionWidth = Math.round(startRect.width * motionScale);
    const motionHeight = Math.round(startRect.height * motionScale);
    let rafId = null;
    let monitorTimer = null;
    let introTimer = null;
    let focusCooldownUntil = 0;
    let lastTs = 0;
    let activeMotion = false;
    let tiltDeg = 0;
    let targetPoint = null;

    function getBounds() {
      const margin = 12;
      const maxX = Math.max(margin, window.innerWidth - motionWidth - margin);
      const maxY = Math.max(margin, window.innerHeight - motionHeight - margin);
      return { margin, maxX, maxY };
    }

    function buildTargets() {
      const { margin, maxX, maxY } = getBounds();
      return [
        { x: margin, y: margin, kind: "corner" },
        { x: maxX, y: margin, kind: "corner" },
        { x: margin, y: maxY, kind: "corner" },
        { x: maxX, y: maxY, kind: "corner" },
      ];
    }

    function pickTarget(force = false) {
      if (!force && targetPoint) return;
      const candidates = buildTargets();
      let filtered = candidates;
      if (targetPoint) {
        filtered = candidates.filter((p) => Math.hypot(p.x - targetPoint.x, p.y - targetPoint.y) > 34);
      }
      if (!filtered.length) filtered = candidates;
      filtered = filtered.sort((a, b) => {
        const da = Math.hypot(a.x - posX, a.y - posY);
        const db = Math.hypot(b.x - posX, b.y - posY);
        return db - da;
      });

      const topPool = filtered.slice(0, Math.max(3, Math.min(5, filtered.length)));
      let chosen = topPool[Math.floor(Math.random() * topPool.length)];
      targetPoint = chosen || filtered[0] || candidates[0];
    }

    function spawnFocusTag(x, y) {
      const now = Date.now();
      if (now < focusCooldownUntil) return;
      focusCooldownUntil = now + 120;
      const tag = document.createElement("div");
      tag.className = "stress-bounce-focus-tag";
      tag.textContent = "FOCUS";
      tag.style.left = `${Math.round(x)}px`;
      tag.style.top = `${Math.round(y)}px`;
      focusTrail.appendChild(tag);
      setTimeout(() => tag.remove(), 200);
    }

    function applyMotionStyles() {
      movingEl.classList.add("stress-bouncing-question-body");
      movingEl.style.position = "fixed";
      movingEl.style.left = `${Math.round(posX)}px`;
      movingEl.style.top = `${Math.round(posY)}px`;
      movingEl.style.width = `${motionWidth}px`;
      movingEl.style.maxWidth = `${motionWidth}px`;
      movingEl.style.zIndex = "70";
      movingEl.style.margin = "0";
      movingEl.style.transform = "translate3d(0, 0, 0) scale(1) rotate(0deg)";
      movingEl.style.pointerEvents = "auto";
      movingEl.style.boxSizing = "border-box";
      movingEl.style.willChange = "left, top, transform";
    }

    function frame(ts) {
      if (!activeMotion) return;
      if (!lastTs) lastTs = ts;
      const dt = Math.max(0.6, Math.min(2.2, (ts - lastTs) / 16.67));
      lastTs = ts;

      pickTarget();
      if (targetPoint) {
        const centerX = posX + (motionWidth / 2);
        const centerY = posY + (motionHeight / 2);
        const tx = targetPoint.x + (motionWidth / 2);
        const ty = targetPoint.y + (motionHeight / 2);
        const dx = tx - centerX;
        const dy = ty - centerY;
        const dist = Math.hypot(dx, dy) || 1;
        const desiredSpeed = dist < 180 ? minSpeed + ((maxSpeed - minSpeed) * 0.55) : maxSpeed;
        const desiredX = (dx / dist) * desiredSpeed;
        const desiredY = (dy / dist) * desiredSpeed;
        velX += (desiredX - velX) * steerStrength * dt;
        velY += (desiredY - velY) * steerStrength * dt;
        if (dist <= arriveDistance) {
          targetPoint = null;
          pickTarget(true);
        }
      }

      const speedNow = Math.hypot(velX, velY) || 1;
      const clampedSpeed = Math.max(minSpeed, Math.min(maxSpeed, speedNow));
      velX = (velX / speedNow) * clampedSpeed;
      velY = (velY / speedNow) * clampedSpeed;

      posX += velX * dt;
      posY += velY * dt;

      const w = motionWidth;
      const h = motionHeight;
      const { margin, maxX, maxY } = getBounds();
      const cx = posX + (w / 2);
      const cy = posY + (h / 2);
      let collided = false;

      if (posX <= margin) {
        posX = margin;
        velX = Math.abs(velX) * bounceRetention;
        spawnFocusTag(margin + 56, cy);
        targetPoint = null;
        pickTarget(true);
        collided = true;
      } else if (posX >= maxX) {
        posX = maxX;
        velX = -Math.abs(velX) * bounceRetention;
        spawnFocusTag(window.innerWidth - 78, cy);
        targetPoint = null;
        pickTarget(true);
        collided = true;
      }

      if (posY <= margin) {
        posY = margin;
        velY = Math.abs(velY) * bounceRetention;
        spawnFocusTag(cx, margin + 26);
        targetPoint = null;
        pickTarget(true);
        collided = true;
      } else if (posY >= maxY) {
        posY = maxY;
        velY = -Math.abs(velY) * bounceRetention;
        spawnFocusTag(cx, window.innerHeight - 34);
        targetPoint = null;
        pickTarget(true);
        collided = true;
      }

      if (collided) {
        const postSpeed = Math.hypot(velX, velY) || 1;
        const boosted = Math.max(minSpeed, Math.min(maxSpeed, postSpeed * 1.03));
        velX = (velX / postSpeed) * boosted;
        velY = (velY / postSpeed) * boosted;
      }

      const speed = Math.hypot(velX, velY);
      const targetTilt = Math.max(-10, Math.min(10, (velX * 4.1) + (velY * 1.1)));
      const damping = speed > 1 ? 0.22 : 0.15;
      tiltDeg += (targetTilt - tiltDeg) * damping;

      movingEl.style.left = `${Math.round(posX)}px`;
      movingEl.style.top = `${Math.round(posY)}px`;
      movingEl.style.transform = `translate3d(0, 0, 0) scale(${motionScale}) rotate(${tiltDeg.toFixed(2)}deg)`;
      rafId = requestAnimationFrame(frame);
    }

    function beginMotion() {
      if (activeMotion) return;
      activeMotion = true;
      intro.classList.add("closing");
      setTimeout(() => intro.remove(), 240);
      applyMotionStyles();
      rafId = requestAnimationFrame(frame);
    }

    monitorTimer = setInterval(() => {
      const movedToAnotherQuestion = String(state.currentQuestionId || "") !== targetQuestionId;
      const hasAnswer = Boolean(String(selectedOptions[targetQuestionId] || "").trim());
      if (movedToAnotherQuestion || hasAnswer) {
        deactivateTrigger("boucingQuestion");
      }
    }, 180);

    introTimer = setTimeout(beginMotion, 3200);

    return {
      durationMs: 0,
      cleanup: () => {
        activeMotion = false;
        if (rafId) cancelAnimationFrame(rafId);
        if (monitorTimer) clearInterval(monitorTimer);
        if (introTimer) clearTimeout(introTimer);
        intro.remove();
        focusTrail.remove();
        placeholder.remove();
        movingEl.classList.remove("stress-bouncing-question-body");
        movingEl.style.position = savedStyle.position;
        movingEl.style.left = savedStyle.left;
        movingEl.style.top = savedStyle.top;
        movingEl.style.width = savedStyle.width;
        movingEl.style.maxWidth = savedStyle.maxWidth;
        movingEl.style.zIndex = savedStyle.zIndex;
        movingEl.style.margin = savedStyle.margin;
        movingEl.style.transform = savedStyle.transform;
        movingEl.style.pointerEvents = savedStyle.pointerEvents;
        movingEl.style.boxSizing = savedStyle.boxSizing;
        movingEl.style.willChange = savedStyle.willChange;
      },
    };
  }

  function inferFeedbackMood(userState) {
    const accuracy = getRecentAccuracy();
    const idleMs = Number(userState?.idleMs || 0);
    const changes = Number(userState?.answerChangeCount || 0);
    const streak = Number(state.correctStreak || 0);
    const wrong = Number(state.wrongAnswersCount || 0);

    if (accuracy < 0.45 || wrong >= 3) return "stressed";
    if (idleMs > 9000 || changes >= 3) return "anxious";
    if (accuracy >= 0.75 && streak >= 2) return "confident";
    return "focused";
  }

  function selectFeedbackPrompt(mood) {
    const bucket = FEEDBACK_PROMPT_LIBRARY[mood] || FEEDBACK_PROMPT_LIBRARY.focused;
    const offset = state.feedbackResponseHistory.length % bucket.length;
    return bucket[offset];
  }

  function showFeedbackPulse(reason, promptOverride) {
    if (state.stage !== "popups") return;
    if (state.feedbackPromptOpen) return;
    if (isInterruptionActive()) return;

    const now = Date.now();
    if (now - Number(state.feedbackLastShownAt || 0) < FEEDBACK_MIN_INTERVAL_MS) return;

    const userState = currentUserState();
    const mood = inferFeedbackMood(userState);
    const survey = buildFeedbackSurvey(mood, reason, promptOverride);
    const prompt = survey.prompt;
    const options = survey.options;

    state.feedbackPromptOpen = true;
    state.feedbackLastShownAt = now;
    state.lastFeedbackQuestionType = survey.kind;
    acquireInterruptionLock("feedback");

    const card = document.createElement("div");
    card.className = "stress-feedback-pulse";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-live", "polite");
    card.innerHTML = `
      <div class="feedback-pulse-card">
        <div class="feedback-pulse-eyebrow">${escapeHTML(survey.eyebrow)}</div>
        <div class="feedback-pulse-question">${escapeHTML(prompt)}</div>
        <div class="feedback-chip-wrap"></div>
        <div class="feedback-pulse-actions">
          <button type="button" data-role="skip" class="feedback-pulse-skip">Not now</button>
        </div>
      </div>
    `;

    const chipWrap = card.querySelector(".feedback-chip-wrap");
    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "feedback-chip";
      btn.textContent = opt;
      btn.addEventListener("click", () => finalizeFeedback(opt));
      chipWrap?.appendChild(btn);
    });

    const skipBtn = card.querySelector('[data-role="skip"]');
    skipBtn?.addEventListener("click", () => finalizeFeedback("Skipped"));
    document.body.appendChild(card);

    const closeTimer = setTimeout(() => finalizeFeedback("No response"), FEEDBACK_PROMPT_MAX_OPEN_MS);

    function finalizeFeedback(choice) {
      clearTimeout(closeTimer);
      if (!card.isConnected) return;
      card.remove();

      const payload = {
        at: Date.now(),
        reason: String(reason || "pulse"),
        kind: survey.kind,
        mood,
        answer: String(choice || ""),
        question: prompt,
      };
      state.feedbackResponseHistory.push(payload);
      if (state.feedbackResponseHistory.length > 30) {
        state.feedbackResponseHistory = state.feedbackResponseHistory.slice(-30);
      }

      let intensity = mood === "stressed" || mood === "anxious" ? "medium" : "low";

      if (survey.kind === "difficulty") {
        const selected = String(choice || "").toLowerCase();
        if (selected.includes("hard")) state.feedbackDifficultyPreference = "hard";
        else if (selected.includes("easy")) state.feedbackDifficultyPreference = "easy";
        else state.feedbackDifficultyPreference = "medium";
      }

      if (survey.kind === "topic") {
        scheduleInterestReelTrigger(choice);
      }

      if (survey.kind === "mood") {
        const lower = String(choice || "").toLowerCase();
        if (/need challenge|confident|excited/.test(lower)) state.feedbackDifficultyPreference = "hard";
        if (/overwhelmed|stressed|need a short pause|anxious/.test(lower)) state.feedbackDifficultyPreference = "easy";
      }

      intensity = applyFeedbackIntensityBias(intensity);

      if (sessionId) {
        const snapshot = snapshotFeedbackMetrics(userState);
        postJSON(`/session/${sessionId}/trigger-feedback`, {
          trigger: `student_feedback_pulse:${mood}`,
          intensity,
          pre_metrics: snapshot,
          post_metrics: snapshot,
          recovery_metrics: snapshot,
          note: `[${survey.kind}] ${prompt} -> ${choice}`,
        }).catch((err) => debugLog("feedback_persist_error", err?.message || String(err)));
      }

      state.feedbackPromptOpen = false;
      releaseInterruptionLock("feedback");
    }
  }

  function applyInlineStyles(node, styles) {
    if (!node || !styles) return node;
    Object.entries(styles).forEach(([k, v]) => {
      node.style[k] = String(v);
    });
    return node;
  }

  function showDevToast(message, options = {}) {
    // Disabled in production - no toast notifications shown
    return () => {}; // Return empty cleanup function
  }

  function showFocusCoach(message, options = {}) {
    const bubble = document.createElement("div");
    applyInlineStyles(bubble, {
      position: "fixed",
      right: "20px",
      bottom: "80px",
      zIndex: "13030",
      maxWidth: "min(360px, 88vw)",
      padding: "10px 12px",
      borderRadius: "12px",
      border: "1px solid rgba(100,255,218,0.34)",
      background: options.background || "rgba(7, 21, 39, 0.93)",
      color: "#dff5ff",
      fontSize: "0.88rem",
      lineHeight: "1.35",
      boxShadow: "0 10px 28px rgba(0,0,0,0.34)",
      opacity: "0",
      transform: "translateY(8px)",
      transition: "opacity 220ms ease, transform 220ms ease",
    });
    bubble.textContent = String(message || "");
    document.body.appendChild(bubble);
    requestAnimationFrame(() => {
      bubble.style.opacity = "1";
      bubble.style.transform = "translateY(0)";
    });
    const life = Math.max(1700, Number(options.durationMs || 2800));
    const timer = setTimeout(() => {
      bubble.style.opacity = "0";
      bubble.style.transform = "translateY(8px)";
      setTimeout(() => bubble.remove(), 240);
    }, life);
    return () => {
      clearTimeout(timer);
      bubble.remove();
    };
  }

  function getActiveQuestionContext() {
    const q = testQuestions[testQuestionIndex];
    const stemText = String(questionStem?.textContent || "").replace(/\s+/g, " ").trim();
    const selected = q ? selectedOptions[q.question_id] : "";
    const labels = Array.from(questionOptions?.querySelectorAll("label.option input") || []).map((input) => input.value);
    return { question: q || null, stemText, selected: String(selected || ""), labels };
  }

  function createManualOverlay(baseStyles) {
    const layer = document.createElement("div");
    applyInlineStyles(layer, {
      position: "fixed",
      inset: "0",
      zIndex: "12920",
      pointerEvents: "auto",
      ...baseStyles,
    });
    document.body.appendChild(layer);
    return layer;
  }

  function triggerDevMicroQuizPop() {
    const cleanupFns = [];
    const timers = [];
    const speed = 0.55;
    const deck = [
      { prompt: "Quick: dimensional formula of Force?", options: ["MLT^-2", "ML^2T^-2", "M^-1LT^-2", "ML^-1T^-2"], answer: "MLT^-2" },
      { prompt: "Identify the electrophile:", options: ["OH-", "NO2+", "NH2-", "CN-"], answer: "NO2+" },
      { prompt: "Value of Rydberg constant?", options: ["1.097 x 10^7 m^-1", "9.8 m/s^2", "6.67 x 10^-11", "3 x 10^8"], answer: "1.097 x 10^7 m^-1" },
    ];
    const item = deck[stableRange("devMicroQuiz_item", 0, deck.length - 1)];
    const preGlow = createManualOverlay({
      background: "transparent",
      pointerEvents: "none",
      border: "2px solid rgba(227,242,253,0.25)",
      boxShadow: "inset 0 0 28px rgba(227,242,253,0.48), inset 0 0 80px rgba(100,180,255,0.16)",
      opacity: "0.45",
    });
    const pulseAnim = preGlow.animate([{ opacity: 0.25 }, { opacity: 0.72 }, { opacity: 0.25 }], { duration: 3000, iterations: Infinity, easing: "ease-in-out" });

    const dim = createManualOverlay({
      background: "rgba(8, 18, 34, 0.32)",
      backdropFilter: "blur(3px)",
      WebkitBackdropFilter: "blur(3px)",
      opacity: "0",
      transition: "opacity 220ms ease",
      pointerEvents: "none",
    });
    const card = document.createElement("div");
    applyInlineStyles(card, {
      position: "fixed",
      left: "50%",
      bottom: "-440px",
      transform: "translateX(-50%)",
      width: "min(560px, 92vw)",
      zIndex: "12930",
      borderRadius: "18px",
      overflow: "hidden",
      color: "#ebf8ff",
      border: "1px solid rgba(100,255,218,0.35)",
      background: "linear-gradient(150deg, rgba(10,25,47,0.97), rgba(9,22,40,0.97))",
      boxShadow: "0 24px 52px rgba(0,0,0,0.5)",
      transition: "bottom 320ms cubic-bezier(0.2,0.8,0.2,1)",
    });
    card.innerHTML = `<div style="height:6px;background:rgba(100,255,218,0.12);position:relative;"><div id="devMicroTimer" style="position:absolute;inset:0 auto 0 0;width:100%;background:#64FFDA;transition:width linear;"></div></div><div style="padding:14px 16px 8px;font-weight:700;">Brain buffering? 🧠 Let's recalibrate.</div><div style="padding:0 16px 14px;opacity:.95;">${escapeHTML(item.prompt)}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 16px 16px;">${item.options.map((o) => `<button type="button" class="dev-mq-opt" data-answer="${escapeHTML(o)}" style="border:1px solid rgba(100,255,218,0.35);background:rgba(100,255,218,0.08);color:#dff8f2;border-radius:10px;padding:10px 8px;cursor:pointer;">${escapeHTML(o)}</button>`).join("")}</div>`;
    document.body.appendChild(card);

    let done = false;
    const finalize = (correct) => {
      if (done) return;
      done = true;
      if (correct) {
        showDevToast("Neural link re-established. ⚡ Back to the grind.", { background: "rgba(8,43,22,0.95)", border: "1px solid rgba(0,200,83,0.55)" });
      } else {
        showDevToast("Focus slipping. Take a deep breath and let's go again.", { background: "rgba(48,14,14,0.95)", border: "1px solid rgba(255,109,0,0.55)" });
      }
      deactivateTrigger("devMicroQuizPop");
    };
    cleanupFns.push(showFocusCoach("Coach: 2 second pause. Read stem, then only eliminate 2 wrong options first."));

    card.querySelectorAll(".dev-mq-opt").forEach((btn) => btn.addEventListener("click", () => finalize(btn.getAttribute("data-answer") === item.answer)));
    timers.push(setTimeout(() => {
      dim.style.opacity = "1";
      card.style.bottom = "40px";
      const bar = card.querySelector("#devMicroTimer");
      if (bar) {
        bar.style.transitionDuration = `${Math.floor(5000 * speed)}ms`;
        requestAnimationFrame(() => { bar.style.width = "0%"; });
      }
    }, Math.floor(12000 * speed)));
    timers.push(setTimeout(() => finalize(false), Math.floor(17200 * speed)));

    cleanupFns.push(() => timers.forEach((id) => clearTimeout(id)));
    cleanupFns.push(() => pulseAnim.cancel());
    cleanupFns.push(() => preGlow.remove());
    cleanupFns.push(() => dim.remove());
    cleanupFns.push(() => card.remove());
    return { durationMs: Math.floor(18000 * speed), cleanup: () => cleanupFns.forEach((fn) => fn()) };
  }

  function triggerDevFocusSpotlight() {
    const fadeTargets = [];
    [".test-head", ".hud-panel", ".test-controls", ".score-meta", ".question-meta"].forEach((sel) => {
      document.querySelectorAll(sel).forEach((el) => {
        fadeTargets.push({ el, opacity: el.style.opacity });
        el.style.opacity = "0.2";
        el.style.transition = "opacity 300ms ease";
      });
    });

    const vignette = createManualOverlay({
      background: "radial-gradient(circle at center, rgba(18,18,18,0.12) 18%, rgba(18,18,18,0.9) 76%)",
      opacity: "0",
      transition: "opacity 300ms ease",
    });
    const lock = document.createElement("div");
    applyInlineStyles(lock, {
      position: "fixed",
      left: "50%",
      top: "40%",
      transform: "translate(-50%, -50%)",
      zIndex: "12945",
      color: "#dff2ff",
      fontSize: "34px",
      textShadow: "0 0 18px rgba(100,255,218,0.5)",
    });
    lock.textContent = "🔒";
    vignette.appendChild(lock);

    const node = document.createElement("button");
    node.type = "button";
    applyInlineStyles(node, {
      position: "fixed",
      left: "18%",
      top: "58%",
      width: "34px",
      height: "34px",
      borderRadius: "50%",
      border: "1px solid rgba(100,255,218,0.82)",
      background: "radial-gradient(circle, #64ffda 0%, #0f8f7c 72%)",
      boxShadow: "0 0 24px rgba(100,255,218,0.65)",
      zIndex: "12950",
      cursor: "pointer",
      opacity: "0",
      transition: "opacity 240ms ease",
    });
    document.body.appendChild(node);

    const pathTrace = document.createElement("div");
    applyInlineStyles(pathTrace, {
      position: "fixed",
      right: "24px",
      bottom: "24px",
      zIndex: "12952",
      color: "#e3f2fd",
      fontSize: "0.85rem",
      padding: "8px 10px",
      borderRadius: "10px",
      border: "1px solid rgba(100,255,218,0.32)",
      background: "rgba(18,18,18,0.62)",
    });
    pathTrace.textContent = "Tap moving Focus Node to unlock";
    document.body.appendChild(pathTrace);

    const drift = node.animate(
      [{ transform: "translate(0,0)" }, { transform: "translate(56vw,-20vh)" }, { transform: "translate(16vw,12vh)" }],
      { duration: 5300, easing: "ease-in-out", iterations: Infinity, direction: "alternate" }
    );
    vignette.style.opacity = "1";
    node.style.opacity = "1";

    let unlocked = false;
    node.addEventListener("click", () => {
      unlocked = true;
      if (navigator.vibrate) {
        try { navigator.vibrate(20); } catch (e) {}
      }
      showDevToast("Tunnel vision activated. 🎯 Keep your eyes on the prize.", { background: "rgba(9,44,24,0.95)", border: "1px solid rgba(0,200,83,0.55)" });
      deactivateTrigger("devFocusSpotlight");
    });

    const failTimer = setTimeout(() => {
      if (!unlocked) {
        showDevToast("Focus slipped. Recalibration timed out.");
        deactivateTrigger("devFocusSpotlight");
      }
    }, 9000);
    const removeCoach = showFocusCoach("Coach: track the moving node with calm eyes, not fast clicks.");

    return {
      durationMs: 9600,
      cleanup: () => {
        clearTimeout(failTimer);
        removeCoach();
        drift.cancel();
        vignette.remove();
        node.remove();
        pathTrace.remove();
        fadeTargets.forEach(({ el, opacity }) => { el.style.opacity = opacity || ""; });
      },
    };
  }

  function triggerDevMatrixGlitch() {
    if (!questionStem) return null;
    const trapRegex = /\b(NOT|INCORRECT|EXCEPT)\b/i;
    const sourceHtml = questionStem.innerHTML;
    const sourceText = questionStem.textContent || "";
    const fallbackRegex = /\b(least|most|always|never|only|maximum|minimum|all|none|must|best|correct|wrong)\b/i;
    const numRegex = /\b\d+(\.\d+)?\b/;
    let marker = trapRegex;
    if (!trapRegex.test(sourceText)) {
      if (fallbackRegex.test(sourceText)) marker = fallbackRegex;
      else if (numRegex.test(sourceText)) marker = numRegex;
      else marker = /\b[A-Za-z]{7,}\b/;
    }
    questionStem.innerHTML = sourceHtml.replace(marker, '<span data-dev-matrix-trap="1" style="font-weight:800;">$1</span>');
    const trap = questionStem.querySelector("[data-dev-matrix-trap='1']");
    if (!trap) {
      questionStem.innerHTML = sourceHtml;
      showDevToast("Could not detect a risky token in this stem.");
      return null;
    }
    trap.scrollIntoView({ behavior: "smooth", block: "center" });
    trap.animate(
      [
        { textShadow: "0 0 0 transparent", color: "#FF00FF", filter: "none" },
        { textShadow: "-2px 0 #FF00FF, 2px 0 #00FFFF", color: "#00FFFF", filter: "saturate(1.45)" },
        { textShadow: "2px 0 #FF00FF, -2px 0 #00FFFF", color: "#FF00FF", filter: "saturate(1.45)" },
        { textShadow: "0 0 0 transparent", color: "inherit", filter: "none" },
      ],
      { duration: 520, easing: "steps(2, end)" }
    );
    if (navigator.vibrate) {
      try { navigator.vibrate([24, 34, 24]); } catch (e) {}
    }
    showDevToast("Trap detector active. Slow down and parse this keyword/token.");
    const removeCoach = showFocusCoach("Coach: line ko once silently read karo, phir option mark karo.");
    return { durationMs: 2200, cleanup: () => { removeCoach(); questionStem.innerHTML = sourceHtml; } };
  }

  function triggerDevCognitiveMelt() {
    if (!questionStem || !questionOptions) return null;
    const cleanupFns = [];
    const timers = [];
    const tapNeeded = 3;
    let tapCount = 0;
    let wakeResolved = false;
    // In manual/dev trigger testing, don't force full inactivity wait.
    const isManual = Boolean(arguments[0]?.manual || arguments[0]?.force || arguments[0]?.immediate);
    const inactiveMs = isManual ? 500 : stableRange("dev_cognitiveMelt_inactive", 12000, 15000);
    const driftNodes = [];
    const listeners = [];

    const questionBits = [];
    questionStem.querySelectorAll("p, li, span, strong, em").forEach((n) => {
      if ((n.textContent || "").trim()) questionBits.push(n);
    });
    if (!questionBits.length && questionStem.firstChild) questionBits.push(questionStem);
    const optionBits = Array.from(questionOptions.querySelectorAll("label.option"));
    const allBits = [...questionBits.slice(0, 8), ...optionBits];
    allBits.forEach((node, idx) => {
      const prev = { transform: node.style.transform, transition: node.style.transition, filter: node.style.filter, opacity: node.style.opacity };
      driftNodes.push({ node, prev });
      node.style.transition = "transform 1200ms cubic-bezier(0.22,0.78,0.24,1), opacity 1200ms ease, filter 1200ms ease";
      node.style.transformOrigin = "50% 50%";
      node.style.willChange = "transform, opacity, filter";
      timers.push(setTimeout(() => {
        const dx = stableRange(`dev_cognitiveMelt_dx_${idx}`, -90, 90);
        const dy = stableRange(`dev_cognitiveMelt_dy_${idx}`, 90, 220);
        const rot = stableRange(`dev_cognitiveMelt_rot_${idx}`, -24, 24);
        node.style.transform = `translate(${dx}px, ${dy}px) rotate(${rot}deg) scale(0.96)`;
        node.style.opacity = "0.28";
        node.style.filter = "blur(0.9px)";
      }, 110 + idx * 70));
    });

    const shade = createManualOverlay({
      zIndex: "12965",
      background: "linear-gradient(180deg, rgba(6,15,28,0.22), rgba(6,15,28,0.58))",
      pointerEvents: "none",
      opacity: "0",
      transition: "opacity 260ms ease",
    });
    const wakePanel = document.createElement("div");
    const stemRect = questionStem.getBoundingClientRect();
    const wakeTop = Math.min(window.innerHeight - 140, Math.max(92, Math.round(stemRect.bottom + 18)));
    applyInlineStyles(wakePanel, {
      position: "fixed",
      left: "50%",
      top: `${wakeTop}px`,
      transform: "translateX(-50%)",
      zIndex: "12970",
      borderRadius: "16px",
      border: "1px solid rgba(255,255,255,0.42)",
      background: "rgba(9,23,40,0.96)",
      color: "#f4fbff",
      padding: "14px 16px",
      minWidth: "min(420px, 92vw)",
      textAlign: "center",
      opacity: "1",
      transition: "opacity 180ms ease",
      boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
      pointerEvents: "auto",
      userSelect: "none",
    });
    wakePanel.innerHTML = `<div style="font-weight:800;font-size:1.08rem;margin-bottom:6px;">Cognitive Melt</div><div id="devWakeGuide" style="font-size:.96rem;opacity:.97;">Move cursor to activate tapping</div><button type="button" id="devWakeBtn" tabindex="0" disabled style="margin-top:12px;min-height:60px;min-width:260px;padding:14px 22px;border-radius:14px;border:1px solid #FFD400;background:linear-gradient(135deg,#FFE347,#FFC400);color:#1b1200;font-size:1.08rem;font-weight:800;letter-spacing:.02em;cursor:not-allowed;opacity:.55;pointer-events:auto;position:relative;z-index:1;touch-action:manipulation;box-shadow:0 10px 24px rgba(255,196,0,0.5), inset 0 1px 0 rgba(255,255,255,0.45);">Tap 3 Times (0/3)</button>`;
    document.body.appendChild(wakePanel);

    const resolveWake = () => {
      if (wakeResolved) return;
      wakeResolved = true;
      showDevToast("Focus restored. Back to controlled reading.", { background: "rgba(7,44,24,0.95)" });
      deactivateTrigger("devCognitiveMelt");
    };

    const armMelt = () => {
      shade.style.opacity = "1";
      wakePanel.style.opacity = "1";
      wakePanel.animate(
        [{ transform: "translateX(-50%) scale(0.96)" }, { transform: "translateX(-50%) scale(1)" }],
        { duration: 180, easing: "ease-out", fill: "forwards" }
      );
      const btn = wakePanel.querySelector("#devWakeBtn");
      const guide = wakePanel.querySelector("#devWakeGuide");
      const clickMessages = [
        "Good. Breath in 2 seconds, breath out 2 seconds.",
        "Nice. Now read only the last line of question carefully.",
        "Perfect. Focus lock regained. Solve step-by-step.",
      ];
      let tapArmed = false;
      const onTap = () => {
        if (!tapArmed) return;
        if (wakeResolved) return;
        tapCount += 1;
        if (btn) btn.textContent = `Tap 3 Times (${tapCount}/${tapNeeded})`;
        const msg = clickMessages[Math.min(tapCount - 1, clickMessages.length - 1)];
        showFocusCoach(`Coach: ${msg}`, { durationMs: 1800 });
        if (tapCount >= tapNeeded) resolveWake();
      };
      const onPointerUp = (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        onTap();
      };
      const onTouchStart = (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        onTap();
      };
      const onKeyDown = (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          onTap();
        }
      };
      btn?.addEventListener("pointerup", onPointerUp);
      btn?.addEventListener("touchstart", onTouchStart, { passive: false });
      btn?.addEventListener("keydown", onKeyDown);
      btn?.addEventListener("click", onTap);
      listeners.push({ target: btn, type: "pointerup", fn: onPointerUp });
      listeners.push({ target: btn, type: "touchstart", fn: onTouchStart });
      listeners.push({ target: btn, type: "keydown", fn: onKeyDown });
      listeners.push({ target: btn, type: "click", fn: onTap });

      let moved = 0;
      let prevX = null;
      let prevY = null;
      const moveArmedAt = Date.now() + 80;
      const onMove = (evt) => {
        if (Date.now() < moveArmedAt) return;
        if (wakeResolved) return;
        const x = Number(evt?.clientX || 0);
        const y = Number(evt?.clientY || 0);
        if (prevX == null || prevY == null) {
          prevX = x;
          prevY = y;
          return;
        }
        if (prevX != null && prevY != null) {
          moved += Math.hypot(x - prevX, y - prevY);
        }
        prevX = x;
        prevY = y;
        if (!tapArmed && moved >= 1000) {
          tapArmed = true;
          if (btn) {
            btn.disabled = false;
            btn.style.opacity = "1";
            btn.style.cursor = "pointer";
            btn.textContent = `Tap 3 Times (${tapCount}/${tapNeeded})`;
          }
          if (guide) guide.textContent = "Now tap the button 3 times to restore focus";
          showFocusCoach("Coach: good, tap mode activated. Press the button 3 times.");
        }
      };
      window.addEventListener("mousemove", onMove, { passive: true });
      listeners.push({ target: window, type: "mousemove", fn: onMove });
      cleanupFns.push(showFocusCoach("Coach: aankhon se stem ko track karo. Saans normal, phir restart."));
    };

    timers.push(setTimeout(armMelt, inactiveMs));

    return {
      // Keep enough time after wake UI appears so student can react.
      durationMs: Math.max(38000, inactiveMs + 26000),
      cleanup: () => {
        timers.forEach((id) => clearTimeout(id));
        listeners.forEach(({ target, type, fn }) => target?.removeEventListener(type, fn));
        driftNodes.forEach(({ node, prev }) => {
          node.style.transform = prev.transform || "";
          node.style.transition = prev.transition || "";
          node.style.filter = prev.filter || "";
          node.style.opacity = prev.opacity || "";
          node.style.willChange = "";
        });
        shade.remove();
        wakePanel.remove();
        cleanupFns.forEach((fn) => fn?.());
      },
    };
  }

  function triggerDevSlideToLock() {
    if (!questionOptions) return null;
    const ctx = getActiveQuestionContext();
    const currentLabel = ctx.selected || ctx.labels[0] || "";
    if (!currentLabel) return null;
    const targetLabel = questionOptions.querySelector(`label.option input[value="${currentLabel}"]`)?.closest("label.option");
    if (!targetLabel) return null;
    targetLabel.classList.add("stress-mirage");

    const shell = document.createElement("div");
    applyInlineStyles(shell, {
      marginTop: "10px",
      padding: "10px",
      borderRadius: "12px",
      background: "rgba(255,215,0,0.1)",
      border: "1px solid rgba(255,215,0,0.42)",
    });
    shell.innerHTML = `<div style="font-size:.9rem;color:#ffd700;margin-bottom:8px;">Slide to lock in Option ${escapeHTML(currentLabel)}.</div><input type="range" min="0" max="100" value="0" class="dev-lock-slider" style="width:100%;accent-color:#FFD700;">`;
    targetLabel.appendChild(shell);
    const slider = shell.querySelector(".dev-lock-slider");
    slider?.focus();
    slider?.addEventListener("input", () => {
      const val = Number(slider.value || 0);
      shell.style.background = `linear-gradient(90deg, rgba(255,215,0,0.18) ${val}%, rgba(255,215,0,0.08) ${val}%)`;
      slider.style.accentColor = val >= 96 ? "#00C853" : "#FFD700";
      if (val < 96) return;
      if (navigator.vibrate) {
        try { navigator.vibrate(45); } catch (e) {}
      }
      showDevToast("Locked and loaded. 🔒", { background: "rgba(8,47,23,0.95)", border: "1px solid rgba(0,200,83,0.55)" });
      const triggerRecall = /\d/.test(ctx.stemText || "") || (ctx.question && String(ctx.question.question_type || "").toLowerCase() === "integer");
      deactivateTrigger("devSlideToLock");
      if (triggerRecall) {
        setTimeout(() => activateManualShowcaseTrigger("devBlindRecall", { source: "slide_lock_chain" }), 180);
      }
    });
    return {
      durationMs: 13000,
      cleanup: () => {
        targetLabel.classList.remove("stress-mirage");
        shell.remove();
      },
    };
  }

  function triggerDevBlindRecall() {
    const ctx = getActiveQuestionContext();
    const numeric = (ctx.stemText.match(/\b\d+(\.\d+)?\b/g) || []).slice(0, 3);
    const correctVal = numeric[0] || "Not given";
    const variants = ["Not given", "0.1", "0.2", "0.5", "1", "2", "10"];
    const pool = [correctVal, ...variants.filter((v) => v !== correctVal)].slice(0, 4);
    for (let i = pool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    const layer = createManualOverlay({
      zIndex: "12970",
      background: "rgba(98,0,234,0.94)",
      display: "grid",
      placeItems: "center",
    });
    const card = document.createElement("div");
    applyInlineStyles(card, {
      width: "min(530px, 90vw)",
      borderRadius: "16px",
      background: "rgba(12,9,36,0.86)",
      border: "1px solid rgba(215,183,255,0.52)",
      boxShadow: "0 24px 64px rgba(0,0,0,0.45)",
      padding: "18px",
      color: "#fff",
    });
    card.innerHTML = `<div style="font-weight:700;font-size:1.03rem;margin-bottom:10px;">Wait, what key value did the question give?</div><div style="opacity:.9;margin-bottom:10px;">Memory check in 3 seconds. Choose fast.</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">${pool.map((v) => `<button type="button" class="dev-recall-choice" data-v="${escapeHTML(v)}" style="padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.26);background:rgba(255,255,255,0.08);color:#fff;">${escapeHTML(v)}</button>`).join("")}</div><div style="margin-top:12px;height:6px;background:rgba(255,255,255,0.16);border-radius:999px;overflow:hidden;"><div id="devRecallFuse" style="height:100%;width:100%;background:#ffb300;"></div></div>`;
    layer.appendChild(card);
    layer.animate([{ transform: "rotateY(0deg)" }, { transform: "rotateY(180deg)" }, { transform: "rotateY(360deg)" }], { duration: 420, easing: "ease-in-out" });
    card.querySelector("#devRecallFuse")?.animate([{ width: "100%" }, { width: "0%" }], { duration: 3000, easing: "linear", fill: "forwards" });
    const timeout = setTimeout(() => {
      showDevToast("Careful! Don't lose track of your variables.");
      deactivateTrigger("devBlindRecall");
    }, 3050);
    card.querySelectorAll(".dev-recall-choice").forEach((btn) => btn.addEventListener("click", () => {
      const ok = btn.getAttribute("data-v") === correctVal;
      showDevToast(ok ? "Memory of an elephant! +10 Accuracy XP." : "Careful! Don't lose track of your variables.", {
        background: ok ? "rgba(9,47,24,0.95)" : "rgba(48,14,14,0.95)",
      });
      deactivateTrigger("devBlindRecall");
    }));
    return { durationMs: 3600, cleanup: () => { clearTimeout(timeout); layer.remove(); } };
  }

  function triggerDevConfidenceSlider() {
    const host = getTestCard();
    if (!host) return null;
    const panel = document.createElement("div");
    applyInlineStyles(panel, {
      marginTop: "12px",
      borderRadius: "14px",
      border: "1px solid rgba(255,255,255,0.14)",
      background: "rgba(8,20,35,0.78)",
      padding: "12px",
      color: "#eaf5ff",
    });
    panel.innerHTML = `<div style="font-weight:700;margin-bottom:7px;">Confidence Slider (Risk vs Reward)</div><input type="range" min="0" max="100" value="50" id="devConfRange" style="width:100%;accent-color:#FF6D00;"><div style="display:flex;justify-content:space-between;margin-top:6px;font-size:.9rem;"><span id="devConfBand">Calculated Risk</span><span id="devConfPts">+2 / -1</span></div><button type="button" id="devConfCommit" class="btn primary small" style="margin-top:10px;">Lock confidence</button>`;
    host.appendChild(panel);
    const range = panel.querySelector("#devConfRange");
    const band = panel.querySelector("#devConfBand");
    const pts = panel.querySelector("#devConfPts");
    const update = () => {
      const val = Number(range?.value || 0);
      if (val <= 30) {
        if (range) range.style.accentColor = "#D50000";
        if (band) band.textContent = "High Risk";
        if (pts) pts.textContent = "0 / 0";
      } else if (val <= 70) {
        if (range) range.style.accentColor = "#FF6D00";
        if (band) band.textContent = "Calculated Risk";
        if (pts) pts.textContent = "+2 / -1";
      } else {
        if (range) range.style.accentColor = "#00C853";
        if (band) band.textContent = "Sure Shot";
        if (pts) pts.textContent = "+4 / -2";
      }
    };
    update();
    range?.addEventListener("input", update);
    panel.querySelector("#devConfCommit")?.addEventListener("click", () => {
      const val = Number(range?.value || 0);
      const confidenceBias = val >= 90 ? 0.67 : val <= 25 ? 0.38 : 0.52;
      const correct = Math.random() < confidenceBias;
      if (val >= 95 && correct) {
        showDevToast("Calculated risk paid off! High conviction, high reward. 🎯");
      } else if (val >= 95 && !correct) {
        getAppShell()?.animate([{ transform: "translateX(0)" }, { transform: "translateX(-8px)" }, { transform: "translateX(8px)" }, { transform: "translateX(0)" }], { duration: 280, easing: "ease-in-out" });
        showDevToast("Overconfidence penalty applied. Stay grounded.");
      } else if (val <= 5 && !correct) {
        showDevToast("Good thing you hedged your bets. Negative marking avoided.");
      } else {
        showDevToast("Confidence logged. Keep calibrating your risk.");
      }
      deactivateTrigger("devConfidenceSlider");
    });
    return { durationMs: 18000, cleanup: () => panel.remove() };
  }

  function triggerDifficultyCheckPrompt() {
    if (state.feedbackPromptOpen) return null;
    const qid = String(state.currentQuestionId || "");
    const userState = currentUserState();
    const mood = inferFeedbackMood(userState);
    const prompt = "How was that last question?";
    const triggerName = "difficultyCheckPrompt";

    state.feedbackPromptOpen = true;
    state.feedbackLastShownAt = Date.now();
    state.lastFeedbackQuestionType = "difficulty";
    acquireInterruptionLock("feedback");

    const overlay = document.createElement("div");
    overlay.className = "stress-difficulty-check-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `
      <div class="stress-difficulty-check-card">
        <div class="stress-difficulty-check-eyebrow">Quick Check</div>
        <div class="stress-difficulty-check-title">${escapeHTML(prompt)}</div>
        <div class="stress-difficulty-check-sub">Your honest rating before we continue.</div>
        <div class="stress-difficulty-check-options">
          <button type="button" class="stress-difficulty-check-option easy" data-level="Easy">
            <span class="stress-difficulty-check-emoji" aria-hidden="true">😎</span>
            <span class="stress-difficulty-check-label">Easy</span>
          </button>
          <button type="button" class="stress-difficulty-check-option medium" data-level="Medium">
            <span class="stress-difficulty-check-emoji" aria-hidden="true">🤔</span>
            <span class="stress-difficulty-check-label">Medium</span>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    let finalized = false;
    const closeTimer = setTimeout(() => finalizeChoice("No response"), FEEDBACK_PROMPT_MAX_OPEN_MS);

    function finalizeChoice(choice) {
      if (finalized) return;
      finalized = true;
      clearTimeout(closeTimer);
      const selected = String(choice || "");
      const selectedLower = selected.toLowerCase();

      const payload = {
        at: Date.now(),
        reason: "trigger_difficulty_check",
        kind: "difficulty",
        mood,
        answer: selected,
        question: prompt,
        question_id: qid || "",
      };
      state.feedbackResponseHistory.push(payload);
      if (state.feedbackResponseHistory.length > 30) {
        state.feedbackResponseHistory = state.feedbackResponseHistory.slice(-30);
      }

      if (selectedLower.includes("hard")) state.feedbackDifficultyPreference = "hard";
      else if (selectedLower.includes("easy")) state.feedbackDifficultyPreference = "easy";
      else state.feedbackDifficultyPreference = "medium";

      const snapshot = snapshotFeedbackMetrics(userState);
      if (sessionId) {
        postJSON(`/session/${sessionId}/trigger-feedback`, {
          trigger: "student_feedback_pulse:difficulty_check",
          intensity: applyFeedbackIntensityBias("low"),
          pre_metrics: snapshot,
          post_metrics: snapshot,
          recovery_metrics: snapshot,
          note: `[difficulty-check] ${prompt} -> ${selected}`,
        }).catch((err) => debugLog("feedback_persist_error", err?.message || String(err)));
      }

      // Trigger AI recommender again with explicit difficulty feedback context.
      const recommendedLevel = state.feedbackDifficultyPreference;
      setTimeout(() => {
        requestTriggerFromAI("difficulty_feedback_submitted", {
          source_trigger: triggerName,
          difficulty_feedback: selected || "No response",
          preferred_trigger_difficulty: recommendedLevel,
          question_id: qid || "",
        });
      }, SCREEN_QUIET_BREAK_MS + 220);

      deactivateTrigger(triggerName);
    }

    function showSelectionResult(choice) {
      const selected = String(choice || "Medium").trim();
      const selectedLower = selected.toLowerCase();
      const easyPicked = selectedLower.includes("easy");
      const resultClass = easyPicked ? "is-easy" : "is-medium";
      const headline = easyPicked
        ? "Easy? We'll remember you said that."
        : "When people are unsure about the question they chose medium.";
      const sub = "Preparing the next one...";
      const emoji = easyPicked ? "😏" : "🤨";

      const card = overlay.querySelector(".stress-difficulty-check-card");
      if (!card) {
        finalizeChoice(selected);
        return;
      }

      card.className = `stress-difficulty-check-card stress-difficulty-check-result ${resultClass}`;
      card.innerHTML = `
        <div class="stress-difficulty-check-result-emoji" aria-hidden="true">${emoji}</div>
        <div class="stress-difficulty-check-result-title">${escapeHTML(headline)}</div>
        <div class="stress-difficulty-check-result-sub">${escapeHTML(sub)}</div>
      `;

      setTimeout(() => finalizeChoice(selected), 1400);
    }

    overlay.querySelectorAll(".stress-difficulty-check-option").forEach((btn) => {
      btn.addEventListener("click", () => {
        const level = btn.getAttribute("data-level") || "Medium";
        showSelectionResult(level);
      });
    });

    return {
      durationMs: 0,
      cleanup: () => {
        clearTimeout(closeTimer);
        overlay.remove();
        state.feedbackPromptOpen = false;
        releaseInterruptionLock("feedback");
      },
    };
  }

  // ========================================================================
  // Question-Level Triggers for Focus Zones Test
  // Using beautiful glassmorphic design matching existing triggers
  // ========================================================================

  // Q1 → SPOTLIGHT_HUNT
  // Fires 6 seconds after Q1 loads. Dark overlay with 320px radius lit circle
  // that drifts following sine wave. Runs indefinitely.
  function triggerSpotlightHunt() {
    if (!questionBody) return null;
    
    const spotlight = document.createElement('div');
    spotlight.className = 'stress-spotlight-overlay';
    spotlight.setAttribute('role', 'presentation');
    spotlight.setAttribute('aria-hidden', 'true');
    
    // Start at center
    let centerX = window.innerWidth / 2;
    let centerY = window.innerHeight / 2;
    let time = 0;
    
    spotlight.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: radial-gradient(
        circle 160px at ${centerX}px ${centerY}px,
        transparent 0%,
        rgba(0,0,0,0.95) 160px
      );
      pointer-events: none;
      z-index: 9998;
    `;
    
    // Sine wave drift animation
    const driftInterval = setInterval(() => {
      time += 0.05;
      const driftX = Math.sin(time) * 100;
      const driftY = Math.cos(time * 0.7) * 80;
      const spotX = centerX + driftX;
      const spotY = centerY + driftY;
      
      spotlight.style.background = `radial-gradient(
        circle 160px at ${spotX}px ${spotY}px,
        transparent 0%,
        rgba(0,0,0,0.95) 160px
      )`;
    }, 50);
    
    document.body.appendChild(spotlight);
    
    return {
      durationMs: 0, // Runs indefinitely
      cleanup: () => {
        clearInterval(driftInterval);
        spotlight.remove();
      },
    };
  }

  // Q2 → HARD_FOG
  function triggerHardFog() {
    if (!questionBody) return null;
    
    const timers = [];
    let fogElement = null;
    let stressCountdown = null;
    let countdownInterval = null; // Store interval reference for cleanup
    const triggerQuestionId = state.currentQuestionId; // Store the question ID when trigger starts
    let isCleanedUp = false; // Flag to prevent actions after cleanup
    
    // Monitor for question changes and cleanup immediately
    const questionChangeMonitor = setInterval(() => {
      if (state.currentQuestionId !== triggerQuestionId && !isCleanedUp) {
        console.log('[triggerHardFog] Question changed detected by monitor - cleaning up immediately');
        isCleanedUp = true;
        clearInterval(questionChangeMonitor);
        
        // Clear all timers
        timers.forEach(t => clearTimeout(t));
        if (countdownInterval) clearInterval(countdownInterval);
        
        // Remove all elements
        const overlays = document.querySelectorAll('.stress-difficulty-check-overlay');
        overlays.forEach(el => el.remove());
        if (fogElement) fogElement.remove();
        if (stressCountdown) stressCountdown.remove();
      }
    }, 100); // Check every 100ms
    
    const overlay = document.createElement('div');
    overlay.className = 'stress-difficulty-check-overlay';
    overlay.innerHTML = `
      <div class="stress-difficulty-check-card">
        <div class="stress-difficulty-check-emoji">🤔</div>
        <div class="stress-difficulty-check-title">Rate Previous Question</div>
        <div class="stress-difficulty-check-sub">How difficult was it for you?</div>
        <div class="stress-difficulty-check-options" style="grid-template-columns: repeat(3, 1fr);">
          <button class="stress-difficulty-check-option easy" data-rating="easy">
            <span class="stress-difficulty-check-emoji">😊</span>
            <span style="font-size: 18px; font-weight: 700;">Easy</span>
          </button>
          <button class="stress-difficulty-check-option medium" data-rating="medium">
            <span class="stress-difficulty-check-emoji">😐</span>
            <span style="font-size: 18px; font-weight: 700;">Medium</span>
          </button>
          <button class="stress-difficulty-check-option" style="border-color: rgba(255, 99, 132, 0.72); color: #ff6384;" data-rating="hard">
            <span class="stress-difficulty-check-emoji">😰</span>
            <span style="font-size: 18px; font-weight: 700;">Hard</span>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    
    const showSelectionResult = (choice) => {
      const selected = String(choice || "Medium").trim();
      const selectedLower = selected.toLowerCase();
      const easyPicked = selectedLower.includes("easy");
      const hardPicked = selectedLower.includes("hard");
      
      let emoji, headline;
      if (easyPicked) {
        emoji = "😏";
        headline = "Easy? We'll remember you said that.";
      } else if (hardPicked) {
        emoji = "😰";
        headline = "Hard? At least you're honest about your limits.";
      } else {
        emoji = "🤨";
        headline = "When people are unsure they chose medium.";
      }
      
      const card = overlay.querySelector('.stress-difficulty-check-card');
      if (!card) {
        continueSequence();
        return;
      }
      
      card.className = 'stress-difficulty-check-card stress-difficulty-check-result';
      card.innerHTML = `
        <div class="stress-difficulty-check-result-emoji" aria-hidden="true">${emoji}</div>
        <div class="stress-difficulty-check-result-title">${headline}</div>
        <div class="stress-difficulty-check-result-sub">Preparing the next one...</div>
      `;
      
      setTimeout(() => continueSequence(), 1400);
    };
    
    const continueSequence = () => {
      // Check if we're still on the same question
      if (state.currentQuestionId !== triggerQuestionId) {
        console.log('[triggerHardFog] Question changed, stopping sequence');
        overlay.remove();
        return;
      }
      
      overlay.remove();
      
      timers.push(setTimeout(() => {
        // Check again before showing warning
        if (state.currentQuestionId !== triggerQuestionId) {
          console.log('[triggerHardFog] Question changed, stopping at warning');
          return;
        }
        
        const warningOverlay = document.createElement('div');
        warningOverlay.className = 'stress-difficulty-check-overlay';
        warningOverlay.innerHTML = `
          <div class="binary-card">
            <div class="stress-difficulty-check-emoji" style="font-size: 62px;">⚠️</div>
            <div class="binary-question">Hard Question Ahead</div>
            <div class="stress-difficulty-check-sub">Prepare yourself. This one is challenging.</div>
          </div>
        `;
        document.body.appendChild(warningOverlay);
        
        timers.push(setTimeout(() => {
          // Check again before showing countdown
          if (state.currentQuestionId !== triggerQuestionId) {
            console.log('[triggerHardFog] Question changed, stopping at countdown');
            warningOverlay.remove();
            return;
          }
          
          warningOverlay.remove();
          
          stressCountdown = document.createElement('div');
          stressCountdown.className = 'trigger-countdown';
          document.body.appendChild(stressCountdown);
          
          let timeLeft = 30;
          stressCountdown.textContent = `⏱️ ${timeLeft}s`;
          
          countdownInterval = setInterval(() => {
            // Check if question changed during countdown
            if (state.currentQuestionId !== triggerQuestionId) {
              console.log('[triggerHardFog] Question changed during countdown, stopping');
              clearInterval(countdownInterval);
              if (stressCountdown) stressCountdown.remove();
              if (fogElement) fogElement.remove();
              return;
            }
            
            timeLeft--;
            if (timeLeft <= 0) {
              clearInterval(countdownInterval);
              if (typeof skipToNextQuestion === 'function') {
                skipToNextQuestion();
              }
              return;
            }
            stressCountdown.textContent = `⏱️ ${timeLeft}s`;
            if (timeLeft <= 10) {
              stressCountdown.classList.add('urgent');
            }
          }, 1000);
          
          timers.push(setTimeout(() => {
            // Check if question changed before applying fog
            if (state.currentQuestionId !== triggerQuestionId) {
              console.log('[triggerHardFog] Question changed, not applying fog');
              return;
            }
            
            fogElement = document.createElement('div');
            fogElement.className = 'trigger-fog-overlay';
            
            if (questionBody.parentElement) {
              questionBody.style.position = 'relative';
              questionBody.appendChild(fogElement);
            }
            
            timers.push(setTimeout(() => {
              if (fogElement) fogElement.remove();
            }, 45000));
            
          }, 3500));
          
        }, 6000));
        
      }, 2500));
    };
    
    overlay.querySelectorAll('.stress-difficulty-check-option').forEach(btn => {
      btn.addEventListener('click', () => {
        const rating = btn.getAttribute('data-rating') || 'medium';
        showSelectionResult(rating);
      });
    });
    
    return {
      durationMs: 0,
      cleanup: () => {
        console.log('[triggerHardFog] Cleanup called - clearing', timers.length, 'timers');
        isCleanedUp = true;
        clearInterval(questionChangeMonitor);
        timers.forEach(t => clearTimeout(t));
        if (countdownInterval) {
          console.log('[triggerHardFog] Clearing countdown interval');
          clearInterval(countdownInterval);
        }
        overlay.remove();
        if (fogElement) {
          console.log('[triggerHardFog] Removing fog element');
          fogElement.remove();
        }
        if (stressCountdown) {
          console.log('[triggerHardFog] Removing countdown element');
          stressCountdown.remove();
        }
      },
    };
  }

  // Q3 → FLIP_CYCLE
  // Fires 5s after Q3 loads. Flips 180°, stays 5s, flips back, waits 5s, repeats 5 times.
  // Final flip state stays permanently.
  function triggerFlipCycle() {
    const shell = getAppShell();
    if (!shell) return null;
    
    let flipCount = 0;
    const maxFlips = 5;
    let isFlipped = false;
    
    shell.style.transition = 'transform 1s ease-in-out';
    
    const doFlip = () => {
      if (flipCount >= maxFlips) return;
      
      isFlipped = !isFlipped;
      shell.style.transform = isFlipped ? 'rotateX(180deg)' : 'rotateX(0deg)';
      flipCount++;
      
      if (flipCount < maxFlips) {
        setTimeout(doFlip, 5000); // Wait 5s before next flip
      }
      // If flipCount === maxFlips, leave it in final state permanently
    };
    
    doFlip(); // Start first flip
    
    return {
      durationMs: 0, // Runs indefinitely, final state stays
      cleanup: () => {
        // Don't reset transform - final flip state should stay
      },
    };
  }

  // Q4 → ACCURACY_TEST
  function triggerAccuracyTest(ctx) {
    if (!questionBody) return null;
    
    console.log('[triggerAccuracyTest] Starting accuracy test');
    
    let shakeTimeoutId = null;
    const timePenalty = 180000; // 3 minutes penalty (180 seconds)
    const createdOverlays = []; // Track all created overlays for cleanup
    let isCleanedUp = false; // Flag to prevent showing popups after cleanup
    const triggerQuestionId = state.currentQuestionId; // Store the question ID when trigger starts
    
    // Create the initial popup - exact colors from design
    const overlay = document.createElement('div');
    overlay.className = 'stress-difficulty-check-overlay';
    overlay.style.zIndex = '10000';
    createdOverlays.push(overlay);
    overlay.innerHTML = `
      <div class="stress-difficulty-check-card" style="
        max-width: 420px; 
        padding: 40px 28px; 
        background: rgba(30, 25, 20, 0.98);
        border: 1px solid rgba(120, 100, 80, 0.3);
        border-radius: 20px;
      ">
        <div class="stress-difficulty-check-emoji" style="font-size: 80px; margin-bottom: 20px;">🎯</div>
        <div class="stress-difficulty-check-eyebrow" style="
          font-size: 11px; 
          letter-spacing: 0.2em; 
          text-transform: uppercase; 
          color: #D4A574; 
          font-weight: 700; 
          margin-bottom: 16px;
        ">ACCURACY CHECK</div>
        <div class="stress-difficulty-check-title" style="
          font-size: 26px; 
          font-weight: 700; 
          margin-bottom: 12px; 
          line-height: 1.3;
          color: #FFFFFF;
        ">Wanna test your accuracy?</div>
        <div class="stress-difficulty-check-sub" style="
          font-size: 14px; 
          color: rgba(180, 170, 160, 0.85); 
          font-style: italic; 
          margin-bottom: 28px;
        ">(Say yes if you're confident you can read anything.)</div>
        <div class="binary-actions" style="display: flex; gap: 12px; width: 100%;">
          <button class="binary-btn" id="accuracy-no" style="
            flex: 1; 
            background: rgba(50, 45, 40, 0.6); 
            border: 1px solid rgba(100, 90, 80, 0.4); 
            color: rgba(200, 190, 180, 0.9); 
            padding: 16px 24px; 
            border-radius: 12px; 
            font-size: 16px; 
            font-weight: 600; 
            cursor: pointer; 
            transition: all 0.2s;
          ">No</button>
          <button class="binary-btn" id="accuracy-yes" style="
            flex: 1; 
            background: #F5A623; 
            border: 1px solid #F5A623; 
            color: #1A1410; 
            padding: 16px 24px; 
            border-radius: 12px; 
            font-size: 16px; 
            font-weight: 700; 
            cursor: pointer; 
            transition: all 0.2s;
          ">Yes</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    
    // Apply time penalty and show penalty UI (Image 2)
    const applyTimePenalty = () => {
      console.log('[triggerAccuracyTest] Applying time penalty:', timePenalty, 'ms');
      
      // Apply penalty by making it appear the exam started earlier
      // This increases the elapsed time, reducing the remaining time
      if (state.examStartedAt && state.examStartedAt > 0) {
        state.examStartedAt -= timePenalty;
        console.log('[triggerAccuracyTest] Exam timer reduced by', timePenalty / 1000, 'seconds. New examStartedAt:', state.examStartedAt);
      }
      
      // Show penalty notification (Image 2 style)
      const penaltyOverlay = document.createElement('div');
      penaltyOverlay.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 10001;
        width: calc(100% - 40px);
        max-width: 460px;
        animation: slideUpFade 0.3s ease;
      `;
      
      const penaltySeconds = Math.floor(timePenalty / 1000);
      const penaltyMinutes = Math.floor(penaltySeconds / 60);
      const remainingSeconds = penaltySeconds % 60;
      const penaltyDisplay = penaltyMinutes > 0 
        ? `${penaltyMinutes}:${remainingSeconds.toString().padStart(2, '0')}`
        : `${penaltySeconds}s`;
      
      penaltyOverlay.innerHTML = `
        <div style="
          background: linear-gradient(135deg, rgba(127, 29, 29, 0.95), rgba(153, 27, 27, 0.95));
          border: 1px solid rgba(248, 113, 113, 0.4);
          border-radius: 16px;
          padding: 20px 24px;
          display: flex;
          align-items: center;
          gap: 16px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        ">
          <div style="
            font-size: 42px;
            line-height: 1;
            flex-shrink: 0;
          ">⏱️</div>
          <div style="flex: 1;">
            <div style="
              font-size: 12px;
              letter-spacing: 0.1em;
              text-transform: uppercase;
              color: rgba(252, 165, 165, 0.9);
              font-weight: 700;
              margin-bottom: 4px;
            ">TIME PENALTY</div>
            <div style="
              font-size: 14px;
              color: rgba(254, 202, 202, 0.95);
              line-height: 1.4;
            ">You declined the challenge. −${penaltyDisplay} deducted.</div>
          </div>
          <div style="
            font-size: 32px;
            font-weight: 800;
            color: #fca5a5;
            flex-shrink: 0;
          ">−${penaltyDisplay}</div>
        </div>
      `;
      
      document.body.appendChild(penaltyOverlay);
      
      // Remove penalty notification after 5 seconds
      setTimeout(() => {
        penaltyOverlay.style.opacity = '0';
        penaltyOverlay.style.transform = 'translateX(-50%) translateY(20px)';
        penaltyOverlay.style.transition = 'all 0.3s ease';
        setTimeout(() => penaltyOverlay.remove(), 300);
      }, 5000);
    };
    
    // Show roast message
    const showRoast = (message, callback) => {
      if (isCleanedUp || state.stage === "results") return;
      console.log('[triggerAccuracyTest] Showing roast:', message);
      const roastOverlay = document.createElement('div');
      roastOverlay.className = 'stress-difficulty-check-overlay';
      roastOverlay.style.zIndex = '10002';
      roastOverlay.innerHTML = `
        <div class="binary-card" style="max-width: 420px; padding: 28px 24px;">
          <div class="binary-question" style="font-size: 20px; font-weight: 600; line-height: 1.4; color: #f8fafc;">${message}</div>
        </div>
      `;
      document.body.appendChild(roastOverlay);
      
      setTimeout(() => {
        roastOverlay.remove();
        if (callback) callback();
      }, 4500);
    };
    
    // Show post-shake check
    const showPostShakeCheck = () => {
      // Don't show if we've moved to a different question or cleanup was called or test ended
      if (isCleanedUp || state.currentQuestionId !== triggerQuestionId || state.stage === "results") {
        console.log('[triggerAccuracyTest] Skipping post-shake check - question changed or cleaned up');
        return;
      }
      
      console.log('[triggerAccuracyTest] Showing post-shake check');
      const postOverlay = document.createElement('div');
      postOverlay.className = 'stress-difficulty-check-overlay';
      postOverlay.style.zIndex = '10002';
      createdOverlays.push(postOverlay); // Track for cleanup
      postOverlay.innerHTML = `
        <div class="stress-difficulty-check-card" style="max-width: 420px; padding: 32px 24px;">
          <div class="stress-difficulty-check-title" style="font-size: 22px; font-weight: 700; margin-bottom: 24px;">Could you read through the shake?</div>
          <div class="binary-actions" style="display: flex; gap: 12px; width: 100%;">
            <button class="binary-btn" id="post-no" style="flex: 1; background: rgba(248, 113, 113, 0.15); border: 1px solid rgba(248, 113, 113, 0.4); color: #f87171; padding: 14px 20px; border-radius: 12px; font-size: 15px; font-weight: 600; cursor: pointer;">No, I couldn't</button>
            <button class="binary-btn" id="post-yes" style="flex: 1; background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.4); color: #22c55e; padding: 14px 20px; border-radius: 12px; font-size: 15px; font-weight: 600; cursor: pointer;">Yes, I could</button>
          </div>
        </div>
      `;
      document.body.appendChild(postOverlay);
      
      // Handle "No, I couldn't"
      document.getElementById('post-no').addEventListener('click', () => {
        console.log('[triggerAccuracyTest] User said they could not read');
        postOverlay.remove();
        showRoast("Honesty is rare. But weakness still has a price. ⏱️", applyTimePenalty);
      });
      
      // Handle "Yes, I could" - show explain trap
      document.getElementById('post-yes').addEventListener('click', () => {
        console.log('[triggerAccuracyTest] User said they could read - showing explain trap');
        postOverlay.remove();
        
        const explainOverlay = document.createElement('div');
        explainOverlay.className = 'stress-difficulty-check-overlay';
        explainOverlay.style.zIndex = '10003';
        createdOverlays.push(explainOverlay); // Track for cleanup
        explainOverlay.innerHTML = `
          <div class="stress-difficulty-check-card" style="max-width: 480px; padding: 32px 24px;">
            <div class="stress-difficulty-check-title" style="font-size: 22px; font-weight: 700; margin-bottom: 12px;">Impressive! Explain how:</div>
            <div class="stress-difficulty-check-sub" style="font-size: 14px; color: rgba(226, 232, 240, 0.7); margin-bottom: 16px;">Tell us your technique for reading through the shake.</div>
            <textarea class="trigger-textarea" placeholder="Type your explanation..." style="
              width: 100%;
              min-height: 120px;
              padding: 14px;
              border-radius: 10px;
              border: 1px solid rgba(148, 163, 184, 0.3);
              background: rgba(15, 23, 42, 0.6);
              color: #e2e8f0;
              font-size: 15px;
              font-family: inherit;
              resize: vertical;
              margin-bottom: 16px;
            "></textarea>
            <button class="binary-btn" id="explain-submit" style="
              width: 100%;
              background: rgba(59, 130, 246, 0.2);
              border: 1px solid rgba(59, 130, 246, 0.5);
              color: #3b82f6;
              padding: 14px 20px;
              border-radius: 12px;
              font-size: 15px;
              font-weight: 600;
              cursor: pointer;
            ">Submit Explanation</button>
          </div>
        `;
        document.body.appendChild(explainOverlay);
        
        document.getElementById('explain-submit').addEventListener('click', () => {
          console.log('[triggerAccuracyTest] User submitted explanation');
          explainOverlay.remove();
          showRoast("Interesting technique. We'll see if it actually worked. 🤔", null);
        });
      });
    };
    
    // Handle "No" button click
    document.getElementById('accuracy-no').addEventListener('click', () => {
      console.log('[triggerAccuracyTest] User clicked No - applying penalty immediately');
      overlay.remove();
      applyTimePenalty();
    });
    
    // Handle "Yes" button click - activate heartbeat shake
    document.getElementById('accuracy-yes').addEventListener('click', () => {
      console.log('[triggerAccuracyTest] User clicked Yes - activating heartbeat shake');
      overlay.remove();
      
      // Remove accuracyTest from active map WITHOUT calling cleanup
      // This allows heartbeatVibration to activate (max 1 active trigger)
      // but keeps our state intact (isCleanedUp stays false)
      if (active.has('accuracyTest')) {
        const entry = active.get('accuracyTest');
        // Clear any timers but don't call cleanup
        (entry.timers || []).forEach((timerId) => clearTimeout(timerId));
        active.delete('accuracyTest');
        console.log('[triggerAccuracyTest] Removed accuracyTest from active map (without cleanup)');
      }
      
      // Small delay to ensure overlay is removed
      setTimeout(() => {
        // Activate heartbeat vibration trigger
        // Note: The system caps duration at 20 seconds max, so we use that
        const shakeDuration = 20000; // 20 seconds (system maximum)
        
        console.log('[triggerAccuracyTest] Calling activateTrigger for heartbeatVibration');
        const result = activateTrigger('heartbeatVibration', {
          userState: currentUserState(),
          force: true,
          reason: 'accuracy_test:shake_challenge',
          timeoutMs: shakeDuration
        });
        
        console.log('[triggerAccuracyTest] activateTrigger result:', result);
        
        if (result) {
          console.log('[triggerAccuracyTest] Heartbeat shake activated successfully for', shakeDuration, 'ms');
          // After shake completes, show post-shake check
          shakeTimeoutId = setTimeout(() => {
            console.log('[triggerAccuracyTest] Shake complete - showing post-shake check');
            showPostShakeCheck();
          }, shakeDuration);
        } else {
          console.error('[triggerAccuracyTest] Failed to activate heartbeat shake');
          // Show post-shake check immediately if activation failed
          showPostShakeCheck();
        }
      }, 100);
    });
    
    return {
      durationMs: 0, // Immediate popup
      cleanup: () => {
        console.log('[triggerAccuracyTest] Cleanup called - removing all overlays');
        isCleanedUp = true; // Set flag to prevent future popups
        
        // Remove all created overlays
        createdOverlays.forEach(el => {
          if (el && el.parentNode) {
            el.remove();
          }
        });
        
        // Clear the shake timeout
        if (shakeTimeoutId) {
          clearTimeout(shakeTimeoutId);
          shakeTimeoutId = null;
        }
      },
    };
  }

  // Q5 → READING_TEST
  function triggerReadingTest() {
    if (!questionBody) return null;
    
    const timers = [];
    
    const fingerOverlay = document.createElement('div');
    fingerOverlay.className = 'stress-difficulty-check-overlay';
    fingerOverlay.innerHTML = `
      <div class="binary-card">
        <div style="font-size: 72px; line-height: 1;">👉 READ CAREFULLY 👈</div>
      </div>
    `;
    document.body.appendChild(fingerOverlay);
    
    timers.push(setTimeout(() => {
      fingerOverlay.remove();
      
      timers.push(setTimeout(() => {
        const blurOverlay = document.createElement('div');
        blurOverlay.className = 'trigger-blur-overlay';
        
        const unlockBtn = document.createElement('button');
        unlockBtn.className = 'trigger-unlock-btn';
        unlockBtn.textContent = '🔓 Unlock';
        
        blurOverlay.appendChild(unlockBtn);
        
        if (questionBody.parentElement) {
          questionBody.style.position = 'relative';
          questionBody.appendChild(blurOverlay);
        }
        
        unlockBtn.addEventListener('click', () => {
          const challengeOverlay = document.createElement('div');
          challengeOverlay.className = 'stress-difficulty-check-overlay';
          challengeOverlay.innerHTML = `
            <div class="stress-difficulty-check-card" style="width: min(500px, calc(100vw - 34px));">
              <div class="stress-difficulty-check-title">What was the question about?</div>
              <textarea class="trigger-textarea" id="reading-answer" placeholder="Type what you remember..."></textarea>
              <div class="binary-actions">
                <button class="binary-btn" id="reading-submit" style="background: rgba(26, 215, 181, 0.15); border-color: rgba(26, 215, 181, 0.5); color: #28d8af;">Submit</button>
                <button class="binary-btn" id="reading-giveup">I gave up</button>
              </div>
            </div>
          `;
          document.body.appendChild(challengeOverlay);
          
          const showRoastAndUnlock = (message) => {
            challengeOverlay.remove();
            
            const roastOverlay = document.createElement('div');
            roastOverlay.className = 'stress-difficulty-check-overlay';
            roastOverlay.innerHTML = `
              <div class="binary-card">
                <div class="binary-question">${message}</div>
              </div>
            `;
            document.body.appendChild(roastOverlay);
            
            setTimeout(() => {
              roastOverlay.remove();
              blurOverlay.remove();
            }, 4500);
          };
          
          document.getElementById('reading-submit').addEventListener('click', () => {
            const answer = document.getElementById('reading-answer').value.trim();
            if (answer.length < 10) {
              showRoastAndUnlock("That's barely an attempt! But fine, you're unlocked. 😤");
            } else {
              showRoastAndUnlock("Nice try, but you still wasted time! Focus better next time. 😏");
            }
          });
          
          document.getElementById('reading-giveup').addEventListener('click', () => {
            showRoastAndUnlock("Giving up already? Weak! But at least you're honest. 😈");
          });
        });
        
      }, 8000));
      
    }, 4000));
    
    return {
      durationMs: 0,
      cleanup: () => {
        timers.forEach(t => clearTimeout(t));
        fingerOverlay.remove();
      },
    };
  }

  // Q6 → HARD_PEER_DOUBT
  function triggerHardPeerDoubt() {
    if (!questionBody) return null;
    
    const timers = [];
    let fogElement = null;
    let stressCountdown = null;
    let countdownInterval = null; // Store interval reference for cleanup
    let interceptionCount = 0;
    const maxInterceptions = 2;
    
    const overlay = document.createElement('div');
    overlay.className = 'stress-difficulty-check-overlay';
    overlay.innerHTML = `
      <div class="stress-difficulty-check-card">
        <div class="stress-difficulty-check-emoji">🤔</div>
        <div class="stress-difficulty-check-title">Rate Previous Question</div>
        <div class="stress-difficulty-check-sub">How difficult was it for you?</div>
        <div class="stress-difficulty-check-options" style="grid-template-columns: repeat(3, 1fr);">
          <button class="stress-difficulty-check-option easy">
            <span class="stress-difficulty-check-emoji">😊</span>
            <span style="font-size: 18px; font-weight: 700;">Easy</span>
          </button>
          <button class="stress-difficulty-check-option medium">
            <span class="stress-difficulty-check-emoji">😐</span>
            <span style="font-size: 18px; font-weight: 700;">Medium</span>
          </button>
          <button class="stress-difficulty-check-option" style="border-color: rgba(255, 99, 132, 0.72); color: #ff6384;">
            <span class="stress-difficulty-check-emoji">😰</span>
            <span style="font-size: 18px; font-weight: 700;">Hard</span>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    
    const showSelectionResult = (choice) => {
      const selected = String(choice || "Medium").trim();
      const selectedLower = selected.toLowerCase();
      const easyPicked = selectedLower.includes("easy");
      const hardPicked = selectedLower.includes("hard");
      
      let emoji, headline;
      if (easyPicked) {
        emoji = "😏";
        headline = "Easy? We'll remember you said that.";
      } else if (hardPicked) {
        emoji = "😰";
        headline = "Hard? At least you're honest about your limits.";
      } else {
        emoji = "🤨";
        headline = "When people are unsure they chose medium.";
      }
      
      const card = overlay.querySelector('.stress-difficulty-check-card');
      if (!card) {
        continueSequence();
        return;
      }
      
      card.className = 'stress-difficulty-check-card stress-difficulty-check-result';
      card.innerHTML = `
        <div class="stress-difficulty-check-result-emoji" aria-hidden="true">${emoji}</div>
        <div class="stress-difficulty-check-result-title">${headline}</div>
        <div class="stress-difficulty-check-result-sub">Preparing the next one...</div>
      `;
      
      setTimeout(() => continueSequence(), 1400);
    };
    
    const continueSequence = () => {
      overlay.remove();
      
      timers.push(setTimeout(() => {
        const warningOverlay = document.createElement('div');
        warningOverlay.className = 'stress-difficulty-check-overlay';
        warningOverlay.innerHTML = `
          <div class="binary-card">
            <div class="stress-difficulty-check-emoji" style="font-size: 62px;">⚠️</div>
            <div class="binary-question">Hard Question Ahead</div>
          </div>
        `;
        document.body.appendChild(warningOverlay);
        
        timers.push(setTimeout(() => {
          warningOverlay.remove();
          
          stressCountdown = document.createElement('div');
          stressCountdown.className = 'trigger-countdown';
          document.body.appendChild(stressCountdown);
          
          let timeLeft = 30;
          stressCountdown.textContent = `⏱️ ${timeLeft}s`;
          
          countdownInterval = setInterval(() => {
            timeLeft--;
            if (timeLeft <= 0) {
              clearInterval(countdownInterval);
              if (typeof skipToNextQuestion === 'function') {
                skipToNextQuestion();
              }
              return;
            }
            stressCountdown.textContent = `⏱️ ${timeLeft}s`;
            if (timeLeft <= 10) {
              stressCountdown.classList.add('urgent');
            }
          }, 1000);
          
          timers.push(setTimeout(() => {
            fogElement = document.createElement('div');
            fogElement.className = 'trigger-fog-overlay';
            
            if (questionBody.parentElement) {
              questionBody.style.position = 'relative';
              questionBody.appendChild(fogElement);
            }
            
            timers.push(setTimeout(() => {
              if (fogElement) fogElement.remove();
            }, 45000));
            
          }, 3500));
          
        }, 6000));
        
      }, 2500));
    };
    
    overlay.querySelectorAll('.stress-difficulty-check-option').forEach(btn => {
      btn.addEventListener('click', () => {
        const rating = btn.textContent.trim().toLowerCase();
        showSelectionResult(rating);
      });
    });
    
    const interceptSubmission = (e) => {
      if (interceptionCount >= maxInterceptions) return;
      
      e.preventDefault();
      e.stopPropagation();
      interceptionCount++;
      
      const doubtMessages = [
        "73% of toppers picked option B. Are you sure?",
        "Most high scorers chose differently. Reconsider?",
        "Top students disagree with your choice. Final answer?"
      ];
      
      const doubtOverlay = document.createElement('div');
      doubtOverlay.className = 'stress-difficulty-check-overlay';
      doubtOverlay.innerHTML = `
        <div class="binary-card">
          <div class="stress-difficulty-check-emoji" style="font-size: 48px;">⚠️</div>
          <div class="binary-question">Peer Doubt Alert</div>
          <div class="stress-difficulty-check-sub">${doubtMessages[Math.min(interceptionCount - 1, doubtMessages.length - 1)]}</div>
          <button class="binary-btn" id="doubt-continue" style="width: 100%; background: rgba(26, 215, 181, 0.15); border-color: rgba(26, 215, 181, 0.5); color: #28d8af;">Continue Anyway</button>
        </div>
      `;
      document.body.appendChild(doubtOverlay);
      
      document.getElementById('doubt-continue').addEventListener('click', () => {
        doubtOverlay.remove();
      });
    };
    
    const submitBtn = document.querySelector('#submit-answer-btn');
    if (submitBtn) {
      submitBtn.addEventListener('click', interceptSubmission, true);
    }
    
    return {
      durationMs: 0,
      cleanup: () => {
        timers.forEach(t => clearTimeout(t));
        if (countdownInterval) clearInterval(countdownInterval);
        overlay.remove();
        if (fogElement) fogElement.remove();
        if (stressCountdown) stressCountdown.remove();
        if (submitBtn) {
          submitBtn.removeEventListener('click', interceptSubmission, true);
        }
      },
    };
  }

  // Q7 → BILLIARD_BALL
  function triggerBilliardBall() {
    if (!questionBody) return null;
    
    const timers = [];
    let rafId = null;
    
    const tauntOverlay = document.createElement('div');
    tauntOverlay.className = 'stress-difficulty-check-overlay';
    tauntOverlay.innerHTML = `
      <div class="binary-card">
        <div class="stress-difficulty-check-emoji" style="font-size: 48px;">⚠️</div>
        <div class="binary-question">This one breaks 80% of students. Watch. 😈</div>
      </div>
    `;
    document.body.appendChild(tauntOverlay);
    
    timers.push(setTimeout(() => {
      tauntOverlay.remove();
      
      timers.push(setTimeout(() => {
        const card = questionBody.parentElement;
        if (!card) return;
        
        const originalPosition = card.style.position;
        const originalWidth = card.style.width;
        const originalTransform = card.style.transform;
        const originalLeft = card.style.left;
        const originalTop = card.style.top;
        const originalZIndex = card.style.zIndex;
        
        // Set up for bouncing - 65% scale for better readability and clickability
        card.style.position = 'fixed';
        card.style.width = '600px';
        card.style.transform = 'scale(0.65)';
        card.style.transformOrigin = 'top left';
        card.style.zIndex = '9999';
        card.style.transition = 'none';
        
        // Physics variables - adjusted for 65% scale
        const cardWidth = 390; // 600 * 0.65
        const cardHeight = 325; // ~500 * 0.65
        let x = window.innerWidth / 2 - cardWidth / 2;
        let y = window.innerHeight / 2 - cardHeight / 2;
        let vx = 4 + Math.random() * 2;
        let vy = 3 + Math.random() * 2;
        
        const animate = () => {
          x += vx;
          y += vy;
          
          let bounced = false;
          
          if (x <= 0) {
            x = 0;
            vx = Math.abs(vx);
            bounced = true;
          } else if (x + cardWidth >= window.innerWidth) {
            x = window.innerWidth - cardWidth;
            vx = -Math.abs(vx);
            bounced = true;
          }
          
          if (y <= 0) {
            y = 0;
            vy = Math.abs(vy);
            bounced = true;
          } else if (y + cardHeight >= window.innerHeight) {
            y = window.innerHeight - cardHeight;
            vy = -Math.abs(vy);
            bounced = true;
          }
          
          if (bounced) {
            const callout = document.createElement('div');
            callout.className = 'trigger-focus-callout';
            callout.style.left = `${x + cardWidth / 2}px`;
            callout.style.top = `${y + cardHeight / 2}px`;
            callout.textContent = 'FOCUS!';
            document.body.appendChild(callout);
            
            if (navigator.vibrate) {
              navigator.vibrate(100);
            }
            
            setTimeout(() => callout.remove(), 500);
          }
          
          card.style.left = x + 'px';
          card.style.top = y + 'px';
          
          rafId = requestAnimationFrame(animate);
        };
        
        rafId = requestAnimationFrame(animate);
        
        const cleanup = () => {
          if (rafId) cancelAnimationFrame(rafId);
          card.style.position = originalPosition;
          card.style.width = originalWidth;
          card.style.transform = originalTransform;
          card.style.left = originalLeft;
          card.style.top = originalTop;
          card.style.zIndex = originalZIndex;
        };
        
        timers.push(cleanup);
        
      }, 800));
      
    }, 4000));
    
    return {
      durationMs: 0,
      cleanup: () => {
        timers.forEach(t => {
          if (typeof t === 'function') t();
          else clearTimeout(t);
        });
        if (tauntOverlay.parentElement) tauntOverlay.remove();
        if (rafId) cancelAnimationFrame(rafId);
      },
    };
  }

  // ========================================================================
  // End of Question-Level Triggers
  // ========================================================================

  const devNarrativeTriggerHandlers = {
    devMicroQuizPop: triggerDevMicroQuizPop,
    devFocusSpotlight: triggerDevFocusSpotlight,
    devCognitiveMelt: triggerDevCognitiveMelt,
    devMatrixGlitch: triggerDevMatrixGlitch,
    devSlideToLock: triggerDevSlideToLock,
    devBlindRecall: triggerDevBlindRecall,
    devConfidenceSlider: triggerDevConfidenceSlider,
  };

  function activateManualShowcaseTrigger(name, context) {
    if (!manualStressTriggerMode || !enableDevTriggerPanel) return false;
    if (active.has(name)) {
      deactivateTrigger(name);
      return false;
    }
    if (active.size >= 1) {
      showDevToast("Another trigger is active. Clear it first.");
      return false;
    }
    const handler = devNarrativeTriggerHandlers[name];
    if (!handler) return false;
    let out = null;
    try {
      out = handler(context || {});
    } catch (err) {
      debugLog("manual_showcase_error", `${name}:${err?.message || String(err)}`);
      return false;
    }
    if (!out) return false;
    const durationMs = Math.max(1800, Math.min(30000, Number(out.durationMs || 8000)));
    registerTrigger(name, out.cleanup, durationMs, {
      ...(context || {}),
      force: true,
      manual: true,
      intensity: "medium",
      reason: `dev_showcase:${name}`,
      userState: currentUserState(),
    });
    return true;
  }

  const triggerHandlers = {
    optionShuffle: triggerOptionShuffle,
    phantomCompetitor: triggerPhantomCompetitor,
    stressTimer: triggerStressTimer,
    confidenceBreaker: triggerConfidenceBreaker,
    focusHandSignal: triggerFocusHandSignal,
    focusReadGate: triggerFocusReadGate,
    premiumImagePopup: triggerPremiumImagePopup,
    optionFeedbackPopups: triggerOptionFeedbackPopups,
    mirageHighlight: triggerMirageHighlight,
    blurAttack: triggerBlurAttack,
    screenFlip: triggerScreenFlip,
    colorInversion: triggerColorInversion,
    heartbeatVibration: triggerHeartbeatVibration,
    waveDistortion: triggerWaveDistortion,
    fakeMentorCount: triggerFakeMentorCount,
    chaosBackground: triggerChaosBackground,
    shepardTone: triggerShepardTone,
    spatialTicking: triggerSpatialTicking,
    fakeLowBattery: triggerFakeLowBattery,
    fakeCrashScreen: triggerFakeCrashScreen,
    blackout: triggerBlackout,
    hesitationHeatmap: triggerHesitationHeatmap,
    torchlightSpotlight: triggerTorchlightSpotlight,
    difficultyCheckPrompt: triggerDifficultyCheckPrompt,
    boucingQuestion: triggerBouncingQuestion,
    // Question-level triggers for Focus Zones test
    hardFog: triggerHardFog,
    accuracyTest: triggerAccuracyTest,
    readingTest: triggerReadingTest,
    hardPeerDoubt: triggerHardPeerDoubt,
    billiardBall: triggerBilliardBall,
  };

  function activateTrigger(name, context) {
    console.log('[activateTrigger] Attempting to activate:', name);
    const check = canActivateTrigger(name, context);
    if (!check.ok) {
      console.log('[activateTrigger] Cannot activate:', name, 'reason:', check.reason);
      debugLog("rejected", `${name}:${check.reason}`);
      return false;
    }
    const handler = triggerHandlers[name];
    if (!handler) {
      console.log('[activateTrigger] No handler found for:', name);
      return false;
    }
    console.log('[activateTrigger] Handler found, calling it for:', name);
    let out = null;
    try {
      out = handler(context);
      console.log('[activateTrigger] Handler returned:', out);
    } catch (err) {
      console.error('[activateTrigger] Handler error for', name, ':', err);
      debugLog("handler_error", `${name}:${err?.message || String(err)}`);
      return false;
    }
    if (!out) {
      console.log('[activateTrigger] Handler returned null/falsy for:', name);
      debugLog("rejected", `${name}:no-effect`);
      return false;
    }
    const requestedDuration = Number(context?.timeoutMs || 0);
    const handlerDuration = Number(out.durationMs || 0);
    let durationMs = requestedDuration > 0 ? requestedDuration : handlerDuration;
    if (durationMs > 0) {
      durationMs = Math.max(2000, Math.min(20000, durationMs)); // Max 20 seconds instead of 12
    }
    console.log('[activateTrigger] Registering trigger:', name, 'duration:', durationMs);
    registerTrigger(name, out.cleanup, durationMs, context);
    return true;
  }

  function queueTriggerRequest(eventType, extra, delayMs) {
    if (isInterruptionActive()) return;
    state.queuedTriggerRequest = {
      eventType,
      extra: extra || {},
      at: Date.now(),
    };
    if (state.aiDebounceTimer) return;
    const waitMs = Math.max(AI_DECISION_DEBOUNCE_MS, Math.floor(Number(delayMs || 0)));
    state.aiDebounceTimer = setTimeout(() => {
      state.aiDebounceTimer = null;
      if (!state.queuedTriggerRequest) return;
      if (state.stage !== "popups") {
        state.queuedTriggerRequest = null;
        return;
      }
      if (active.size >= 1) return;
      const queued = state.queuedTriggerRequest;
      state.queuedTriggerRequest = null;
      requestTriggerFromAI(queued.eventType, queued.extra);
    }, waitMs);
  }

  function pickLocalFallbackTrigger(eventType, userState, available, decision) {
    if (!Array.isArray(available) || !available.length) return "";
    const recent = new Set((state.recentTriggerNames || []).slice(-4));
    const scored = evaluateUserState(userState).map((item) => item.name);
    const suggested = String(decision?.suggested_trigger || "").trim();

    const ordered = [];
    const seen = new Set();
    const pushName = (name) => {
      if (!name || seen.has(name)) return;
      seen.add(name);
      ordered.push(name);
    };

    if (suggested && available.includes(suggested)) pushName(suggested);
    scored.forEach((name) => {
      if (available.includes(name)) pushName(name);
    });
    available.forEach(pushName);

    for (const name of ordered) {
      if (recent.has(name)) continue;
      if (canActivateTrigger(name, { userState }).ok) return name;
    }
    for (const name of ordered) {
      if (canActivateTrigger(name, { userState }).ok) return name;
    }
    return "";
  }

  async function requestTriggerFromAI(eventType, extra) {
    if (disableStressMode) return false;
    if (state.stage !== "popups") return false;
    
    // Disable AI trigger system for questions with custom trigger sequences (Q1-Q7 in Focus Zones test)
    const questionNumber = testQuestionIndex + 1;
    const triggerInfo = getQuestionTrigger(questionNumber);
    if (triggerInfo && triggerInfo.name) {
      console.log('[requestTriggerFromAI] Skipping AI triggers - question has custom trigger sequence:', triggerInfo.name);
      return false;
    }
    
    if (isInterruptionActive()) return false;
    if (isInQuietBreak()) return false;
    if (!testQuestions.length) return false;
    if (active.size >= 1) {
      queueTriggerRequest(eventType, extra, AI_DECISION_DEBOUNCE_MS);
      return false;
    }

    const now = Date.now();
    if (state.aiDecisionInFlight) {
      queueTriggerRequest(eventType, extra, AI_DECISION_DEBOUNCE_MS);
      return false;
    }
    if (now < Number(state.aiBackoffUntil || 0)) {
      queueTriggerRequest(eventType, extra, Number(state.aiBackoffUntil || 0) - now + AI_DECISION_DEBOUNCE_MS);
      return false;
    }
    if (now - state.lastAIDecisionAt < AI_DECISION_MIN_GAP_MS) {
      queueTriggerRequest(eventType, extra, AI_DECISION_MIN_GAP_MS - (now - state.lastAIDecisionAt));
      return false;
    }

    const userState = currentUserState();
    const available = getTriggerNames().filter((name) => canActivateTrigger(name, { userState }).ok);

    if (!available.length) return false;

    state.aiDecisionInFlight = true;
    state.lastAIDecisionAt = now;
    try {
      const elapsedSeconds = getElapsedSeconds();
      const remainingMs = timeRemainingMs();
      const testPhase = getTestPhase();
      const recentAccuracy = getRecentAccuracy();
      const interactionHesitationMs = Math.max(
        Number(state.interactionHesitationMs || 0),
        Number(userState.timeOnQuestionMs || 0) > 8000 ? Number(userState.timeOnQuestionMs || 0) : 0
      );

      const payload = {
        event_name: eventType,
        event_type: eventType,
        context: {
          platform: getPlatform(),
          elapsed_seconds: elapsedSeconds,
          time_remaining_seconds: Math.max(0, Math.floor(remainingMs / 1000)),
          test_phase: testPhase,
          current_stress_budget: state.stressBudget,
        },
        telemetry: {
          response_time_ms: Number.isFinite(userState.answerLatencyMs)
            ? Math.max(0, Math.floor(userState.answerLatencyMs))
            : 0,
          interaction_hesitation_ms: Math.max(0, Math.floor(interactionHesitationMs)),
          recent_accuracy: recentAccuracy,
          avg_touch_pressure: getAvgTouchPressure(),
          tap_velocity: Math.max(0, Math.min(1, userState.clickFrequency / 10)),
          device_movement_index: Math.max(0, Math.min(10, Number(state.deviceMovementIndex || 0))),
          app_focus_loss_count: state.lastContextSwitchAt ? 1 : 0,
          current_stress_budget: state.stressBudget,
        },
        user_state: {
          time_on_question_ms: Math.floor(userState.timeOnQuestionMs || 0),
          idle_ms: Math.floor(userState.idleMs || 0),
          answer_change_count: Number(userState.answerChangeCount || 0),
          answer_latency_ms: Number.isFinite(userState.answerLatencyMs) ? Math.floor(userState.answerLatencyMs) : null,
          time_remaining_ms: Math.floor(userState.timeRemainingMs || 0),
          hover_intent_on_option: Boolean(userState.hoverIntentOnOption),
          is_submitting_answer: Boolean(userState.isSubmittingAnswer),
          question_difficulty: String(userState.questionDifficulty || ""),
          feedback_difficulty_preference: String(state.feedbackDifficultyPreference || "medium"),
          feedback_topic_preference: String(state.feedbackTopicPreference || ""),
        },
        metrics: {
          wrong_answers_count: state.wrongAnswersCount,
          total_submissions: state.totalSubmissions,
          correct_streak: state.correctStreak,
          recent_accuracy: recentAccuracy,
        },
        available_triggers: available,
        recent_triggers: state.recentTriggerOutcomes.slice(-8),
        followup_answers: state.followupAnswers.slice(-8),
        student_preferences: {
          preferred_interest_topic: String(state.feedbackTopicPreference || ""),
          preferred_trigger_difficulty: String(state.feedbackDifficultyPreference || "medium"),
          feedback_last_question_type: String(state.lastFeedbackQuestionType || ""),
          feedback_recent: state.feedbackResponseHistory.slice(-6),
        },
        extra: {
          ...(extra || {}),
          session_id: sessionId || null,
        },
      };

      const timeoutMsForDecision = eventType === "enter_popups" ? AI_DECISION_TIMEOUT_FAST_MS : AI_DECISION_TIMEOUT_MS;
      const decision = await postJSON(AI_TRIGGER_ENDPOINT, payload, { timeoutMs: timeoutMsForDecision });
      const forceTrigger = String(extra?.force_trigger || "").trim();
      const triggerName = String(decision?.trigger_name || "").trim();
      const timeoutMs = Number(decision?.timeout_ms || 0);
      const aiIntensity = String(decision?.intensity || "low").toLowerCase();
      const tunedAIIntensity = applyFeedbackIntensityBias(aiIntensity);
      if (Number.isFinite(Number(decision?.budget_after))) {
        state.stressBudget = clampBudget(Number(decision?.budget_after));
      }

      let activated = false;
      if (forceTrigger && available.includes(forceTrigger)) {
        activated = activateTrigger(forceTrigger, {
          userState,
          timeoutMs,
          force: false,
          reason: `forced_by_feedback:${eventType}:${forceTrigger}`,
          intensity: tunedAIIntensity,
        });
      }

      if (!activated && triggerName && available.includes(triggerName)) {
        activated = activateTrigger(triggerName, {
          userState,
          timeoutMs,
          force: false,
          reason: `ai:${eventType}:${triggerName}`,
          intensity: tunedAIIntensity,
        });
      }

      if (!activated) {
        const fallbackName = pickLocalFallbackTrigger(eventType, userState, available, decision);
        if (fallbackName) {
          activated = activateTrigger(fallbackName, {
            userState,
            force: false,
            reason: `local_fallback:${eventType}:${fallbackName}`,
            intensity: applyFeedbackIntensityBias("medium"),
          });
        }
      }

      if (!activated) {
        state.noActionStreak = Number(state.noActionStreak || 0) + 1;
        if (state.noActionStreak >= 2) {
          const forced = available.find((name) => canActivateTrigger(name, { userState }).ok);
          if (forced) {
            activated = activateTrigger(forced, {
              userState,
              force: false,
              reason: `forced_recovery:${eventType}:${forced}`,
              intensity: applyFeedbackIntensityBias("low"),
            });
          }
        }
      }

      if (activated) {
        state.noActionStreak = 0;
        return true;
      }
    } catch (err) {
      state.aiBackoffUntil = Date.now() + AI_DECISION_ERROR_BACKOFF_MS;
      debugLog("ai_trigger_error", err?.message || String(err));
    } finally {
      state.aiDecisionInFlight = false;
    }

    return false;
  }

  function evaluateUserState(userState) {
    const actions = [];
    if (userState.idleMs > 8000) {
      actions.push({ name: "blurAttack", score: 90 });
      actions.push({ name: "colorInversion", score: 94 });
      actions.push({ name: "chaosBackground", score: 91 });
      actions.push({ name: "fakeMentorCount", score: 88 });
    }
    if (userState.answerChangeCount >= 3) {
      actions.push({ name: "optionShuffle", score: 86 });
      actions.push({ name: "screenFlip", score: 90 });
      actions.push({ name: "hesitationHeatmap", score: 92 });
      actions.push({ name: "waveDistortion", score: 89 });
    }
    if (userState.answerLatencyMs < 3000) {
      actions.push({ name: "confidenceBreaker", score: 84 });
      actions.push({ name: "screenFlip", score: 87 });
      actions.push({ name: "fakeCrashScreen", score: 90 });
    }
    if (userState.timeOnQuestionMs > 10000) {
      actions.push({ name: "phantomCompetitor", score: 82 });
      actions.push({ name: "colorInversion", score: 86 });
      actions.push({ name: "spatialTicking", score: 88 });
    }
    if (userState.timeRemainingMs < 300000) {
      actions.push({ name: "heartbeatVibration", score: 92 });
      actions.push({ name: "stressTimer", score: 89 });
      actions.push({ name: "shepardTone", score: 91 });
      actions.push({ name: "fakeLowBattery", score: 90 });
      actions.push({ name: "blackout", score: 93 });
    }
    if (userState.hoverIntentOnOption) {
      actions.push({ name: "mirageHighlight", score: 85 });
    }

    const dedupe = new Map();
    actions.forEach((item) => {
      const existing = dedupe.get(item.name);
      if (!existing || item.score > existing.score) {
        dedupe.set(item.name, item);
      }
    });

    return [...dedupe.values()].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  }

  function getTriggerNames() {
    return Object.keys(triggerHandlers).filter(isTriggerEnabled);
  }

  function onQuestionRendered(question) {
    const clearQuestionWarningOverlay = () => {
      document.querySelectorAll(".psyq-overlay[data-question-warning='1'], .psyq-overlay[data-warning-only='1']").forEach((el) => el.remove());
    };
    if (state.optionFeedbackActive && state.optionFeedbackQuestionId &&
        String(state.optionFeedbackQuestionId) !== String(question?.question_id || "")) {
      closeOptionFeedbackPopup();
    }
    
    // Clean up any active triggers from previous question
    deactivateAllTriggers();
    
    state.currentQuestionId = question?.question_id || "";
    state.questionDifficulty = String(question?.difficulty || "");
    state.questionStartedAt = Date.now();
    state.lastAnswerLatencyMs = null;
    state.hoverIntentOnOption = false;
    state.hoverOptionEl = null;
    state.interactionHesitationMs = 0;
    state.interactionHesitationStartedAt = 0;
    state.optionFeedbackInterceptionEnabled = false;
    state.optionFeedbackInterceptionCount = 0;
    state.optionFeedbackMaxInterceptions = 0;
    
    // Check if this is a hard question
    const isHard = isHardDifficulty(question?.difficulty);
    const questionNumber = testQuestionIndex + 1;
    clearQuestionWarningOverlay();
    
    console.log('[onQuestionRendered] Current testQuestionIndex:', testQuestionIndex);
    console.log('[onQuestionRendered] Calculated questionNumber:', questionNumber);
    console.log('[onQuestionRendered] Question ID:', question?.question_id);
    console.log('[onQuestionRendered] Question difficulty:', question?.difficulty);

    if (questionNumber >= 1 && questionNumber <= 7) {
      const renderedQuestionId = String(question?.question_id || "");
      void fetchQuestionWarningCopy(questionNumber);
      const timeoutId = setTimeout(() => {
        if (String(state.currentQuestionId || "") !== renderedQuestionId) return;
        console.log(`[onQuestionRendered] Showing popup-card sequence for Q${questionNumber}`);
        showQuestionWarningPopup(questionNumber, () => {
          console.log(`[onQuestionRendered] Warning popup dismissed for Q${questionNumber}`);
        });
      }, 5000);
      pendingTriggerTimeouts.push(timeoutId);
      return;
    }
    
    // Fixed per-question flows (new-user sequence every session)
    ensureQuestionTriggerPlan();
    const triggerInfo = getQuestionTrigger(questionNumber);
    const hasCustomTriggerSequence = triggerInfo && triggerInfo.name;
    
    if (testQuestions.length >= 1 && questionNumber >= 1 && questionNumber <= 7) {
      console.log('[onQuestionRendered] Activating custom trigger sequence for question:', questionNumber);
      
      if (questionNumber >= 1 && questionNumber <= 7) {
        let delayMs = 5000;
        
        // Q1 → short aggressive warning card; user must dismiss
        if (questionNumber === 1) {
          scheduleQ1SessionPopup();
        }
        
        // Q2 → short popup, then torch beam (not hard-fog)
        else if (questionNumber === 2) {
          runQ2PopupFlow(2);
        }
        
        // Q3 → screen flip only
        else if (questionNumber === 3) {
          delayMs = 5000;
          const timeoutId = setTimeout(() => {
            if (testQuestionIndex + 1 !== 3) return;
            activateTrigger("screenFlip", {
              userState: currentUserState(),
              force: true,
              reason: "question_trigger:Q3:screenFlip",
              questionNumber: 3,
            });
          }, delayMs);
          pendingTriggerTimeouts.push(timeoutId);
        }
        
        // Q4 → ACCURACY_TEST
        else if (questionNumber === 4) {
          delayMs = 1000;
          const timeoutId = setTimeout(() => {
            console.log(`[onQuestionRendered] Activating Q4 trigger: accuracyTest`);
            activateTrigger('accuracyTest', {
              userState: currentUserState(),
              force: true,
              reason: `question_trigger:Q${questionNumber}:accuracyTest`,
              questionNumber: questionNumber
            });
          }, delayMs);
          pendingTriggerTimeouts.push(timeoutId);
        }
        
        // Q5 → READING_TEST
        else if (questionNumber === 5) {
          delayMs = 3000;
          const timeoutId1 = setTimeout(() => {
            console.log(`[onQuestionRendered] Starting Q5 sequence: focusHandSignal`);
            
            // Step 1: Pointing finger popup for 4 seconds
            const handSignalActivated = activateTrigger('focusHandSignal', {
              userState: currentUserState(),
              force: true,
              reason: `question_trigger:Q${questionNumber}:focusHandSignal`,
              timeoutMs: 4000,
              questionNumber: questionNumber
            });
            
            if (handSignalActivated) {
              console.log(`[onQuestionRendered] Hand signal activated, scheduling 8s clear reading time`);
              
              // Step 2: Wait for hand signal to complete (4s) + 8s clear reading time = 12s total
              const timeoutId2 = setTimeout(() => {
                console.log(`[onQuestionRendered] Clear reading time complete, activating focusReadGate`);
                
                // Step 3: Blur and lock with unlock button
                activateTrigger('focusReadGate', {
                  userState: currentUserState(),
                  force: true,
                  reason: `question_trigger:Q${questionNumber}:focusReadGate`,
                  questionNumber: questionNumber,
                  roastDuration: 4500, // 4.5 second roast
                  noAutoTimeout: true // Stays blurred until user interacts
                });
              }, 12000); // 4s hand signal + 8s clear reading
              pendingTriggerTimeouts.push(timeoutId2);
            } else {
              console.error(
                `[onQuestionRendered] Failed to activate focusHandSignal; falling back to readingTest handler`,
              );
              const timeoutIdFb = setTimeout(() => {
                if (testQuestionIndex + 1 !== questionNumber) return;
                activateTrigger("readingTest", {
                  userState: currentUserState(),
                  force: true,
                  reason: `question_trigger:Q${questionNumber}:readingTest_fallback`,
                  questionNumber: questionNumber,
                });
              }, 600);
              pendingTriggerTimeouts.push(timeoutIdFb);
            }
          }, delayMs);
          pendingTriggerTimeouts.push(timeoutId1);
        }
        
        // Q6 → HARD_PEER_DOUBT
        else if (questionNumber === 6) {
          // Hide question immediately for Q6
          if (questionStem) questionStem.style.visibility = 'hidden';
          if (questionOptions) questionOptions.style.visibility = 'hidden';
          
          delayMs = 0; // Show difficulty check instantly
          setTimeout(() => {
            console.log(`[onQuestionRendered] Starting Q6 pre-sequence: difficultyCheckPrompt`);
            
            // Enable option feedback interception for this question
            state.optionFeedbackInterceptionEnabled = true;
            state.optionFeedbackInterceptionCount = 0;
            state.optionFeedbackMaxInterceptions = 2;
            
            // Force close any existing feedback prompt
            if (state.feedbackPromptOpen) {
              console.log(`[onQuestionRendered] Forcing feedbackPromptOpen to false for Q6`);
              state.feedbackPromptOpen = false;
              releaseInterruptionLock("feedback");
            }
            
            // Step 1: Difficulty rating popup (difficultyCheckPrompt trigger)
            const difficultyCheckResult = activateTrigger('difficultyCheckPrompt', {
              userState: currentUserState(),
              force: true,
              reason: `question_trigger:Q${questionNumber}:pre_sequence`,
              questionNumber: questionNumber
            });
            
            if (!difficultyCheckResult) {
              console.error(`[onQuestionRendered] Failed to activate difficultyCheckPrompt for Q6! Skipping to hardQuestion.`);
              setTimeout(() => {
                const q = testQuestions[testQuestionIndex];
                if (q) {
                  const hardQuestion = { ...q, difficulty: "hard" };
                  activateHardQuestionChallenge(hardQuestion);
                }
              }, 2500);
              return;
            }
            
            // Wait for difficulty check to complete, then continue sequence
            const waitForDifficultyCheck = setInterval(() => {
              if (!isTriggerActive('difficultyCheckPrompt')) {
                clearInterval(waitForDifficultyCheck);
                
                console.log(`[onQuestionRendered] Difficulty check complete, waiting 2.5s`);
                
                // Step 2: 2.5s pause, then activate hardQuestion
                setTimeout(() => {
                  console.log(`[onQuestionRendered] Activating hardQuestion challenge for Q6`);
                  
                  // Step 3: Activate hardQuestion challenge
                  const q = testQuestions[testQuestionIndex];
                  if (q) {
                    const hardQuestion = { ...q, difficulty: "hard" };
                    activateHardQuestionChallenge(hardQuestion);
                  }
                  
                }, 2500);
              }
            }, 100);
            
          }, delayMs);
        }
        
        // Q7 → BILLIARD_BALL
        else if (questionNumber === 7) {
          delayMs = 1500;
          const timeoutId1 = setTimeout(() => {
            console.log(`[onQuestionRendered] Starting Q7 sequence: premiumImagePopup taunt`);
            
            // Step 1: Pre-roast taunt for 4 seconds
            const tauntActivated = activateTrigger('premiumImagePopup', {
              userState: currentUserState(),
              force: true,
              reason: `question_trigger:Q${questionNumber}:pre_taunt`,
              timeoutMs: 4000,
              questionNumber: questionNumber,
              customMessage: "Final question. Let's see if you can focus now."
            });
            
            if (tauntActivated) {
              console.log(`[onQuestionRendered] Taunt activated, scheduling bouncing question`);
              
              // Step 2: Wait for taunt (4s) + gap (0.8s) = 4.8s total
              const timeoutId2 = setTimeout(() => {
                console.log(`[onQuestionRendered] Activating bouncingQuestion`);
                
                // Step 3: Bouncing question (indefinite)
                activateTrigger('boucingQuestion', {
                  userState: currentUserState(),
                  force: true,
                  reason: `question_trigger:Q${questionNumber}:bouncingQuestion`,
                  questionNumber: questionNumber,
                  shrinkTo: 0.5, // 50% size
                  showFocusCallout: true, // "FOCUS!" on each bounce
                  enableVibration: true, // Vibrate on bounce
                  indefinite: true // Runs until submission
                });
              }, 4800); // 4s taunt + 0.8s gap
              pendingTriggerTimeouts.push(timeoutId2);
            } else {
              console.error(`[onQuestionRendered] Failed to activate premiumImagePopup taunt`);
            }
          }, delayMs);
          pendingTriggerTimeouts.push(timeoutId1);
        }

        // Returning-user plans can assign any medium/hard trigger to Q2–Q7. If the backend
        // maps e.g. SCREEN_FLIP to Q5, none of the dedicated branches above run; without
        // this we returned early and fired nothing (and AI triggers stay disabled).
        else if (triggerHandlers[triggerInfo.name]) {
          const name = triggerInfo.name;
          const fallbackDelay =
            name === "screenFlip"
              ? 5000
              : name === "torchlightSpotlight"
                ? 6000
                : name === "accuracyTest"
                  ? 1000
                  : name === "readingTest"
                    ? 3000
                    : name === "billiardBall"
                      ? 1500
                      : 2500;
          const timeoutId = setTimeout(() => {
            if (String(state.currentQuestionId) !== String(question?.question_id || "")) return;
            activateTrigger(name, {
              userState: currentUserState(),
              force: true,
              reason: `question_trigger:Q${questionNumber}:planned_generic`,
              questionNumber: questionNumber,
            });
          }, fallbackDelay);
          pendingTriggerTimeouts.push(timeoutId);
          console.warn(
            `[onQuestionRendered] No dedicated sequence for Q${questionNumber} trigger "${name}"; using generic activation after ${fallbackDelay}ms`,
          );
        } else {
          console.warn(
            `[onQuestionRendered] Planned trigger "${triggerInfo.name}" for Q${questionNumber} has no local handler`,
          );
        }
        
        console.log(`[onQuestionRendered] Trigger sequence initiated for Q${questionNumber}:`, triggerInfo.name);
        
        // Don't call requestTriggerFromAI - we already have a planned trigger
        return;
      }
    } else if (!hasCustomTriggerSequence) {
      console.log('[onQuestionRendered] Hard question detected - using hardQuestionChallenge only');
    }
    
    // Ensure Q1 personalized popup appears every session even without trigger plan.
    // Also suppress AI auto-triggers on Q1 so only this emotional popup is shown.
    if (scheduleQ1SessionPopup()) {
      return;
    }

    // Only call AI trigger system if no question-level trigger was activated
    // Skip AI triggers for questions with custom trigger sequences
    if (!triggerInfo || !triggerInfo.name) {
      requestTriggerFromAI("question_loaded", {
        question_id: state.currentQuestionId,
        difficulty: state.questionDifficulty,
      });
    }
    
    setTimeout(() => {
      showFeedbackPulse("question_rendered");
    }, 1200);
    
    // DISABLED: Automatic hard question activation - only use custom trigger sequences
    // All trigger activation is now handled by the custom sequence logic above
    console.log('[onQuestionRendered] Automatic trigger activation disabled - using custom sequences only');
    
    // Clean up any existing hard question challenge if it's for a different question
    if (
      state.hardQuestionChallenge &&
      state.hardQuestionChallenge.questionId !== String(question?.question_id || "")
    ) {
      clearHardQuestionChallenge();
    }
  }

  function onOptionChange(questionId, prevValue, nextValue) {
    if (!questionId) return;
    if (prevValue && nextValue && prevValue !== nextValue) {
      state.answerChangesByQuestion[questionId] = Number(state.answerChangesByQuestion[questionId] || 0) + 1;
    }
    if (state.lastAnswerLatencyMs == null && state.questionStartedAt) {
      state.lastAnswerLatencyMs = Date.now() - state.questionStartedAt;
    }
    markInteraction("click");
    requestTriggerFromAI("answer_changed", {
      question_id: questionId,
      previous_value: prevValue || "",
      next_value: nextValue || "",
    });
    maybeShowOptionFeedbackPopup(questionId, nextValue);
  }

  function onOptionClick(questionId, value) {
    maybeShowOptionFeedbackPopup(questionId, value);
  }

  function onOptionHover(optionEl) {
    state.hoverIntentOnOption = true;
    state.hoverOptionEl = optionEl || null;
    state.interactionHesitationStartedAt = state.interactionHesitationStartedAt || Date.now();
    markInteraction("pointer");
    if (state.questionStartedAt && Date.now() - state.questionStartedAt > 7000) {
      state.interactionHesitationMs = Date.now() - state.questionStartedAt;
      requestTriggerFromAI("interaction_hesitation", {
        question_id: state.currentQuestionId,
        interaction_hesitation_ms: state.interactionHesitationMs,
      });
    }
  }

  function onOptionPointerDown(optionEl, evt) {
    state.hoverOptionEl = optionEl || null;
    state.interactionHesitationStartedAt = Date.now();
    markInteraction("pointerdown", evt);
  }

  function onOptionPointerUp() {
    if (!state.interactionHesitationStartedAt) return;
    const hesitationMs = Date.now() - state.interactionHesitationStartedAt;
    state.interactionHesitationStartedAt = 0;
    if (hesitationMs < 650) return;
    state.interactionHesitationMs = hesitationMs;
    requestTriggerFromAI("interaction_hesitation", {
      question_id: state.currentQuestionId,
      interaction_hesitation_ms: hesitationMs,
    });
  }

  function beginExamTimer() {
    if (!state.examStartedAt) {
      state.examStartedAt = Date.now();
      console.log('[beginExamTimer] Exam started at:', state.examStartedAt, 'Date:', new Date(state.examStartedAt).toISOString());
      state.stressBudget = STRESS_BUDGET_MAX;
      
      // Increment total_sessions when test actually starts
      const user = window.StressDostAuth?.getUser();
      if (user && user.user_id) {
        console.log('[beginExamTimer] Incrementing session count for user:', user.user_id);
        fetch(`/api/user/${user.user_id}/session-start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
        .then(res => res.json())
        .then(data => {
          console.log('[beginExamTimer] Session started:', data);
          // Update local storage with new session count
          if (user) {
            user.total_sessions = data.total_sessions;
            window.StressDostAuth.setUser(user);
          }
        })
        .catch(err => {
          console.error('[beginExamTimer] Failed to increment session:', err);
        });
      }
    } else {
      console.log('[beginExamTimer] Exam already started at:', state.examStartedAt, 'Date:', new Date(state.examStartedAt).toISOString());
    }
    startExamClock();
  }
  
  function stopExamTimer() {
    if (state.examTimerId) {
      clearInterval(state.examTimerId);
      state.examTimerId = null;
      console.log('[stopExamTimer] Exam timer stopped');
    }
  }

  function startExamClock() {
    if (state.examTimerId) {
      console.log('[startExamClock] Timer already running with ID:', state.examTimerId);
      return;
    }
    
    console.log('[startExamClock] Starting new timer interval');
    let tickCount = 0;
    state.examTimerId = setInterval(() => {
      tickCount++;
      console.log('[startExamClock] Tick #' + tickCount);
      
      const el = document.getElementById("questionTimer");
      if (!el) {
        console.warn('[startExamClock] Timer element not found!');
        return;
      }
      
      // If exam hasn't started yet, show initial time
      if (!state.examStartedAt || state.examStartedAt <= 0) {
        el.textContent = "15:00";
        return;
      }
      
      // If hard question is active, show its countdown instead
      if (state.hardQuestionChallenge && state.hardQuestionChallenge.deadlineAt) {
        const remainingMs = Math.max(0, state.hardQuestionChallenge.deadlineAt - Date.now());
        const totalSeconds = Math.ceil(remainingMs / 1000);
        el.textContent = `00:${String(Math.max(0, totalSeconds)).padStart(2, "0")}`;
        return;
      }
      
      // Normal exam timer - countdown from 15:00
      const now = Date.now();
      const elapsed = now - state.examStartedAt;
      const remainingMs = state.examDurationMs - elapsed;
      
      // Debug logging (remove after fixing)
      if (remainingMs > state.examDurationMs || remainingMs < -60000) {
        console.log('[startExamClock] DEBUG:', {
          now,
          examStartedAt: state.examStartedAt,
          elapsed,
          examDurationMs: state.examDurationMs,
          remainingMs,
          elapsedMinutes: (elapsed / 60000).toFixed(2),
          remainingMinutes: (remainingMs / 60000).toFixed(2)
        });
      }
      
      // Cap remaining time to valid range
      const cappedRemainingMs = Math.max(0, Math.min(remainingMs, state.examDurationMs));
      
      const totalSeconds = Math.max(0, Math.ceil(cappedRemainingMs / 1000));
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      el.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
      
      // Check if time is up
      if (cappedRemainingMs <= 0) {
        console.log('[startExamClock] Time is up! Showing end screen');
        clearInterval(state.examTimerId);
        state.examTimerId = null;
        
        // Capture the time used (should be full exam duration)
        const timeUsedAtEnd = StressTriggers.timeUsedMs();
        
        // Cancel all pending triggers
        cancelPendingTriggers();
        
        // Deactivate all active triggers
        if (typeof StressTriggers !== 'undefined' && StressTriggers.deactivateAllTriggers) {
          StressTriggers.deactivateAllTriggers();
        }
        
        // Show test end screen
        setTimeout(() => {
          showTestEndScreen(timeUsedAtEnd);
        }, 500);
      }
    }, 1000);
  }

  function onPopupsEntered() {
    // Reset gate timers so the very first trigger is attempted immediately.
    state.lastAIDecisionAt = 0;
    if (!testQuestions.length) return;

    requestTriggerFromAI("enter_popups", {
      question_id: state.currentQuestionId,
      difficulty: state.questionDifficulty,
      immediate: true,
    });
  }

  function getFollowupAnswers() {
    return (state.followupAnswers || []).map((item) => ({ ...item }));
  }

  async function beforeSubmitDelay() {
    state.isSubmittingAnswer = true;
    requestTriggerFromAI("submit_attempt", {
      question_id: state.currentQuestionId,
    });
    const remaining = timeRemainingMs();
    if (remaining < 5 * 60 * 1000) {
      requestTriggerFromAI("time_pressure", { time_remaining_ms: remaining });
    }
  }

  function afterSubmit() {
    state.isSubmittingAnswer = false;
  }

  function noteAnswerOutcome(correct, hasAnswerKey) {
    state.totalSubmissions += 1;
    if (hasAnswerKey) {
      state.lastAnswerWasCorrect = Boolean(correct);
    }
    if (!hasAnswerKey) return;
    const hardActive = Boolean(
      state.hardQuestionChallenge &&
      state.hardQuestionChallenge.questionId === String(state.currentQuestionId || "")
    );
    if (hardActive) {
      state.hardQuestionChallenge.resolved = true;
      if (correct) {
        clearHardQuestionChallenge();
      } else {
        // Wrong answer - show fail-wrong screen with shaky skull
        state.hardQuestionPostSubmitDelayMs = 3200;
        const failOverlay = showHardQuestionFullScreen("fail-wrong");
        state.hardQuestionChallenge.failOverlay = failOverlay;
        setTimeout(() => {
          failOverlay.remove();
          clearHardQuestionChallenge();
        }, 3200);
      }
    }
    if (correct) {
      state.correctStreak += 1;
      addBudget(3);
      setTimeout(() => showFeedbackPulse("post_correct_answer"), 900);
      return;
    }
    state.correctStreak = 0;
    state.wrongAnswersCount += 1;
    const confidenceNow = estimateConfidence(currentUserState());
    if (confidenceNow < 0.4) {
      addBudget(-5);
    }
    requestTriggerFromAI("wrong_answer", {
      wrong_answers_count: state.wrongAnswersCount,
      question_id: state.currentQuestionId,
    });
    setTimeout(() => showFeedbackPulse("post_wrong_answer"), 900);
  }

  function consumePostSubmitDelayMs() {
    const value = Number(state.hardQuestionPostSubmitDelayMs || 0);
    state.hardQuestionPostSubmitDelayMs = 0;
    return Math.max(0, value);
  }

  function onReset() {
    // Clear the exam timer
    if (state.examTimerId) {
      clearInterval(state.examTimerId);
      state.examTimerId = null;
      console.log('[onReset] Cleared exam timer');
    }
    
    state.examStartedAt = 0;
    state.questionStartedAt = 0;
    state.currentQuestionId = "";
    state.answerChangesByQuestion = {};
    state.followupAnswers = [];
    state.wrongAnswersCount = 0;
    state.totalSubmissions = 0;
    state.q1PopupShownThisSession = false;
    state.correctStreak = 0;
    state.aiDecisionInFlight = false;
    state.lastAIDecisionAt = 0;
    state.aiBackoffUntil = 0;
    state.recentTriggerNames = [];
    state.recentTriggerOutcomes = [];
    state.queuedTriggerRequest = null;
    if (state.aiDebounceTimer) {
      clearTimeout(state.aiDebounceTimer);
      state.aiDebounceTimer = null;
    }
    state.noActionStreak = 0;
    state.lastAnswerLatencyMs = null;
    state.lastAnswerWasCorrect = null;
    state.isSubmittingAnswer = false;
    state.stressBudget = STRESS_BUDGET_MAX;
    state.interactionHesitationMs = 0;
    state.interactionHesitationStartedAt = 0;
    state.pointerPressureSamples = [];
    state.deviceMovementIndex = 0;
    state.lastAgitationEventAt = 0;
    state.lastContextSwitchAt = 0;
    state.lastRapidTapEventAt = 0;
    state.interruptionLocks = {};
    state.feedbackLastShownAt = 0;
    state.feedbackPromptOpen = false;
    state.feedbackResponseHistory = [];
    state.feedbackDifficultyPreference = "medium";
    state.feedbackTopicPreference = "";
    state.lastFeedbackQuestionType = "";
    clearInterestReelSchedule();
    state.screenQuietUntil = 0;
    state.newsReelHistory = [];
    state.lastNewsTopic = "";
    state.lastNewsImage = "";
    clearHardQuestionChallenge();
    state.hardQuestionPostSubmitDelayMs = 0;
    state.optionFeedbackActive = false;
    state.optionFeedbackQuestionId = "";
    state.optionFeedbackLastOption = "";
    // Reset Q6 option feedback interception state
    state.optionFeedbackInterceptionEnabled = false;
    state.optionFeedbackInterceptionCount = 0;
    closeOptionFeedbackPopup();
    deactivateAllTriggers();
  }

  function recordFollowupAnswer(answer, domain, slot, questionText) {
    const clean = String(answer || "").trim();
    if (!clean) return;
    state.followupAnswers.push({
      answer: clean,
      domain: domain || "",
      slot: slot || "",
      question: String(questionText || ""),
      at: Date.now(),
    });
    if (state.followupAnswers.length > 20) {
      state.followupAnswers = state.followupAnswers.slice(-20);
    }
  }

  // Dev panel completely removed for production
  /*
  function mountDevPanel() {
    if (!enableDevTriggerPanel || !hudPanel) return;
    const existingPanel = document.getElementById("devTriggerPanel");
    if (existingPanel) {
      existingPanel.remove();
      devButtons.clear();
    }

    const panel = document.createElement("div");
    panel.className = "hud-section dev-trigger-panel";
    panel.id = "devTriggerPanel";

    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Trigger Test (Dev)";
    panel.appendChild(title);

    const row = document.createElement("div");
    row.className = "dev-trigger-grid";

    getTriggerNames().forEach((name) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost small dev-trigger-btn";
      btn.textContent = name;
      btn.addEventListener("click", () => {
        if (isTriggerActive(name)) {
          deactivateTrigger(name);
          return;
        }
        activateTrigger(name, { force: true, manual: true, userState: currentUserState() });
      });
      devButtons.set(name, btn);
      row.appendChild(btn);
    });

    const hardQuestionBtn = document.createElement("button");
    hardQuestionBtn.type = "button";
    hardQuestionBtn.className = "btn ghost small dev-trigger-btn";
    hardQuestionBtn.textContent = "hardQuestion";
    hardQuestionBtn.addEventListener("click", () => {
      if (state.hardQuestionChallenge) {
        clearHardQuestionChallenge();
        showDevToast("Hard question cleared.");
        return;
      }
      const q = testQuestions[testQuestionIndex];
      if (!q || !q.question_id || !questionBody) {
        showDevToast("No active question available for hard question.");
        return;
      }
      const devQuestion = { ...q, difficulty: "hard" };
      activateHardQuestionChallenge(devQuestion);
      showDevToast("Hard question challenge activated.");
    });
    row.appendChild(hardQuestionBtn);





    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "btn danger small dev-trigger-clear";
    clearBtn.textContent = "Clear Triggers";
    clearBtn.addEventListener("click", () => deactivateAllTriggers());

    const showFollowupsBtn = document.createElement("button");
    showFollowupsBtn.type = "button";
    showFollowupsBtn.className = "btn ghost small dev-trigger-followups";
    showFollowupsBtn.textContent = "Show Follow-up Answers";
    showFollowupsBtn.addEventListener("click", () => {
      const rows = getFollowupAnswers();
      log("followup_answers_count", rows.length);
      log("followup_answers", rows);
    });

    const clearFollowupsBtn = document.createElement("button");
    clearFollowupsBtn.type = "button";
    clearFollowupsBtn.className = "btn danger small dev-trigger-followups-clear";
    clearFollowupsBtn.textContent = "Clear Follow-up Answers";
    clearFollowupsBtn.addEventListener("click", () => {
      state.followupAnswers = [];
      log("followup_answers_cleared");
    });

    const fallbackBtn = document.createElement("button");
    fallbackBtn.type = "button";
    fallbackBtn.className = "btn primary small dev-fallback-open";
    fallbackBtn.textContent = "Open Fallback Questions";
    fallbackBtn.addEventListener("click", async () => {
      await openDevFallbackQuestionsDirect();
    });

    panel.appendChild(row);


    panel.appendChild(fallbackBtn);
    panel.appendChild(clearBtn);
    panel.appendChild(showFollowupsBtn);
    panel.appendChild(clearFollowupsBtn);
    hudPanel.appendChild(panel);
  }
  */

  function attachGlobalListeners() {
    ["click", "keydown", "scroll", "pointerdown"].forEach((eventName) => {
      window.addEventListener(eventName, (evt) => {
        const idleBefore = Date.now() - state.lastInteractionAt;
        markInteraction(eventName, evt);
        if ((eventName === "click" || eventName === "keydown") && idleBefore > 9000) {
          requestTriggerFromAI("idle_resumed", { idle_before_ms: idleBefore });
        }
      }, { passive: true });
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        state.lastContextSwitchAt = Date.now();
        return;
      }
      if (!state.lastContextSwitchAt) return;
      const hiddenMs = Math.max(0, Date.now() - state.lastContextSwitchAt);
      state.lastContextSwitchAt = 0;
      if (hiddenMs >= 1200) {
        requestTriggerFromAI("context_switched", {
          focus_lost_ms: hiddenMs,
        });
      }
    });

    window.addEventListener("devicemotion", (evt) => {
      const accel = evt?.accelerationIncludingGravity;
      if (!accel) return;
      const magnitude = Math.sqrt(
        Math.pow(Number(accel.x || 0), 2) +
        Math.pow(Number(accel.y || 0), 2) +
        Math.pow(Number(accel.z || 0), 2)
      );
      const jitterIndex = Math.max(0, Math.min(10, (magnitude - 8) * 1.2));
      updateDeviceMovement(jitterIndex);
      if (state.deviceMovementIndex >= 6 && Date.now() - state.lastAgitationEventAt > 10000) {
        state.lastAgitationEventAt = Date.now();
        requestTriggerFromAI("device_agitation", {
          device_movement_index: state.deviceMovementIndex,
        });
      }
    }, { passive: true });

    // Legacy auto-monitor loop removed intentionally.
  }

  return {
    activateTrigger,
    deactivateTrigger,
    deactivateAllTriggers,
    isTriggerActive,
    canActivateTrigger,
    isInterruptionActive,
    isScreenBusyForPopup,
    requestFeedbackPulse: showFeedbackPulse,
    evaluateUserState,
    currentUserState,
    setStage,
    onQuestionRendered,
    onOptionChange,
    onOptionClick,
    onOptionHover,
    onOptionPointerDown,
    onOptionPointerUp,
    beginExamTimer,
    stopExamTimer,
    onPopupsEntered,
    beforeSubmitDelay,
    afterSubmit,
    noteAnswerOutcome,
    onReset,
    attachGlobalListeners,
    // mountDevPanel removed for production
    getTriggerNames,
    activateManualShowcaseTrigger,
    recordFollowupAnswer,
    getFollowupAnswers,
    consumePostSubmitDelayMs,
    // Q6 interception helpers
    isOptionFeedbackInterceptionEnabled: () => state.optionFeedbackInterceptionEnabled,
    getOptionFeedbackInterceptionCount: () => state.optionFeedbackInterceptionCount,
    getOptionFeedbackMaxInterceptions: () => state.optionFeedbackMaxInterceptions,
    incrementOptionFeedbackInterceptionCount: () => { state.optionFeedbackInterceptionCount++; },
    // Timer helpers
    timeUsedMs,
    timeRemainingMs,
  };
})();

// Expose StressTriggers to window for access from other scripts
window.StressTriggers = StressTriggers;

// Socket -------------------------------------------------------------------
function initSocket() {
  if (socketInitialized) return;
  // Allow polling fallback so users on strict networks still connect.
  socket = io({ transports: ["polling", "websocket"] });
  socketInitialized = true;

  socket.on("connect", () => {
    $("wsStatus").textContent = "WS: connected";
    log("WS connected", socket.id);
    if (sessionId) {
      socket.emit("join_session", { session_id: sessionId });
      logPopupEvent({ event: "join_session_reconnect", session_id: sessionId });
    }
    logPopupEvent({ event: "connect", socket_id: socket.id });
  });

  socket.on("disconnect", () => {
    $("wsStatus").textContent = "WS: disconnected";
    log("WS disconnected");
    logPopupEvent({ event: "disconnect" });
  });

  socket.on("connect_error", (err) => {
    log("WS error", err.message || String(err));
    logPopupEvent({ event: "connect_error", error: err.message || String(err) });
  });

  socket.on("server_hello", (data) => log("server_hello", data));

  socket.on("joined", (data) => log("joined room", data));

  socket.on("popup", (payload) => {
    void payload;
  });

  socket.on("suggestions", (payload) => {
    setSuggestions((payload && payload.items) || []);
  });

  socket.onAny((event, payload) => {
    if (event === "popup") return;
    logPopupEvent({ event, payload });
  });
}

function joinSessionRoom(targetId) {
  const id = targetId || sessionId;
  if (!id) return;
  if (!socketInitialized) initSocket();
  const payload = { session_id: id };
  const emitJoin = () => {
    socket.emit("join_session", payload);
    logPopupEvent({ event: "join_session", session_id: id });
  };

  if (socket.connected) emitJoin();
  else socket.once("connect", emitJoin);
}

// Popup rendering ----------------------------------------------------------
function logPopupEvent(obj) {
  if (!logBox) return;
  const line = `[DBG ${new Date().toLocaleTimeString()}] ${JSON.stringify(obj)}`;
  logBox.textContent = (logBox.textContent + line + "\n").slice(-20000);
  logBox.scrollTop = logBox.scrollHeight;
}

function normalizePopupMessage(rawMessage) {
  let text = "";
  if (typeof rawMessage === "string") {
    text = rawMessage;
  } else if (Array.isArray(rawMessage)) {
    text = rawMessage.map((item) => normalizePopupMessage(item)).find(Boolean) || "";
  } else if (rawMessage && typeof rawMessage === "object") {
    text = normalizePopupMessage(rawMessage.message || rawMessage.text || rawMessage.value || "");
  } else if (rawMessage != null) {
    text = String(rawMessage);
  }

  const trimmed = String(text || "").trim();
  if (!trimmed) return "";

  // Recover from stringified arrays/objects if server sends serialized payloads.
  if (
    (trimmed.startsWith("[") && trimmed.endsWith("]")) ||
    (trimmed.startsWith("{") && trimmed.endsWith("}"))
  ) {
    try {
      const parsed = JSON.parse(trimmed);
      const parsedText = normalizePopupMessage(parsed);
      if (parsedText) return parsedText;
    } catch (e) {
      // Keep original text when it is not valid JSON.
    }
  }

  return trimmed
    .replace(/\[\s*([^\[\]]+?)\s*\]/g, "$1")
    .replace(/[\[\]]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function enqueuePopup(payload) {
  void payload;
}

function processPopupQueue() {
  return;
}

function showPopupCard(payload, done) {
  void payload;
  done?.();
}

function escapeHTML(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Acadza question panel ----------------------------------------------------
function setTestHint(text) {
  if (testHint) testHint.textContent = text || "";
}

function ensureTestBankLoadingOverlay() {
  if (!testCard) return null;
  let overlay = testCard.querySelector(".test-bank-loading");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.className = "test-bank-loading";
  overlay.innerHTML = `
    <div class="test-bank-loading-card">
      <div class="test-bank-loading-spinner" aria-hidden="true"></div>
      <div class="test-bank-loading-title">Loading Test</div>
      <div class="test-bank-loading-status">Preparing your complete test set...</div>
    </div>
  `;
  testCard.appendChild(overlay);
  return overlay;
}

function setTestBankLoading(loading, message) {
  if (!testCard) return;
  const overlay = ensureTestBankLoadingOverlay();
  isLoadingTestBank = Boolean(loading);
  testCard.classList.toggle("is-loading-bank", isLoadingTestBank);
  testCard.setAttribute("aria-busy", isLoadingTestBank ? "true" : "false");
  const statusNode = overlay?.querySelector(".test-bank-loading-status");
  if (statusNode) {
    statusNode.textContent = message || "Preparing your complete test set...";
  }
  if (isLoadingTestBank) {
    if (btnSubmitQuestion) btnSubmitQuestion.disabled = true;
  } else {
    updateTestSubmitButtonState();
  }
}

function ensureStemOptionsInQuestion(q, parts) {
  if (!q || !Array.isArray(q.options) || !q.options.length) return;
  const html = String(q.question_html || "");
  const normalizedHtmlText = html
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .toLowerCase()
    .trim();

  const optionTextsInStem = q.options.reduce((count, opt) => {
    const text = String(opt?.text || "")
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ")
      .toLowerCase()
      .trim();
    if (!text || text.length < 2) return count;
    return normalizedHtmlText.includes(text) ? count + 1 : count;
  }, 0);

  const labelPatternInStem =
    /(?:^|[\s>])(a|b|c|d)\s*[\)\.\:\-]\s*/i.test(normalizedHtmlText) ||
    /option\s*(a|b|c|d)/i.test(normalizedHtmlText);

  const hasBuiltInOptions =
    /class\s*=\s*["'][^"']*stem-options[^"']*["']/i.test(html) ||
    /<ol[\s>]/i.test(html) ||
    /<ul[\s>]/i.test(html) ||
    optionTextsInStem >= 2 ||
    (optionTextsInStem >= 1 && labelPatternInStem);
  if (hasBuiltInOptions) return;
  const rows = q.options
    .map((opt) => {
      const label = (opt?.label || "").trim();
      const text = (opt?.text || "").trim();
      if (!label && !text) return "";
      return `<div class="stem-option-row"><strong>${label}${label ? ")" : ""}</strong> ${processAcadzaHtml(text)}</div>`;
    })
    .filter(Boolean);
  if (!rows.length) return;
  parts.push(`<div class="stem-options">${rows.join("")}</div>`);
}

function stripEmbeddedOptionsFromQuestionHtml(html) {
  const source = String(html || "");
  if (!source) return "";
  const markerMatch = source.match(/\([A-D]\)|(?:^|[\s>])[A-D]\s*[\)\.\:\-]\s*/i);
  if (!markerMatch || markerMatch.index === undefined || markerMatch.index <= 0) {
    return source;
  }
  const stem = source.slice(0, markerMatch.index).trim();
  return stem || source;
}

function collectQuestionImageUrls(q) {
  const urls = [];
  if (Array.isArray(q?.question_images)) {
    q.question_images.forEach((src) => {
      if (typeof src === "string" && src.trim()) urls.push(src.trim());
    });
  }
  const html = processAcadzaHtml(q?.question_html || "");
  const regex = /<img[^>]+src=["']([^"']+)["']/gi;
  let match = regex.exec(html);
  while (match) {
    if (match[1]) urls.push(processAcadzaHtml(match[1]));
    match = regex.exec(html);
  }
  return urls;
}

function preloadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = src;
  });
}

async function preloadQuestionAssets(questions) {
  if (!Array.isArray(questions) || !questions.length) return;
  const uniqueUrls = new Set();
  questions.forEach((q) => {
    collectQuestionImageUrls(q).forEach((url) => uniqueUrls.add(url));
  });
  if (!uniqueUrls.size) return;
  await Promise.all([...uniqueUrls].map((url) => preloadImage(url)));
}

function updateTestSubmitButtonState() {
  if (!btnSubmitQuestion) return;
  const q = testQuestions[testQuestionIndex];
  if (!q) {
    btnSubmitQuestion.disabled = true;
    return;
  }
  const picked = selectedOptions[q.question_id];
  const hasValue = Boolean(String(picked || "").trim());
  btnSubmitQuestion.disabled = !hasValue;
}

function updateSolutionButtonState() {
  if (!btnShowSolution) return;
  const q = testQuestions[testQuestionIndex];
  if (!q) {
    btnShowSolution.hidden = true;
    btnShowSolution.classList.add("is-disabled");
    return;
  }
  const answered = Boolean(answeredMap[q.question_id]);
  btnShowSolution.hidden = !answered;
  btnShowSolution.classList.toggle("is-disabled", !answered);
}

function updateTestHintForQuestion(q) {
  if (!q) {
    setTestHint("");
    return;
  }
  const row = answeredMap[q.question_id];
  if (!row || !row.selected) {
    setTestHint("");
    return;
  }
  const qType = (q.question_type || "").toLowerCase();
  if (qType === "integer") {
    setTestHint("Answer saved.");
    return;
  }
  setTestHint(row.correct ? "Correct answer." : "Wrong answer.");
}

function advanceAfterSubmit() {
  if (!testQuestions.length) return;
  if (solutionModalOpen) {
    pendingAdvanceAfterSubmit = true;
    return;
  }
  const atLastQuestion = testQuestionIndex >= testQuestions.length - 1;
  if (atLastQuestion) {
    setTestHint("Last question saved. You can finish the test.");
    return;
  }
  
  // Cancel any pending triggers from the current question
  cancelPendingTriggers();
  
  // Deactivate all active triggers from the current question
  if (typeof StressTriggers !== 'undefined' && StressTriggers.deactivateAllTriggers) {
    StressTriggers.deactivateAllTriggers();
    console.log('[advanceAfterSubmit] Deactivated all active triggers');
  }
  
  testQuestionIndex += 1;
  renderTestQuestion();
}

function applyAdaptiveQuestionDensity(q) {
  if (!questionPanel || !questionStem) return;
  questionPanel.classList.remove("size-normal", "size-compact", "size-dense");

  const stemText = String(questionStem.textContent || "").replace(/\s+/g, " ").trim();
  const optionText = Array.isArray(q?.options)
    ? q.options.map((opt) => String(opt?.text || "")).join(" ")
    : "";
  const totalLen = stemText.length + optionText.length;
  const hasManyOptions = Array.isArray(q?.options) && q.options.length >= 4;
  const hasImages =
    (Array.isArray(q?.question_images) && q.question_images.length > 0) ||
    /<img[\s>]/i.test(String(q?.question_html || ""));

  let mode = "size-normal";
  if (totalLen > 1300 || (totalLen > 1000 && hasManyOptions) || (hasImages && totalLen > 900)) {
    mode = "size-dense";
  } else if (totalLen > 850 || (hasImages && totalLen > 650)) {
    mode = "size-compact";
  }

  questionPanel.classList.add(mode);

  // Ensure density reacts to real rendered height too.
  requestAnimationFrame(() => {
    if (!questionPanel || !questionStem) return;
    const overflowGap = questionStem.scrollHeight - questionPanel.clientHeight;
    if (overflowGap > 420 && !questionPanel.classList.contains("size-dense")) {
      questionPanel.classList.remove("size-normal", "size-compact");
      questionPanel.classList.add("size-dense");
    } else if (overflowGap > 220 && questionPanel.classList.contains("size-normal")) {
      questionPanel.classList.remove("size-normal");
      questionPanel.classList.add("size-compact");
    }
  });
}

function stripHardQuestionLabel(html) {
  // Remove "HARD QUESTION:" label from question HTML
  if (!html) return html;
  return html.replace(/<strong>\s*HARD\s+QUESTION\s*:\s*<\/strong>\s*/gi, '');
}

function processAcadzaHtml(html) {
  if (window.AcadzaRender?.processAcadzaHtml) {
    return window.AcadzaRender.processAcadzaHtml(html);
  }
  return html || "";
}

function clearQuestionStem(message) {
  if (questionStem && window.AcadzaRender?.destroy) {
    window.AcadzaRender.destroy(questionStem);
  }
  if (questionStem) questionStem.textContent = message || "";
}

function buildQuestionStemHtml(q) {
  const parts = [];
  if (q?.question_html) {
    const cleanedHtml = stripHardQuestionLabel(q.question_html);
    parts.push(stripEmbeddedOptionsFromQuestionHtml(cleanedHtml));
  }
  ensureStemOptionsInQuestion(q, parts);
  if (Array.isArray(q?.question_images)) {
    q.question_images.forEach((src) => {
      if (typeof src !== "string" || !src.trim()) return;
      const url = processAcadzaHtml(src.trim());
      parts.push(`<div class="q-img"><img src="${url}" alt="question image" /></div>`);
    });
  }
  return parts.join("");
}

function renderQuestionStemHtml(q, onReady) {
  if (!questionStem) return;
  const html = buildQuestionStemHtml(q);
  if (window.AcadzaRender?.renderInto) {
    window.AcadzaRender.renderInto(questionStem, html, { onReady });
    return;
  }
  questionStem.innerHTML = processAcadzaHtml(html);
  if (typeof onReady === "function") onReady();
}

function renderTestQuestion() {
  if (!questionStem || !questionOptions || !questionCounter) return;
  if (isLoadingTestBank) return;

  if (!testQuestions.length) {
    clearQuestionStem("Questions will appear here with options.");
    questionOptions.innerHTML = "";
    questionCounter.textContent = "Q. 1 of 1";
    if (questionSubject) questionSubject.textContent = "ID: —";
    if (questionTypeSelect) questionTypeSelect.options[0].textContent = "Math-Single Type";
    if (questionProgress) questionProgress.style.width = "0%";
    if (mutateBadge) mutateBadge.style.display = "none";
    if (btnPrevQuestion) btnPrevQuestion.disabled = true;
    if (btnNextQuestion) btnNextQuestion.disabled = true;
    updateSolutionButtonState();
    return;
  }

  testQuestionIndex = Math.min(Math.max(testQuestionIndex, 0), testQuestions.length - 1);
  const q = testQuestions[testQuestionIndex];
  // Q2/Q6 hard-fog sequences hide stem/options; always restore when switching questions.
  if (questionStem) questionStem.style.visibility = "visible";
  if (questionOptions) questionOptions.style.visibility = "visible";
  if (questionCounter) {
    questionCounter.textContent = `Q. ${testQuestionIndex + 1} of ${testQuestions.length}`;
  }
  if (questionSubject) {
    questionSubject.textContent = `ID: ${q.question_id || "—"}`;
  }
  if (questionTypeSelect) {
    const rawType = q.subject || q.chapter || q.topic || "Math";
    const label = `${rawType}-Single Type`;
    questionTypeSelect.options[0].textContent = label;
  }
  if (questionProgress) {
    const pct = ((testQuestionIndex + 1) / testQuestions.length) * 100;
    questionProgress.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  }
  if (mutateBadge) {
    const mutated = Boolean(q.mutated || (q.meta && q.meta.mutated));
    mutateBadge.style.display = mutated ? "inline-flex" : "none";
  }
  const qType = (q.question_type || "").toLowerCase();
  if (questionBody) {
    questionBody.classList.toggle("integer-mode", qType === "integer");
  }
  if (qType === "integer") {
    if (questionOptions) questionOptions.style.display = "none";
    if (integerPanel) {
      integerPanel.style.display = "flex";
      const existing = selectedOptions[q.question_id] || "";
      if (integerInput) integerInput.value = existing;
      attachKeypadListeners();
    }
  } else {
    if (questionOptions) questionOptions.style.display = "grid";
    if (integerPanel) integerPanel.style.display = "none";
  }
  updateSolutionButtonState();
  updateTestHintForQuestion(q);
  renderQuestionStemHtml(q, () => {
    applyAdaptiveQuestionDensity(q);
    StressTriggers.onQuestionRendered(q);
  });
  questionOptions.innerHTML = "";

  const opts = q.options || [];
  if (qType !== "integer" && !opts.length) {
    const empty = document.createElement("div");
    empty.className = "option-empty";
    empty.textContent = "No options provided.";
    questionOptions.appendChild(empty);
  } else if (qType !== "integer") {
    opts.forEach((opt) => {
      const wrapper = document.createElement("label");
      wrapper.className = "option";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `option-${q.question_id}`;
      input.value = opt.label;
      input.checked = selectedOptions[q.question_id] === opt.label;
      input.addEventListener("change", () => {
        const prev = selectedOptions[q.question_id] || "";
        selectedOptions[q.question_id] = opt.label;
        StressTriggers.onOptionChange(q.question_id, prev, opt.label);
        updateTestSubmitButtonState();
      });
      wrapper.addEventListener("mouseenter", () => {
        StressTriggers.onOptionHover(wrapper);
      });
      wrapper.addEventListener("pointerdown", (evt) => {
        StressTriggers.onOptionPointerDown(wrapper, evt);
      });
      wrapper.addEventListener("pointerup", () => {
        StressTriggers.onOptionPointerUp();
      });
      wrapper.addEventListener("pointercancel", () => {
        StressTriggers.onOptionPointerUp();
      });
      wrapper.addEventListener("click", () => {
        StressTriggers.onOptionClick(q.question_id, opt.label);
      });

      const body = document.createElement("div");
      const labelEl = document.createElement("div");
      labelEl.className = "option-label";
      labelEl.textContent = opt.label || "";
      const markEl = document.createElement("div");
      markEl.className = "option-mark";
      markEl.textContent = "";
      const textEl = document.createElement("div");
      textEl.className = "option-text";
      if (window.AcadzaRender?.renderPlainHtml) {
        window.AcadzaRender.renderPlainHtml(textEl, opt.text || "");
      } else {
        textEl.innerHTML = processAcadzaHtml(opt.text || "");
      }
      body.appendChild(labelEl);
      body.appendChild(markEl);
      body.appendChild(textEl);

      wrapper.appendChild(input);
      wrapper.appendChild(body);
      questionOptions.appendChild(wrapper);
    });
  }

  if (btnPrevQuestion) btnPrevQuestion.disabled = testQuestionIndex === 0;
  if (btnNextQuestion) btnNextQuestion.disabled = testQuestionIndex >= testQuestions.length - 1;
  updateTestSubmitButtonState();
  updateScoreMeta();
  updateLifelineState();
  renderResultStateForCurrentQuestion();
}

/* ── question prefetch metadata ─────────────────────────────────────── */
let _prefetchMeta = null;  // {subject, topics}

/**
 * Store subject/topics so loadTestQuestions can skip the /debug roundtrip.
 * Call this as soon as subject/topics are known.
 */
function startQuestionPrefetch(subject, topics) {
  console.log("[prefetch] storing meta for", subject, topics);
  _prefetchMeta = {
    subject: subject || null,
    topics: topics || [],
  };
}

async function loadTestQuestions() {
  if (!questionStem || !questionCounter) return;
  let hasRenderableQuestions = false;
  setTestBankLoading(true, "Fetching all questions...");
  setTestHint("");
  questionCounter.textContent = "";
  if (questionSubject) questionSubject.textContent = "";
  if (questionTypeSelect) questionTypeSelect.options[0].textContent = "";
  if (questionProgress) questionProgress.style.width = "0%";
  clearMutationTimers();
  clearQuestionStem("");
  questionOptions.innerHTML = "";
  try {
    let payload = {};

    // Get user profile for question selection
    const user = window.StressDostAuth?.getUser?.();
    const userProfile = {
      completed_sessions: user?.completed_sessions || 0,
      total_sessions: user?.total_sessions || 0
    };

    // Use stored metadata if available (skips the /debug roundtrip)
    if (_prefetchMeta) {
      console.log("[loadTestQuestions] using prefetched meta:", _prefetchMeta);
      payload = { ..._prefetchMeta, user_profile: userProfile };
      _prefetchMeta = null;
    } else if (sessionId) {
      // Fallback: fetch meta from debug endpoint
      try {
        const dbg = await getJSON(`/session/${sessionId}/debug`);
        const meta = dbg?.meta || {};
        payload = {
          subject: meta.selected_subject || null,
          topics: meta.selected_topics || [],
          user_profile: userProfile
        };
      } catch (err) {
        log("session_debug_error", err);
        payload = { user_profile: userProfile };
      }
    } else {
      payload = { user_profile: userProfile };
    }

    console.log("[loadTestQuestions] User profile:", userProfile);
    const data = await postJSON("/api/questions/load-test-questions", payload);

    testQuestions = data.questions || [];
    testQuestionIndex = 0;
    if (!testQuestions.length) {
      setTestHint("No questions returned. Add IDs to data/question_ids.csv.");
      questionCounter.textContent = "Questions unavailable";
      return;
    }
    selectedOptions = {};
    answeredMap = {};
    
    // Fetch trigger plan for Focus Zones test
    await fetchQuestionTriggerPlan();
    
    setTestBankLoading(true, "Caching question assets...");
    await preloadQuestionAssets(testQuestions);
    hasRenderableQuestions = testQuestions.length > 0;
    setTestHint("");
  } catch (err) {
    _prefetchMeta = null;
    console.error("[loadTestQuestions] FAILED:", err, err?.stack);
    testQuestions = cloneClientFallbackQuestions();
    testQuestionIndex = 0;
    selectedOptions = {};
    answeredMap = {};
    setTestBankLoading(true, "Caching fallback assets...");
    await preloadQuestionAssets(testQuestions);
    hasRenderableQuestions = testQuestions.length > 0;
    setTestHint("Server unavailable. Loaded local demo questions for trigger testing.");
    log("questions_load_error", err.message || String(err));
  } finally {
    setTestBankLoading(false, "Question bank ready");
    if (hasRenderableQuestions) {
      renderTestQuestion();
    }
  }
}

function buildLocalNewUserTriggerPlan() {
  const sequence = LOCAL_NEW_USER_TRIGGER_NAMES.map((trigger_name, idx) => ({
    question_number: idx + 1,
    trigger_name,
    difficulty: trigger_name.includes("HARD") ? "hard" : "medium",
    intensity: idx < 2 ? "mild" : idx < 5 ? "moderate" : "strong",
    is_hard: trigger_name === "HARD_FOG" || trigger_name === "HARD_PEER_DOUBT",
    is_meta_question: trigger_name === "HARD_FOG" || trigger_name === "HARD_PEER_DOUBT",
  }));
  return {
    status: "success",
    is_new_user: true,
    user_type: "new",
    total_questions: 7,
    medium_count: sequence.filter((t) => !t.is_hard).length,
    hard_count: sequence.filter((t) => t.is_hard).length,
    sequence,
  };
}

function ensureQuestionTriggerPlan() {
  if (questionTriggerPlan?.sequence?.length === 7) return;
  questionTriggerPlan = buildLocalNewUserTriggerPlan();
  console.log("[ensureQuestionTriggerPlan] Using local new-user sequence");
}

async function fetchQuestionTriggerPlan() {
  try {
    // Get user from auth system
    const user = window.StressDostAuth?.getUser?.();
    
    // Get previous triggers from localStorage
    const previousTriggers = JSON.parse(localStorage.getItem('previousTriggers') || '[]');
    
    const userProfile = {
      name: user?.display_name || '',
      test_count: user?.completed_sessions || 0,
      completed_sessions: user?.completed_sessions || 0,  // Send both fields for backend compatibility
      previous_triggers: previousTriggers,
      force_new_user: true,
    };
    
    // Extract question difficulties from loaded questions
    const questionDifficulties = testQuestions.map(q => (q.level || 'MEDIUM').toUpperCase());
    
    console.log('[fetchQuestionTriggerPlan] Fetching trigger plan for user:', userProfile);
    console.log('[fetchQuestionTriggerPlan] Question difficulties:', questionDifficulties);
    
    const response = await postJSON('/api/questions/trigger-plan', {
      user_profile: userProfile,
      question_difficulties: questionDifficulties
    });
    
    questionTriggerPlan = response;
    if (!questionTriggerPlan?.sequence?.length) {
      questionTriggerPlan = buildLocalNewUserTriggerPlan();
    }
    console.log('[fetchQuestionTriggerPlan] Trigger plan received:', questionTriggerPlan);
    console.log('[fetchQuestionTriggerPlan] Sequence:', questionTriggerPlan?.sequence);
    console.log('[fetchQuestionTriggerPlan] User type:', questionTriggerPlan?.user_type);
    console.log('[fetchQuestionTriggerPlan] Is new user:', questionTriggerPlan?.is_new_user);
    
    // Store for next test
    if (response.sequence && Array.isArray(response.sequence)) {
      const triggerNames = response.sequence.map(t => t.trigger_name);
      localStorage.setItem('previousTriggers', JSON.stringify(triggerNames));
    }
  } catch (err) {
    console.error('[fetchQuestionTriggerPlan] Failed to fetch trigger plan:', err);
    console.error('[fetchQuestionTriggerPlan] Error details:', err.message, err.stack);
    questionTriggerPlan = buildLocalNewUserTriggerPlan();
  }
}

function getQuestionTrigger(questionNumber) {
  ensureQuestionTriggerPlan();
  console.log('[getQuestionTrigger] Called for question:', questionNumber);
  console.log('[getQuestionTrigger] questionTriggerPlan:', questionTriggerPlan);
  
  if (!questionTriggerPlan || !questionTriggerPlan.sequence) {
    console.log('[getQuestionTrigger] No trigger plan available');
    return null;
  }
  
  // questionNumber is 1-indexed
  const triggerConfig = questionTriggerPlan.sequence[questionNumber - 1];
  if (!triggerConfig) {
    console.log('[getQuestionTrigger] No trigger config for question', questionNumber);
    return null;
  }
  
  console.log('[getQuestionTrigger] Trigger config:', triggerConfig);
  
  // Convert backend trigger name to frontend trigger name
  // Backend: TORCHLIGHT_SPOTLIGHT -> Frontend: torchlightSpotlight
  const triggerName = triggerConfig.trigger_name;
  if (!triggerName) {
    console.log('[getQuestionTrigger] No trigger_name in config');
    return null;
  }
  
  const frontendTriggerName = triggerName
    .split('_')
    .map((word, idx) => {
      if (idx === 0) return word.toLowerCase();
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join('');
  
  console.log('[getQuestionTrigger] Converted', triggerName, 'to', frontendTriggerName);
  
  return {
    name: frontendTriggerName,
    difficulty: triggerConfig.difficulty,
    intensity: triggerConfig.intensity,
    isHard: triggerConfig.is_hard,
    metadata: triggerConfig
  };
}


function gotoQuestion(delta) {
  if (!testQuestions.length) return;
  
  // Cancel any pending triggers from the previous question
  cancelPendingTriggers();
  
  // Deactivate all active triggers from the previous question
  if (typeof StressTriggers !== 'undefined' && StressTriggers.deactivateAllTriggers) {
    StressTriggers.deactivateAllTriggers();
    console.log('[gotoQuestion] Deactivated all active triggers');
  }
  
  testQuestionIndex = Math.min(
    Math.max(testQuestionIndex + delta, 0),
    testQuestions.length - 1
  );
  renderTestQuestion();
}

function shouldMutateQuestion(q) {
  if (!q) return false;
  const type = (q.question_type || "").toLowerCase();
  if (!["scq", "integer"].includes(type)) return false;
  // Mutate any question that has digits in stem or options
  const hasDigits =
    /\d/.test(q.question_html || "") ||
    (Array.isArray(q.options) && q.options.some((opt) => /\d/.test(opt?.text || "")));
  return hasDigits && !q.mutated && !(q.meta && q.meta.mutated);
}

function scheduleMutationsForQuestions() {
  clearMutationTimers();
  if (mutationPaused) return;
  const maxMutations = 4;
  let scheduled = 0;
  testQuestions.forEach((q, idx) => {
    if (scheduled >= maxMutations) return;
    if (!shouldMutateQuestion(q)) return;
    // Stagger mutations to avoid saturating OpenAI calls that also power triggers.
    const delayMs = 7000 + (scheduled * 9000);
    const timerId = setTimeout(() => mutateQuestionAt(idx), delayMs);
    mutationTimers.push(timerId);
    scheduled += 1;
  });
}

async function mutateQuestionAt(index) {
  if (mutationPaused) return;
  const q = testQuestions[index];
  if (!q || q.mutated || (q.meta && q.meta.mutated)) return;
  try {
    const res = await fetch(`/api/questions/mutate/${q.question_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId || null }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.question) {
      const mutated = data.question;
      mutated.mutated = Boolean(data.mutated);
      testQuestions[index] = mutated;
      if (index === testQuestionIndex) {
        renderTestQuestion();
      }
    } else {
      log("mutate_failed", data.message || data.error || res.status);
    }
  } catch (err) {
    log("mutate_error", err.message || String(err));
  }
}

async function submitCurrentQuestion() {
  console.log('[submitCurrentQuestion] Called');
  
  if (!testQuestions.length) {
    setTestHint("Load questions first.");
    return;
  }
  
  await StressTriggers.beforeSubmitDelay();
  try {
    const q = testQuestions[testQuestionIndex];
    const picked = selectedOptions[q.question_id];
    const qType = (q.question_type || "").toLowerCase();

    if (qType === "integer") {
      const value = (picked || "").trim();
      if (!value) {
        setTestHint("Enter an integer answer first.");
        return;
      }
      const correctVal = q.integer_answer;
      let correct = false;
      const hasAnswerKey = correctVal !== undefined && correctVal !== null;
      if (correctVal !== undefined && correctVal !== null) {
        const numPicked = Number(value);
        const numCorrect = Number(correctVal);
        if (!Number.isNaN(numPicked) && !Number.isNaN(numCorrect)) {
          correct = Math.abs(numPicked - numCorrect) < 1e-6;
        } else {
          correct = value === String(correctVal).trim();
        }
      }
      answeredMap[q.question_id] = { selected: value, correct };
      updateSolutionButtonState();
      updateScoreMeta();
      const lifelinesBeforeDecrement = _lifelines;
      if (!correct && _lifelines > 0) _lifelines -= 1;
      console.log('[submitCurrentQuestion] Lifelines:', lifelinesBeforeDecrement, '→', _lifelines, 'Correct:', correct);
      updateLifelineState();
      
      // Check if test should end due to lifeline loss
      if (_lifelines <= 0) {
        console.log('[submitCurrentQuestion] All lifelines lost! Showing end screen');
        
        // Capture the time used at this moment
        const timeUsedAtEnd = StressTriggers.timeUsedMs();
        console.log('[submitCurrentQuestion] timeUsedAtEnd:', timeUsedAtEnd);
        
        // Cancel all pending triggers
        cancelPendingTriggers();
        
        // Deactivate all active triggers immediately
        if (typeof StressTriggers !== 'undefined' && StressTriggers.deactivateAllTriggers) {
          StressTriggers.deactivateAllTriggers();
          console.log('[submitCurrentQuestion] Deactivated all triggers');
        }
        
        showLifelineLostBanner();
        setTimeout(() => {
          showTestEndScreen(timeUsedAtEnd);
        }, 2000);
        return; // Don't advance to next question
      }
      
      StressTriggers.noteAnswerOutcome(correct, hasAnswerKey);
      setTestHint("Answer saved.");
      const extraDelayMs = StressTriggers.consumePostSubmitDelayMs?.() || 0;
      if (extraDelayMs > 0) await sleep(extraDelayMs);
      await sleep(SOLUTION_GRACE_MS);
      advanceAfterSubmit();
      return;
    }

    if (!picked) {
      setTestHint("Select an option before submitting.");
      return;
    }
    const correctAnswer = q.correct_answer || q.correct_answers;
    const hasAnswerKey =
      (Array.isArray(correctAnswer) && correctAnswer.length > 0) ||
      (typeof correctAnswer === "string" && Boolean(correctAnswer.trim()));
    let correct = false;
    if (Array.isArray(correctAnswer)) {
      const pickedSet = new Set(Array.isArray(picked) ? picked : [picked]);
      const correctSet = new Set(correctAnswer.map((v) => String(v).trim().toUpperCase()));
      correct = pickedSet.size === correctSet.size && [...pickedSet].every((v) => correctSet.has(String(v).trim().toUpperCase()));
    } else if (typeof correctAnswer === "string") {
      correct = picked.trim().toUpperCase() === correctAnswer.trim().toUpperCase();
    }
    const primaryCorrectLabel = Array.isArray(correctAnswer)
      ? normalizeAnswerLabel(correctAnswer[0])
      : normalizeAnswerLabel(correctAnswer);
    answeredMap[q.question_id] = { selected: picked, correct, correctLabel: primaryCorrectLabel };
    updateSolutionButtonState();
    updateScoreMeta();
    if (!correct && _lifelines > 0) _lifelines -= 1;
    updateLifelineState();
    
    // Check if test should end due to lifeline loss
    if (_lifelines <= 0) {
      console.log('[submitCurrentQuestion] All lifelines lost! Showing end screen');
      
      // Capture the time used at this moment
      const timeUsedAtEnd = StressTriggers.timeUsedMs();
      console.log('[submitCurrentQuestion] timeUsedAtEnd:', timeUsedAtEnd);
      
      // Cancel all pending trigger timeouts
      cancelPendingTriggers();
      
      // Deactivate all active triggers immediately
      if (typeof StressTriggers !== 'undefined' && StressTriggers.deactivateAllTriggers) {
        StressTriggers.deactivateAllTriggers();
        console.log('[submitCurrentQuestion] Deactivated all triggers');
      }
      
      showLifelineLostBanner();
      setTimeout(() => {
        showTestEndScreen(timeUsedAtEnd);
      }, 2000);
      return; // Don't advance to next question
    }
    
    renderResultStateForCurrentQuestion();
    StressTriggers.noteAnswerOutcome(correct, hasAnswerKey);
    setTestHint(correct ? "Correct answer." : "Wrong answer.");
    const extraDelayMs = StressTriggers.consumePostSubmitDelayMs?.() || 0;
    await sleep(900 + extraDelayMs + SOLUTION_GRACE_MS);
    advanceAfterSubmit();
  } finally {
    StressTriggers.afterSubmit();
  }
}

// Flow ---------------------------------------------------------------------
async function startSessionFlow() {
  try {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      setIntroHint("Stop the recording first.");
      return;
    }

    btnStart.disabled = true;
    showStage("loading", recordedAudioBlob ? "Transcribing your recording..." : "Absorbing your story...");
    const text = await resolveInitialText();
    if (!text) {
      setIntroHint("Please share a few thoughts first.");
      showStage("intro");
      return;
    }

    lastAnswerEcho = text;
    sessionInitialQuery = text;
    questionWarningCopyCache = new Map();
    questionWarningCopyPromises = new Map();

    setIntroHint("");
    showStage("loading", "Absorbing your story…");

    const startBody = { text };
    const clientUser = clientUserPayload();
    if (clientUser) startBody.client_user = clientUser;
    const data = await postJSON("/session/start", startBody);
    log("start_session", data);

    setSessionUI(data.session_id, data.active_domains);
    joinSessionRoom(data.session_id);
    clearGhost();

    await fetchNextQuestion("Finding the first question…");
  } catch (err) {
    log("start_error", err.message);
    setIntroHint(err.message);
    showStage("intro");
  } finally {
    btnStart.disabled = false;
  }
}

async function fetchNextQuestion(message) {
  if (!sessionId) return;
  showStage("loading", message || "Designing your next cue…");
  try {
    const data = await postJSON(`/session/${sessionId}/next-question`, {});
    log("next_question", data);

    if (data.pending) {
      setHint(data.message || "Answer the current question first.");
      showStage("qa");
      return;
    }

    if (data.done) {
      await handleCompletion();
      return;
    }

    if (data.followups_complete) {
      await handleCompletion();
      return;
    }

    setQuestionUI(data);
    showStage("qa");
  } catch (err) {
    log("next_question_error", err.message);
    setHint(err.message);
    showStage("qa");
  }
}

async function submitAnswer() {
  // CRITICAL: Deactivate all triggers immediately when user submits
  // This prevents triggers from overlapping with the next question
  StressTriggers.deactivateAllTriggers();

  // Remove persistent Q3 screen flip on answer submit
  const shell = document.querySelector(".app-shell");
  if (shell && shell.dataset.psyqFlipActive === "1") {
    shell._psyqFlipCleanup?.();
  }
  
  if (!sessionId || btnAnswer.disabled) return;
  const answer = answerInput.value.trim();
  if (!answer) {
    hintBox.textContent = "Type a quick sentence first.";
    answerInput.classList.add("shake");
    setTimeout(() => answerInput.classList.remove("shake"), 400);
    return;
  }

  try {
    lastAnswerEcho = answer;
    btnAnswer.disabled = true;
    showStage("loading", "Reading your answer…");

    const payload = {
      answer,
      domain: currentDomain,
      slot: currentSlot,
    };
    const data = await postJSON(`/session/${sessionId}/answer`, payload);
    log("answer", data);
    StressTriggers.recordFollowupAnswer?.(answer, currentDomain, currentSlot, $("questionText")?.textContent || "");

    if (data.need_clarification) {
      setHint("Quick clarifier requested: keep it tight.");
      $("questionText").textContent = data.question || "Need a tiny clarification.";
      btnAnswer.disabled = false;
      showStage("qa");
      return;
    }

    answerInput.value = "";
    setHint("Noted. Crafting the next cue…");
    await fetchNextQuestion("Crafting the next question…");
  } catch (err) {
    log("answer_error", err.message);
    setHint(err.message);
    btnAnswer.disabled = false;
    showStage("qa");
  }
}

// Called by btnSkip (followup QA screen) — skips remaining followup questions, no popup
async function skipRemainingQuestions() {
  if (!sessionId || !btnSkip || btnSkip.hidden || btnSkip.disabled) return;
  try {
    btnSkip.disabled = true;
    btnAnswer.disabled = true;
    showStage("loading", "Finishing session…");
    await postJSON(`/session/${sessionId}/complete`, {});
    await handleCompletion();
  } catch (err) {
    log("skip_error", err.message);
    setHint(err.message || "Could not finish right now.");
    btnSkip.disabled = false;
    btnAnswer.disabled = false;
    showStage("qa");
  }
}

// Called by btnFinishTest (test topbar) — shows confirmation popup before ending the test
function finishTestWithConfirm() {
  const confirmOverlay = document.createElement('div');
  confirmOverlay.style.cssText = `
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    backdrop-filter: blur(4px);
  `;

  confirmOverlay.innerHTML = `
    <div style="
      background: linear-gradient(135deg, rgba(30, 30, 40, 0.95), rgba(20, 20, 30, 0.95));
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 32px;
      max-width: 420px;
      width: 100%;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    ">
      <div style="font-size: 48px; text-align: center; margin-bottom: 16px;">⚠️</div>
      <div style="font-size: 22px; font-weight: 700; color: #FFFFFF; text-align: center; margin-bottom: 12px;">
        Finish Test Early?
      </div>
      <div style="font-size: 15px; color: rgba(255, 255, 255, 0.7); text-align: center; margin-bottom: 24px; line-height: 1.5;">
        The test is still in progress. Your results will be calculated based on questions answered so far.
      </div>
      <div style="display: flex; gap: 12px;">
        <button id="confirmNo" style="
          flex: 1;
          padding: 14px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 10px;
          color: #FFFFFF;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
        ">Continue Test</button>
        <button id="confirmYes" style="
          flex: 1;
          padding: 14px;
          background: rgba(248, 113, 113, 0.15);
          border: 1px solid rgba(248, 113, 113, 0.3);
          border-radius: 10px;
          color: #F87171;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
        ">Finish Now</button>
      </div>
    </div>
  `;

  document.body.appendChild(confirmOverlay);

  confirmOverlay.querySelector('#confirmNo').addEventListener('click', () => {
    confirmOverlay.remove();
  });

  confirmOverlay.querySelector('#confirmYes').addEventListener('click', async () => {
    confirmOverlay.remove();

    // Deactivate all stress triggers
    if (StressTriggers && StressTriggers.deactivateAllTriggers) {
      StressTriggers.deactivateAllTriggers();
    }

    // Stop exam timer and get elapsed time
    let timeUsedMs = 0;
    if (StressTriggers && StressTriggers.stopExamTimer) {
      timeUsedMs = StressTriggers.stopExamTimer() || 0;
    }

    // Increment test count
    const testCount = parseInt(localStorage.getItem('testCount')) || 0;
    localStorage.setItem('testCount', testCount + 1);
    console.log('[finishTestWithConfirm] Test count incremented to:', testCount + 1);

    await showTestEndScreen(timeUsedMs);
  });
}

async function handleCompletion() {
  showStage("loading", "Wrapping up your follow-ups…");
  try {
    if (popupSummary) {
      popupSummary.textContent = "Pressure simulation is ready. Accept challenge to begin.";
    }

    let initialText = "";
    let conversationHistory = [];
    try {
      const dbg = await getJSON(`/session/${sessionId}/debug`);
      initialText = String(dbg?.raw_initial_text || "");
      conversationHistory = Array.isArray(dbg?.history) ? dbg.history : [];
      console.log("[handleCompletion] initialText:", initialText?.substring(0, 80), "history entries:", conversationHistory.length);
    } catch (e) { console.warn("[handleCompletion] debug fetch failed:", e); }

    // Show the devil stage immediately, then hydrate its content in the background.
    showStage("devil");
    if (devilHint) devilHint.textContent = "Preparing your brief...";

    const extractionPromise = window.academicTopics?.decideAndStore?.(sessionId, initialText, conversationHistory);
    const popupPrefetchPromise = prefetchQuestionWarningCopies().catch((err) => {
      console.warn("[handleCompletion] popup prefetch failed:", err);
      return [];
    });

    try {
      await buildDevilBriefPage(initialText, conversationHistory);
      if (devilHint) devilHint.textContent = "";
    } catch (e) {
      console.warn("[handleCompletion] devil brief build failed:", e);
      if (devilHint) devilHint.textContent = "Brief unavailable right now. You can still continue.";
    }

    await popupPrefetchPromise;

    const decision = await extractionPromise;
    console.log("[handleCompletion] extraction decision:", JSON.stringify(decision));
    window.__academicDecision = decision || null;
  } catch (err) {
    console.error("[handleCompletion] error during completion flow:", err);
    window.__academicDecision = null;
    showStage("devil");
    if (devilHint) devilHint.textContent = "Something failed while preparing the brief. You can still continue.";
  }
}

async function acceptDevilChallenge() {
  if (!sessionId) return;

  const decision = window.__academicDecision;
  const autoSubject = decision?.autoPickedSubject || null;
  const autoTopics  = decision?.autoPickedTopics  || null;
  console.log("[acceptDevilChallenge] autoSubject:", autoSubject, "autoTopics:", autoTopics);

  // Only show fullscreen if we have both subject AND topics (ready to start test)
  if (autoSubject && autoTopics) {
    // Store the test parameters for later (after fullscreen)
    pendingTestStart = { autoSubject, autoTopics };
    
    // Show fullscreen requirement stage
    showStage("fullscreen");
    
    // Reset fullscreen status
    if (fullscreenStatus) {
      fullscreenStatus.textContent = 'Please enter fullscreen mode to continue';
      fullscreenStatus.className = 'fullscreen-status error';
    }
    return;
  }

  // If subject is known but topics are not, go to topic selection
  if (autoSubject && !autoTopics) {
    console.log("[acceptDevilChallenge] subject known, topics unknown → chapter screen");
    await window.academicTopics?.loadTopicsForSubject?.(autoSubject, sessionId);
    return;
  }

  // If no subject, go to subject selection
  console.log("[acceptDevilChallenge] no subject → subject screen");
  showStage("subjectSelection");
  await window.academicTopics?.initializeSubjectSelection?.(sessionId, null);
}

// HUD ----------------------------------------------------------------------
function toggleHud(open) {
  if (!hudPanel) return;
  const shouldOpen = typeof open === "boolean" ? open : !hudPanel.classList.contains("open");
  hudPanel.classList.toggle("open", shouldOpen);
}

hudToggle?.addEventListener("click", () => toggleHud());
btnCloseHud?.addEventListener("click", () => toggleHud(false));

// Events -------------------------------------------------------------------
btnStart?.addEventListener("click", startSessionFlow);
btnRecord?.addEventListener("click", async () => {
  try {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      stopRecording();
      return;
    }
    await startRecording();
  } catch (err) {
    setIntroHint(err.message || "Mic access failed.");
    setRecordButtonState();
  }
});
btnAnswer?.addEventListener("click", submitAnswer);
btnSkip?.addEventListener("click", skipRemainingQuestions);
btnRestart?.addEventListener("click", resetFlow);
btnReset?.addEventListener("click", resetFlow);
btnAcceptChallenge?.addEventListener("click", acceptDevilChallenge);
btnLogout?.addEventListener("click", () => {
  if (confirm('Are you sure you want to logout?')) {
    window.StressDostAuth?.clearUser?.();
    // Clear localStorage
    try {
      localStorage.removeItem('sd_user');
      localStorage.removeItem('sd_mood');
    } catch (e) {
      console.error('Failed to clear localStorage:', e);
    }
    window.location.href = "/login";
  }
});
btnPrevQuestion?.addEventListener("click", () => gotoQuestion(-1));
btnNextQuestion?.addEventListener("click", () => gotoQuestion(1));
btnReloadQuestions?.addEventListener("click", () => loadTestQuestions());

// Fullscreen Management
const btnEnterFullscreen = document.getElementById('btnEnterFullscreen');
const fullscreenStatus = document.getElementById('fullscreenStatus');
let isTestActive = false;
let fullscreenWarningOverlay = null;

function isFullscreen() {
  return !!(document.fullscreenElement || document.webkitFullscreenElement || 
            document.mozFullScreenElement || document.msFullscreenElement);
}

function enterFullscreen() {
  const elem = document.documentElement;
  if (elem.requestFullscreen) {
    return elem.requestFullscreen();
  } else if (elem.webkitRequestFullscreen) {
    return elem.webkitRequestFullscreen();
  } else if (elem.mozRequestFullScreen) {
    return elem.mozRequestFullScreen();
  } else if (elem.msRequestFullscreen) {
    return elem.msRequestFullscreen();
  }
  return Promise.reject(new Error('Fullscreen not supported'));
}

function showFullscreenWarning() {
  // Remove existing warning if any
  if (fullscreenWarningOverlay) {
    fullscreenWarningOverlay.remove();
  }

  // Create warning overlay
  fullscreenWarningOverlay = document.createElement('div');
  fullscreenWarningOverlay.style.cssText = `
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.95);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(10px);
  `;

  fullscreenWarningOverlay.innerHTML = `
    <div style="
      background: white;
      border-radius: 20px;
      padding: 48px;
      max-width: 500px;
      text-align: center;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    ">
      <div style="font-size: 64px; margin-bottom: 20px;">⚠️</div>
      <h2 style="
        font-size: 28px;
        font-weight: 700;
        color: #1A202C;
        margin: 0 0 16px 0;
      ">Fullscreen Mode Required</h2>
      <p style="
        font-size: 16px;
        line-height: 1.6;
        color: #4A5568;
        margin: 0 0 32px 0;
      ">
        You have exited fullscreen mode. The test is paused.<br/>
        Please return to fullscreen mode to continue.
      </p>
      <button id="btnReturnFullscreen" style="
        width: 100%;
        padding: 16px 32px;
        font-size: 16px;
        font-weight: 600;
        border-radius: 12px;
        background: linear-gradient(135deg, #6366f1, #7c3aed);
        border: none;
        color: white;
        cursor: pointer;
        box-shadow: 0 4px 16px rgba(124, 58, 237, 0.3);
      ">Return to Fullscreen</button>
    </div>
  `;

  document.body.appendChild(fullscreenWarningOverlay);

  // Add click handler to return button
  const btnReturn = fullscreenWarningOverlay.querySelector('#btnReturnFullscreen');
  btnReturn?.addEventListener('click', async () => {
    try {
      await enterFullscreen();
    } catch (err) {
      console.error('[Fullscreen] Error returning to fullscreen:', err);
    }
  });
}

function hideFullscreenWarning() {
  if (fullscreenWarningOverlay) {
    fullscreenWarningOverlay.remove();
    fullscreenWarningOverlay = null;
  }
}

function updateFullscreenStatus() {
  const inFullscreen = isFullscreen();
  
  // Handle fullscreen requirement stage
  if (fullscreenStatus) {
    if (inFullscreen) {
      fullscreenStatus.textContent = '✓ Fullscreen mode active - Starting test...';
      fullscreenStatus.className = 'fullscreen-status success';
      // Auto-proceed to test after entering fullscreen
      setTimeout(() => {
        proceedToTest();
      }, 1000);
    } else {
      fullscreenStatus.textContent = 'Please enter fullscreen mode to continue';
      fullscreenStatus.className = 'fullscreen-status error';
    }
  }

  // Handle during test
  if (isTestActive) {
    if (inFullscreen) {
      hideFullscreenWarning();
    } else {
      showFullscreenWarning();
    }
  }
}

btnEnterFullscreen?.addEventListener('click', async () => {
  try {
    await enterFullscreen();
    updateFullscreenStatus();
  } catch (err) {
    console.error('[Fullscreen] Error:', err);
    if (fullscreenStatus) {
      fullscreenStatus.textContent = '✗ Could not enter fullscreen. Please try F11 or try again.';
      fullscreenStatus.className = 'fullscreen-status error';
    }
  }
});

// Listen for fullscreen changes
document.addEventListener('fullscreenchange', updateFullscreenStatus);
document.addEventListener('webkitfullscreenchange', updateFullscreenStatus);
document.addEventListener('mozfullscreenchange', updateFullscreenStatus);
document.addEventListener('MSFullscreenChange', updateFullscreenStatus);

// Store the original acceptDevilChallenge logic
let pendingTestStart = null;

async function proceedToTest() {
  if (!pendingTestStart) return;
  
  const { autoSubject, autoTopics } = pendingTestStart;
  
  // Mark test as active to monitor fullscreen
  isTestActive = true;
  
  // Continue with the original test start logic
  if (autoSubject && autoTopics) {
    try {
      await postJSON(`/api/session/${sessionId}/meta`, {
        selected_subject: autoSubject,
        selected_topics: autoTopics,
      });
    } catch (_) {}

    startQuestionPrefetch(autoSubject, autoTopics);

    if (devilHint) devilHint.textContent = "Challenge accepted. Entering test arena...";
    StressTriggers.beginExamTimer();
    showStage("popups");

    await loadTestQuestions();

    try {
      const data = await postJSON(`/session/${sessionId}/start-simulation`, {});
      log("start_simulation", data);
      if (popupSummary) popupSummary.textContent = "Pressure simulation is live. Keep your focus.";
    } catch (err) {
      log("simulation_error", err.message || String(err));
      if (popupSummary) popupSummary.textContent = "Could not start popup simulation.";
    }
    StressTriggers.onPopupsEntered();
    pendingTestStart = null;
    return;
  }

  if (autoSubject && !autoTopics) {
    console.log("[proceedToTest] subject known, topics unknown → chapter screen");
    await window.academicTopics?.loadTopicsForSubject?.(autoSubject, sessionId);
    pendingTestStart = null;
    return;
  }

  console.log("[proceedToTest] no subject → subject screen");
  showStage("subjectSelection");
  await window.academicTopics?.initializeSubjectSelection?.(sessionId, null);
  pendingTestStart = null;
}

let _lifelines = 3;  // top-level lifeline counter (state.lifelines is inside the IIFE)

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeAnswerLabel(value) {
  return String(value || "").trim().toUpperCase();
}

function getPrimaryCorrectAnswer(q) {
  const answer = q?.correct_answer || q?.correct_answers;
  if (Array.isArray(answer) && answer.length) return normalizeAnswerLabel(answer[0]);
  if (typeof answer === "string") return normalizeAnswerLabel(answer);
  return "";
}

function renderResultStateForCurrentQuestion() {
  const q = testQuestions[testQuestionIndex];
  if (!q || (q.question_type || "").toLowerCase() !== "scq" || !questionOptions) return;
  const row = answeredMap[q.question_id];
  questionOptions.querySelectorAll("label.option").forEach((node) => {
    const mark = node.querySelector(".option-mark");
    node.classList.remove("option-result-correct", "option-result-wrong");
    if (mark) mark.textContent = "";
  });
  if (!row || !row.selected) return;
  const picked = normalizeAnswerLabel(row.selected);
  const correctLabel = normalizeAnswerLabel(row.correctLabel || getPrimaryCorrectAnswer(q));
  questionOptions.querySelectorAll("label.option").forEach((node) => {
    const input = node.querySelector("input[type=radio]");
    const mark = node.querySelector(".option-mark");
    const label = normalizeAnswerLabel(input?.value);
    if (!label) return;
    if (label === correctLabel) {
      node.classList.add("option-result-correct");
      if (mark) mark.textContent = "✓";
    } else if (label === picked && picked !== correctLabel) {
      node.classList.add("option-result-wrong");
      if (mark) mark.textContent = "✗";
    }
  });
}

function updateLifelineState() {
  if (!btnLifeline) return;
  const lifelineCount = Math.max(0, _lifelines);
  btnLifeline.textContent = `Lifelines: ${lifelineCount}`;
  
  // Add visual feedback when lifelines are lost
  if (lifelineCount === 0) {
    btnLifeline.classList.add('lifeline-lost');
  } else {
    btnLifeline.classList.remove('lifeline-lost');
  }
  
  const q = testQuestions[testQuestionIndex];
  if (lifelineCount <= 0 || !q || (q.question_type || "").toLowerCase() !== "scq" || answeredMap[q.question_id] || q.lifelineUsed) {
    btnLifeline.disabled = true;
  } else {
    btnLifeline.disabled = false;
  }
}

function showLifelineLostBanner() {
  const banner = document.createElement('div');
  banner.style.cssText = `
    position: fixed;
    top: 60px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10000;
    width: calc(100% - 40px);
    max-width: 440px;
    background: linear-gradient(135deg, rgba(120, 53, 15, 0.95), rgba(146, 64, 14, 0.95));
    border: 1px solid rgba(217, 119, 6, 0.4);
    border-radius: 12px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    animation: slideDown 0.3s ease;
  `;
  
  banner.innerHTML = `
    <div style="font-size: 24px;">💀</div>
    <div style="
      flex: 1;
      font-size: 15px;
      font-weight: 600;
      color: #FEF3C7;
      letter-spacing: 0.02em;
    ">All lifelines lost!</div>
  `;
  
  document.body.appendChild(banner);
  
  // Auto-remove after 2 seconds
  setTimeout(() => {
    banner.style.opacity = '0';
    banner.style.transform = 'translateX(-50%) translateY(-10px)';
    banner.style.transition = 'all 0.3s ease';
    setTimeout(() => banner.remove(), 300);
  }, 2000);
}

async function showTestEndScreen(timeUsedMs) {
  console.log('[showTestEndScreen] Called with timeUsedMs:', timeUsedMs);
  
  // Mark test as inactive IMMEDIATELY — this blocks all trigger activation
  isTestActive = false;
  hideFullscreenWarning();
  
  // Kill all triggers completely
  if (StressTriggers) {
    if (StressTriggers.deactivateAllTriggers) StressTriggers.deactivateAllTriggers();
    if (StressTriggers.stopExamTimer) StressTriggers.stopExamTimer();
  }
  
  // Cancel all pending trigger timeouts
  cancelPendingTriggers();
  
  // Remove any lingering trigger overlays/popups from the DOM
  document.querySelectorAll('.hard-question-fullscreen, .stress-timer-overlay, .phantom-competitor-bar, .stress-news-diversion, .stress-blackout, .stress-difficulty-check-overlay').forEach(el => el.remove());
  
  // Clean up body/shell classes from triggers
  document.body.classList.remove('stress-blur-attack', 'stress-color-inversion', 'stress-chaos-bg');
  const shell = document.querySelector('.app-shell');
  if (shell) {
    shell.classList.remove('stress-screen-flip', 'stress-wave-distortion', 'stress-heartbeat', 'stress-news-diversion-open');
    shell.style.transform = '';
    shell.style.filter = '';
  }
  
  // Keep fullscreen — don't exit when showing results
  
  // Calculate stats
  const totalQuestions = testQuestions.length;
  const answeredCount = Object.keys(answeredMap).length;
  const correctCount = Object.values(answeredMap).filter(a => a.correct).length;
  const percentage = answeredCount > 0 ? Math.round((correctCount / answeredCount) * 100) : 0;
  
  if (!timeUsedMs || timeUsedMs < 0 || timeUsedMs > 900000) timeUsedMs = 0;
  const minutes = Math.floor(timeUsedMs / 60000);
  const seconds = Math.floor((timeUsedMs % 60000) / 1000);
  const timeUsedStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  
  // Theme
  let level, ringColor, headline, verdict, ctaText;
  if (percentage <= 20) {
    level = "CRITICAL"; ringColor = "#ef4444"; headline = "Needs Attention"; verdict = "Focus broke down early. Identify the pattern and rebuild."; ctaText = "Try Again";
  } else if (percentage <= 50) {
    level = "BELOW PAR"; ringColor = "#f97316"; headline = "Room to Grow"; verdict = "Inconsistent under pressure. The gaps are fixable."; ctaText = "Go Again";
  } else if (percentage <= 75) {
    level = "AVERAGE"; ringColor = "#eab308"; headline = "Solid Base"; verdict = "Decent hold. One focused session away from the next tier."; ctaText = "Push Further";
  } else if (percentage <= 89) {
    level = "STRONG"; ringColor = "#22c55e"; headline = "Well Played"; verdict = "Held focus when it mattered. Keep compounding."; ctaText = "Continue";
  } else {
    level = "ELITE"; ringColor = "#06b6d4"; headline = "Exceptional"; verdict = "Peak execution under pressure. Rare territory."; ctaText = "Done";
  }

  // Switch to results stage — hides test UI completely
  showStage("results");
  
  const container = document.getElementById("resultsScreen");
  if (!container) return;
  
  // Background effects per level (intense glows reaching into the page)
  let bgEffectHTML = '';
  if (percentage <= 20) {
    bgEffectHTML = `
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 0% 50%,rgba(239,68,68,0.18) 0%,transparent 55%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 100% 50%,rgba(239,68,68,0.18) 0%,transparent 55%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 0%,rgba(239,68,68,0.1) 0%,transparent 40%);animation:resPulse 3s ease-in-out infinite;"></div>`;
  } else if (percentage <= 50) {
    bgEffectHTML = `
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 0% 70%,rgba(249,115,22,0.15) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 100% 30%,rgba(249,115,22,0.12) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 100%,rgba(249,115,22,0.1) 0%,transparent 45%);"></div>`;
  } else if (percentage <= 75) {
    bgEffectHTML = `
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 0% 30%,rgba(234,179,8,0.12) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 100% 70%,rgba(234,179,8,0.1) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 0%,rgba(234,179,8,0.08) 0%,transparent 40%);"></div>`;
  } else if (percentage <= 89) {
    bgEffectHTML = `
      <div style="position:absolute;inset:0;pointer-events:none;overflow:hidden;" id="resParticles"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 0% 50%,rgba(34,197,94,0.14) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 100% 50%,rgba(34,197,94,0.14) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 100%,rgba(34,197,94,0.08) 0%,transparent 40%);"></div>`;
  } else {
    bgEffectHTML = `
      <div style="position:absolute;inset:0;pointer-events:none;overflow:hidden;" id="resParticles"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 0% 40%,rgba(6,182,212,0.18) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 100% 60%,rgba(6,182,212,0.18) 0%,transparent 50%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 0%,rgba(6,182,212,0.12) 0%,transparent 45%);"></div>`;
  }
  
  container.style.background = "#000";
  container.innerHTML = `
    <style>
      @keyframes resPulse { 0%,100%{opacity:0.5;} 50%{opacity:1;} }
      @keyframes resFloat { 0%{transform:translateY(0) scale(1);opacity:0.6;} 50%{transform:translateY(-20px) scale(1.1);opacity:1;} 100%{transform:translateY(-40px) scale(0.8);opacity:0;} }
    </style>
    ${bgEffectHTML}
    <div style="
      position:relative;z-index:1;
      width:100%;max-width:440px;display:flex;flex-direction:column;align-items:center;
      padding:48px 20px 60px;opacity:0;transform:translateY(14px);
      transition:opacity 0.8s ease,transform 0.8s ease;
    " id="resInner">
      
      <div style="font-size:12px;letter-spacing:0.3em;text-transform:uppercase;color:rgba(255,255,255,0.3);font-weight:600;margin-bottom:44px;">SESSION COMPLETE</div>
      
      <!-- Ring -->
      <div style="position:relative;width:220px;height:220px;margin-bottom:40px;">
        <svg width="220" height="220" style="transform:rotate(-90deg);">
          <circle cx="110" cy="110" r="96" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="7"/>
          <circle cx="110" cy="110" r="96" fill="none" stroke="${ringColor}" stroke-width="7" stroke-linecap="round"
            stroke-dasharray="603" stroke-dashoffset="603"
            style="transition:stroke-dashoffset 2s cubic-bezier(0.4,0,0.15,1) 0.5s;"
            id="resRingFill"/>
        </svg>
        <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
          <span style="font-size:62px;font-weight:800;color:rgba(255,255,255,0.95);letter-spacing:-3px;line-height:1;" id="resPercentNum">0</span>
          <span style="font-size:15px;color:${ringColor};font-weight:600;margin-top:4px;opacity:0.85;">%</span>
        </div>
      </div>
      
      <!-- Level badge -->
      <div style="
        font-size:13px;letter-spacing:0.18em;text-transform:uppercase;
        color:${ringColor};font-weight:700;margin-bottom:14px;opacity:0.9;
      ">${level}</div>
      <div style="font-size:28px;font-weight:700;color:rgba(255,255,255,0.92);margin-bottom:10px;letter-spacing:-0.3px;">${headline}</div>
      <div style="font-size:16px;color:rgba(255,255,255,0.5);text-align:center;line-height:1.6;margin-bottom:44px;max-width:320px;">${verdict}</div>
      
      <!-- Stats -->
      <div style="width:100%;display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:rgba(255,255,255,0.06);border-radius:12px;overflow:hidden;margin-bottom:44px;">
        <div style="background:#0a0a0a;padding:24px 12px;text-align:center;">
          <div style="font-size:28px;font-weight:800;color:rgba(255,255,255,0.92);">${correctCount}<span style="font-size:15px;font-weight:500;color:rgba(255,255,255,0.35);">/${answeredCount}</span></div>
          <div style="font-size:11px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:0.12em;margin-top:8px;">Correct</div>
        </div>
        <div style="background:#0a0a0a;padding:24px 12px;text-align:center;">
          <div style="font-size:28px;font-weight:800;color:rgba(255,255,255,0.92);">${answeredCount}<span style="font-size:15px;font-weight:500;color:rgba(255,255,255,0.35);">/${totalQuestions}</span></div>
          <div style="font-size:11px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:0.12em;margin-top:8px;">Attempted</div>
        </div>
        <div style="background:#0a0a0a;padding:24px 12px;text-align:center;">
          <div style="font-size:28px;font-weight:800;color:rgba(255,255,255,0.92);">${timeUsedStr}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:0.12em;margin-top:8px;">Duration</div>
        </div>
      </div>
      
      <!-- CTA -->
      <button onclick="window.location.href='/'" style="
        width:100%;padding:18px;border:1px solid rgba(255,255,255,0.12);border-radius:10px;
        background:transparent;color:rgba(255,255,255,0.75);font-size:16px;font-weight:600;
        cursor:pointer;letter-spacing:0.03em;transition:all 0.2s;
      " onmouseover="this.style.background='rgba(255,255,255,0.06)';this.style.color='rgba(255,255,255,0.95)'" onmouseout="this.style.background='transparent';this.style.color='rgba(255,255,255,0.75)'">${ctaText}</button>
    </div>
  `;
  
  // Animate in
  requestAnimationFrame(() => {
    const inner = document.getElementById("resInner");
    if (inner) { inner.style.opacity = "1"; inner.style.transform = "translateY(0)"; }
    
    // Animate ring fill
    setTimeout(() => {
      const ring = document.getElementById("resRingFill");
      if (ring) ring.style.strokeDashoffset = String(603 - (603 * percentage / 100));
    }, 100);
    
    // Animate percentage counter
    let current = 0;
    const target = percentage;
    const numEl = document.getElementById("resPercentNum");
    if (numEl && target > 0) {
      const step = Math.max(1, Math.floor(target / 40));
      const interval = setInterval(() => {
        current += step;
        if (current >= target) { current = target; clearInterval(interval); }
        numEl.textContent = String(current);
      }, 30);
    }
    
    // Floating particles for good/excellent
    if (percentage > 75) {
      const particleContainer = document.getElementById("resParticles");
      if (particleContainer) {
        for (let i = 0; i < 12; i++) {
          const p = document.createElement("div");
          const size = Math.random() * 3 + 2;
          p.style.cssText = `
            position:absolute;bottom:0;
            left:${Math.random() * 100}%;
            width:${size}px;height:${size}px;
            background:${ringColor};border-radius:50%;opacity:0;
            animation:resFloat ${3 + Math.random() * 4}s ease-in-out ${Math.random() * 3}s infinite;
          `;
          particleContainer.appendChild(p);
        }
      }
    }
  });
  
  // Effects per level
  if (percentage <= 20) {
    // No celebration — just the pulsing vignette
  } else if (percentage <= 50) {
    // Subtle — no confetti
  } else if (percentage <= 75) {
    // Mild confetti
    setTimeout(() => createConfetti(30, ringColor), 1200);
  } else if (percentage <= 89) {
    // Good — confetti burst
    setTimeout(() => createConfetti(80, ringColor), 900);
  } else {
    // Elite — heavy confetti + delayed second wave
    setTimeout(() => createConfetti(100, ringColor), 700);
    setTimeout(() => createConfetti(60, '#FFD700'), 1800);
  }
  
  // Increment completed_sessions
  const user = window.StressDostAuth?.getUser();
  if (user && user.user_id) {
    try {
      const response = await fetch(`/api/user/${user.user_id}/session-complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      if (user && data.completed_sessions !== undefined) {
        user.completed_sessions = data.completed_sessions;
        window.StressDostAuth.setUser(user);
        syncUserUI();
      }
    } catch (err) {
      console.error('[showTestEndScreen] Failed to increment completed session:', err);
    }
  }
}

function createConfetti(count, baseColor) {
  const colors = [
    baseColor,
    '#FFD700', // Gold
    '#FF69B4', // Pink
    '#00CED1', // Cyan
    '#FF6347', // Tomato
    '#32CD32', // Lime
    '#FF1493', // Deep pink
    '#00FF7F'  // Spring green
  ];
  
  const shapes = ['circle', 'square', 'triangle'];
  
  for (let i = 0; i < count; i++) {
    const confetti = document.createElement('div');
    confetti.className = 'confetti';
    
    const shape = shapes[Math.floor(Math.random() * shapes.length)];
    const color = colors[Math.floor(Math.random() * colors.length)];
    const size = Math.random() * 8 + 6; // 6-14px
    const left = Math.random() * 100; // 0-100%
    const animationDuration = Math.random() * 2 + 3; // 3-5s
    const animationDelay = Math.random() * 0.5; // 0-0.5s stagger
    
    confetti.style.left = `${left}%`;
    confetti.style.width = `${size}px`;
    confetti.style.height = `${size}px`;
    confetti.style.backgroundColor = color;
    confetti.style.animation = `confettiFall ${animationDuration}s linear ${animationDelay}s forwards`;
    
    // Apply shape-specific styles
    if (shape === 'circle') {
      confetti.style.borderRadius = '50%';
    } else if (shape === 'triangle') {
      confetti.style.width = '0';
      confetti.style.height = '0';
      confetti.style.backgroundColor = 'transparent';
      confetti.style.borderLeft = `${size/2}px solid transparent`;
      confetti.style.borderRight = `${size/2}px solid transparent`;
      confetti.style.borderBottom = `${size}px solid ${color}`;
    }
    // square is default (no border-radius)
    
    document.body.appendChild(confetti);
    
    // Remove confetti after animation completes
    setTimeout(() => {
      confetti.remove();
    }, (animationDuration + animationDelay) * 1000);
  }
}

function openSolutionModal() {
  if (btnShowSolution?.hidden || btnShowSolution?.classList.contains("is-disabled")) return;
  const q = testQuestions[testQuestionIndex];
  if (!q || !solutionModal) return;
  const labelAnswer = getPrimaryCorrectAnswer(q);
  const integerAnswer =
    q.integer_answer !== undefined && q.integer_answer !== null ? String(q.integer_answer) : "";
  const answer = labelAnswer || integerAnswer || "Not available";
  if (solutionAnswerLine) solutionAnswerLine.textContent = `Correct answer: ${answer}`;
  if (solutionContent) {
    const solutionHtml = q.solution_html || "<p>Solution not available.</p>";
    if (window.AcadzaRender?.renderInto) {
      window.AcadzaRender.renderInto(solutionContent, solutionHtml);
    } else {
      solutionContent.innerHTML = processAcadzaHtml(solutionHtml);
    }
  }
  solutionModalOpen = true;
  solutionModal.hidden = false;
}

function closeSolutionModal() {
  if (solutionModal) solutionModal.hidden = true;
  if (solutionContent && window.AcadzaRender?.destroy) {
    window.AcadzaRender.destroy(solutionContent);
    solutionContent.textContent = "";
  }
  solutionModalOpen = false;
  if (pendingAdvanceAfterSubmit) {
    pendingAdvanceAfterSubmit = false;
    advanceAfterSubmit();
  }
}

btnLifeline?.addEventListener("click", () => {
  if (_lifelines <= 0) return;
  const q = testQuestions[testQuestionIndex];
  if (!q || (q.question_type || "").toLowerCase() !== "scq") return;
  if (q.lifelineUsed || answeredMap[q.question_id]) return;
  
  // Add temporary animation when using lifeline
  btnLifeline.style.transform = 'scale(0.95)';
  setTimeout(() => {
    btnLifeline.style.transform = 'scale(1)';
  }, 150);
  
  // Find incorrect options
  const correct = q.correct_answer || "A";
  const incorrects = (q.options || []).filter(o => o.label !== correct).map(o => o.label);
  
  // Pick 2 at random to hide
  const toHide = [];
  while(toHide.length < 2 && incorrects.length > 0) {
    const idx = Math.floor(Math.random() * incorrects.length);
    toHide.push(incorrects.splice(idx, 1)[0]);
  }
  
  // Hide them visually
  const inputs = questionOptions.querySelectorAll("input[type=radio]");
  inputs.forEach(input => {
    if (toHide.includes(input.value)) {
      input.closest("label").style.opacity = "0.3";
      input.closest("label").style.pointerEvents = "none";
    }
  });
  
  _lifelines--;
  q.lifelineUsed = true;
  updateLifelineState();
  
  // Show feedback
  setTestHint("Lifeline used! Two incorrect options removed.");
});
btnShowSolution?.addEventListener("click", openSolutionModal);
btnShowSolution?.addEventListener("keydown", (evt) => {
  if (evt.key === "Enter" || evt.key === " ") {
    evt.preventDefault();
    openSolutionModal();
  }
});
btnCloseSolution?.addEventListener("click", closeSolutionModal);
solutionModal?.addEventListener("click", (evt) => {
  if (evt.target === solutionModal) closeSolutionModal();
});

btnSubmitQuestion?.addEventListener("click", submitCurrentQuestion);
btnFinishTest?.addEventListener("click", () => finishTestWithConfirm());
btnReportError?.addEventListener("click", () => {
  setTestHint("Thanks - the report was captured.");
});
// Handle save button in subject selection
btnSaveQuestionSubject?.addEventListener("click", () => {
  btnSaveQuestionSubject.classList.toggle("is-saved");
  const isSaved = btnSaveQuestionSubject.classList.contains("is-saved");
  
  // Update emoji based on save state
  if (isSaved) {
    btnSaveQuestionSubject.textContent = "💎"; // Premium emoji for saved state
    setSubjectHint("Subject preference saved!");
  } else {
    btnSaveQuestionSubject.textContent = "🔖"; // Original emoji
    setSubjectHint("Save preference removed.");
  }
});

// Question header save button handler
btnSaveQuestionHeader?.addEventListener("click", () => {
  btnSaveQuestionHeader.classList.toggle("is-saved");
  const isSaved = btnSaveQuestionHeader.classList.contains("is-saved");
  
  // Update SVG fill based on save state
  const svg = btnSaveQuestionHeader.querySelector("svg");
  if (isSaved) {
    svg.setAttribute("fill", "currentColor"); // Filled when saved
    setTestHint("Question saved for review.");
  } else {
    svg.setAttribute("fill", "none"); // Outline when not saved
    setTestHint("Save removed.");
  }
});

// Original save button handler (for any remaining instances)
btnSaveQuestion?.addEventListener("click", () => {
  btnSaveQuestion.classList.toggle("is-saved");
  const isSaved = btnSaveQuestion.classList.contains("is-saved");
  
  // Update emoji based on save state
  if (isSaved) {
    btnSaveQuestion.textContent = "💎"; // Premium emoji for saved state
    setTestHint("Saved for review.");
  } else {
    btnSaveQuestion.textContent = "🔖"; // Original emoji
    setTestHint("Save removed.");
  }
});
btnZoomQuestion?.addEventListener("click", () => {
  const panel = document.querySelector(".question-panel");
  if (!panel) return;
  panel.classList.toggle("is-zoomed");
});

// Live suggestions for initial text — inline ghost-text autocomplete ------
// We use a simple approach: a readonly <textarea> clone sits behind the real one,
// showing the full merged text. The real textarea has a transparent background.
// Ghost tail is shown in a faded colour; accepted with Tab or →.

let currentGhostSuggestion = ""; // the full text that would result from accepting
let ghostSyncScheduled = false;

function getGhostTail(typedValue, fullSuggestion) {
  const typed = String(typedValue || "");
  const full  = String(fullSuggestion || "").trim();
  if (!full) return "";

  const typedLower = typed.toLowerCase();
  const fullLower  = full.toLowerCase();

  if (fullLower.startsWith(typedLower)) {
    return full.slice(typed.length); // continuation of what they typed
  }
  // Suggestion is a replacement / append — show whole thing after a space
  const trimmed = typed.trimEnd();
  return (trimmed ? " " : "") + full;
}

function renderGhost() {
  ghostSyncScheduled = false;
  const textarea = document.getElementById("initialText");
  const ghost    = document.getElementById("inlineSuggestGhost");
  const hint     = document.getElementById("inlineSuggestHint");
  if (!textarea || !ghost) return;

  if (!currentGhostSuggestion) {
    ghost.textContent = "";
    if (hint) hint.classList.remove("visible");
    return;
  }

  const tail = getGhostTail(textarea.value, currentGhostSuggestion);
  if (!tail) {
    ghost.textContent = "";
    if (hint) hint.classList.remove("visible");
    return;
  }

  // Copy exact computed styles from textarea so ghost aligns pixel-perfectly
  const cs = window.getComputedStyle(textarea);
  const props = [
    "padding","paddingTop","paddingRight","paddingBottom","paddingLeft",
    "fontSize","fontFamily","fontWeight","fontStyle","lineHeight",
    "letterSpacing","wordSpacing","textIndent","borderTopWidth",
    "borderRightWidth","borderBottomWidth","borderLeftWidth","boxSizing",
    "width","overflowX","overflowY","whiteSpace","wordWrap","wordBreak"
  ];
  props.forEach(p => { ghost.style[p] = cs[p]; });
  ghost.style.border       = "1px solid transparent"; // same box model, invisible border
  ghost.style.borderRadius = cs.borderRadius;
  ghost.style.background   = "transparent";
  ghost.style.color        = "transparent"; // typed part invisible
  ghost.style.position     = "absolute";
  ghost.style.top          = "0";
  ghost.style.left         = "0";
  ghost.style.height       = cs.height;
  ghost.style.pointerEvents = "none";
  ghost.style.zIndex       = "0";
  ghost.style.overflow     = "hidden";
  ghost.style.resize       = "none";
  ghost.style.whiteSpace   = "pre-wrap";

  // Build: invisible typed text + visible ghost tail
  ghost.innerHTML = "";
  const typedNode = document.createTextNode(textarea.value);
  const tailSpan  = document.createElement("span");
  tailSpan.style.cssText = "color: #9ca3af; font-style: normal;";
  tailSpan.textContent   = tail;
  ghost.appendChild(typedNode);
  ghost.appendChild(tailSpan);

  if (hint) {
    hint.textContent = "Tab";
    hint.classList.add("visible");
  }
}

function scheduleGhostRender() {
  if (!ghostSyncScheduled) {
    ghostSyncScheduled = true;
    requestAnimationFrame(renderGhost);
  }
}

function setSuggestions(items) {
  const input = document.getElementById("initialText");
  const list  = Array.isArray(items) ? items.filter(Boolean) : [];

  if (!list.length || !input) {
    currentGhostSuggestion = "";
    scheduleGhostRender();
    return;
  }

  // Take only the single best suggestion (first item)
  const best   = list[0];
  currentGhostSuggestion = mergeSuggestionText(input.value, best);
  scheduleGhostRender();
}

function clearGhost() {
  currentGhostSuggestion = "";
  scheduleGhostRender();
}

function applySuggestion(text) {
  const input = document.getElementById("initialText");
  if (!input) return;
  const suggestion = String(text || "").trim();
  if (!suggestion) return;
  // text is already the full merged value (typed + continuation)
  input.value = suggestion;
  input.selectionStart = input.selectionEnd = input.value.length;
  input.focus();
  currentGhostSuggestion = "";
  renderGhost(); // immediate, no rAF needed
}

function mergeSuggestionText(current, suggestion) {
  const base = String(current || "").trimEnd();
  const next = String(suggestion || "").trim();
  if (!base) return next;
  if (!next) return base;

  const baseLower = base.toLowerCase();
  const nextLower = next.toLowerCase();

  // If suggestion starts with what user typed, it's a full replacement (legacy)
  if (nextLower.startsWith(baseLower)) return next;

  // Otherwise it's a continuation — append with proper spacing
  const needsSpace = !base.endsWith(" ") && !next.startsWith(",") && !next.startsWith(".");
  return base + (needsSpace ? " " : "") + next;
}

function requestSuggestionsDebounced(rawText) {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(() => {
    const text = (rawText || "").trim();
    if (!text || text.length < 4) {
      clearGhost();
      return;
    }
    if (!socketInitialized) initSocket();
    if (socket) {
      socket.emit("suggest_request", { text });
    }
  }, 280);
}

(function attachInitialTextListeners() {
  const el = document.getElementById("initialText");
  if (!el) return;

  // Tab or → at end of line accepts the ghost
  el.addEventListener("keydown", (evt) => {
    if (!currentGhostSuggestion) return;
    const atEnd = el.selectionStart === el.value.length && el.selectionEnd === el.value.length;
    if ((evt.key === "Tab" || evt.key === "ArrowRight") && atEnd) {
      evt.preventDefault();
      applySuggestion(currentGhostSuggestion);
    } else if (evt.key === "Escape") {
      clearGhost();
    }
    // Don't clear on every other key — let the input event handle it
  });

  // On new input: clear ghost immediately, then request a fresh one
  el.addEventListener("input", (evt) => {
    currentGhostSuggestion = ""; // wipe without rAF so ghost doesn't flicker
    renderGhost();
    requestSuggestionsDebounced(evt.target.value);
  });

  // Clear ghost when focus leaves
  el.addEventListener("blur", () => clearGhost());
})();





function attachKeypadListeners() {
  if (integerKeypadListenerAttached) return;
  integerKeypadListenerAttached = true;
  const keypad = $("keypad");
  if (keypad) {
    keypad.addEventListener("click", (evt) => {
      const key = evt.target?.dataset?.key;
      if (!key) return;
      const q = testQuestions[testQuestionIndex];
      if (!q || (q.question_type || "").toLowerCase() !== "integer") return;
      const current = selectedOptions[q.question_id] || "";
      const next = current + key;
      selectedOptions[q.question_id] = next;
      if (integerInput) integerInput.value = next;
      updateTestSubmitButtonState();
    });
  }
  btnClearInteger?.addEventListener("click", () => {
    const q = testQuestions[testQuestionIndex];
    if (!q) return;
    selectedOptions[q.question_id] = "";
    if (integerInput) integerInput.value = "";
    updateTestSubmitButtonState();
  });
  btnBackspace?.addEventListener("click", () => {
    const q = testQuestions[testQuestionIndex];
    if (!q) return;
    const current = selectedOptions[q.question_id] || "";
    const next = current.slice(0, -1);
    selectedOptions[q.question_id] = next;
    if (integerInput) integerInput.value = next;
    updateTestSubmitButtonState();
  });
  integerInput?.addEventListener("input", (evt) => {
    const q = testQuestions[testQuestionIndex];
    if (!q) return;
    selectedOptions[q.question_id] = evt.target.value;
    updateTestSubmitButtonState();
  });
}

answerInput?.addEventListener("keydown", (evt) => {
  if (evt.key === "Enter" && (evt.metaKey || evt.ctrlKey)) {
    submitAnswer();
  }
});

answerInput?.addEventListener("input", updateAnswerButtonState);

function updateAnswerButtonState() {
  if (!btnAnswer || !answerInput) return;
  const hasText = Boolean(String(answerInput.value || "").trim());
  btnAnswer.disabled = !hasText;
  btnAnswer.hidden = !hasText;
}

// Init ---------------------------------------------------------------------
if (!window.StressDostAuth?.getUser?.()) {
  if (window.StressDostAuth?.redirectToLogin) {
    window.StressDostAuth.redirectToLogin();
  } else {
    window.location.replace("/login");
  }
} else {
  syncUserUI();
  
  // Show logout button, user name, and session counter if logged in
  const user = window.StressDostAuth?.getUser?.();
  console.log('[Init] User data for session counter:', user);
  if (user && user.display_name) {
    const userNameDisplay = document.getElementById('userNameDisplay');
    if (userNameDisplay) {
      userNameDisplay.textContent = user.display_name;
    }
    if (btnLogout) {
      btnLogout.style.display = 'block';
    }
    
    // Show session counter
    const sessionCounter = document.getElementById('sessionCounter');
    console.log('[Init] Session counter element:', sessionCounter);
    if (sessionCounter) {
      const completedSessions = user.completed_sessions || 0;
      console.log('[Init] Completed sessions:', completedSessions);
      sessionCounter.textContent = `Sessions: ${completedSessions}`;
      sessionCounter.style.setProperty('display', 'inline-block', 'important');
      console.log('[Init] Session counter display set to:', sessionCounter.style.display);
      console.log('[Init] Session counter computed display:', window.getComputedStyle(sessionCounter).display);
    } else {
      console.error('[Init] Session counter element not found!');
    }
  } else {
    console.log('[Init] No user or display_name, not showing session counter');
  }
  
  StressTriggers.attachGlobalListeners();
  // Dev panel removed for production
  resetFlow();
  initSocket();
  setRecordButtonState();
}

// expose for console debugging
window.__stressApp = {
  resetFlow,
  fetchNextQuestion,
  submitAnswer,
  loadTestQuestions,
  startQuestionPrefetch,
  submitCurrentQuestion,
  evaluateUserState: StressTriggers.evaluateUserState,
  activateTrigger: (name, context = {}) =>
    StressTriggers.activateTrigger(name, { force: true, manual: true, ...context }),
  activateTriggerManual: (name) =>
    StressTriggers.activateTrigger(name, { force: true, manual: true }),
  activateNarrativeTriggerManual: (name) =>
    StressTriggers.activateManualShowcaseTrigger(name, { force: true, manual: true }),
  deactivateTrigger: StressTriggers.deactivateTrigger,
  getUserId: () => window.StressDostAuth?.getUserId?.() ?? null,
  buildDevilBriefPage,
  showStage,
  setPendingTestStart: (params) => {
    pendingTestStart = params;
  },
};
