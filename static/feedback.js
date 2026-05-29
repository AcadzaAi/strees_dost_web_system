/* Feedback widget — collects user + device details and submits to /api/feedback/submit */
(function () {
  "use strict";

  var fab = document.getElementById("feedbackFab");
  var modal = document.getElementById("feedbackModal");
  if (!fab || !modal) return;

  var categoryEl = document.getElementById("feedbackCategory");
  var messageEl = document.getElementById("feedbackMessage");
  var hintEl = document.getElementById("feedbackHint");
  var sendBtn = document.getElementById("feedbackSend");

  function openModal() {
    modal.hidden = false;
    requestAnimationFrame(function () { modal.classList.add("is-open"); });
    setHint("");
    setTimeout(function () { messageEl && messageEl.focus(); }, 120);
  }

  function closeModal() {
    modal.classList.remove("is-open");
    setTimeout(function () { modal.hidden = true; }, 220);
  }

  function setHint(text, isError) {
    if (!hintEl) return;
    hintEl.textContent = text || "";
    hintEl.classList.toggle("is-error", !!isError);
    hintEl.classList.toggle("is-success", !!text && !isError);
  }

  function detectDeviceType() {
    var ua = navigator.userAgent || "";
    if (/Mobi|Android|iPhone|iPod/i.test(ua)) return "Mobile";
    if (/iPad|Tablet/i.test(ua)) return "Tablet";
    return "Desktop";
  }

  function collectDevice() {
    var tz = "";
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) {}
    return {
      device_type: detectDeviceType(),
      platform: navigator.platform || "",
      user_agent: navigator.userAgent || "",
      screen: (window.screen ? (window.screen.width + "x" + window.screen.height) : ""),
      viewport: (window.innerWidth + "x" + window.innerHeight),
      language: navigator.language || "",
      timezone: tz,
      page_url: window.location.href || "",
    };
  }

  function collectUser() {
    var u = (window.StressDostAuth && window.StressDostAuth.getUser && window.StressDostAuth.getUser()) || null;
    if (!u) {
      return {
        user_id: "",
        display_name: "Guest (not logged in)",
        account_type: "guest",
        total_sessions: 0,
        completed_sessions: 0,
        mood: "",
        logged_in_at: "",
      };
    }
    var accountType = "registered";
    if ((u.completed_sessions || 0) === 0) accountType = "new_user";
    else if ((u.completed_sessions || 0) >= 5) accountType = "returning_user";
    return {
      user_id: u.user_id || "",
      display_name: u.display_name || "Guest",
      account_type: accountType,
      total_sessions: u.total_sessions || 0,
      completed_sessions: u.completed_sessions || 0,
      mood: u.mood || "",
      logged_in_at: u.logged_in_at || "",
    };
  }

  async function submitFeedback() {
    var message = (messageEl && messageEl.value || "").trim();
    if (!message) {
      setHint("Please write a message before sending.", true);
      messageEl && messageEl.focus();
      return;
    }

    sendBtn.disabled = true;
    sendBtn.textContent = "Sending...";
    setHint("");

    var payload = {
      message: message,
      category: (categoryEl && categoryEl.value) || "General",
      user: collectUser(),
      device: collectDevice(),
    };

    try {
      var res = await fetch("/api/feedback/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var data = await res.json().catch(function () { return {}; });

      if (res.ok) {
        setHint(data.message || "Thanks! Your feedback was sent.", false);
        if (messageEl) messageEl.value = "";
        setTimeout(closeModal, 1400);
      } else if (res.status === 429) {
        setHint("You've sent feedback recently. Please try again in a bit.", true);
      } else {
        setHint(data.error || "Could not send feedback. Please try again.", true);
      }
    } catch (err) {
      setHint("Network error. Check your connection and try again.", true);
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = "Send";
    }
  }

  // Event wiring
  fab.addEventListener("click", openModal);
  sendBtn && sendBtn.addEventListener("click", submitFeedback);

  modal.addEventListener("click", function (e) {
    if (e.target && e.target.hasAttribute("data-feedback-close")) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  // Ctrl/Cmd + Enter to send while typing
  messageEl && messageEl.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submitFeedback();
  });
})();
