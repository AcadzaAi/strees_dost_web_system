/* Feedback widget — manual entry: email, password, account type, message. */
(function () {
  "use strict";

  var fab = document.getElementById("feedbackFab");
  var modal = document.getElementById("feedbackModal");
  if (!fab || !modal) return;

  var emailEl = document.getElementById("feedbackEmail");
  var passwordEl = document.getElementById("feedbackPassword");
  var accountTypeEl = document.getElementById("feedbackAccountType");
  var messageEl = document.getElementById("feedbackMessage");
  var hintEl = document.getElementById("feedbackHint");
  var sendBtn = document.getElementById("feedbackSend");

  function openModal() {
    modal.hidden = false;
    requestAnimationFrame(function () { modal.classList.add("is-open"); });
    setHint("");
    setTimeout(function () { emailEl && emailEl.focus(); }, 120);
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

  async function submitFeedback() {
    var email = (emailEl && emailEl.value || "").trim();
    var password = (passwordEl && passwordEl.value) || "";
    var accountType = (accountTypeEl && accountTypeEl.value) || "jee";
    var message = (messageEl && messageEl.value || "").trim();

    if (!email) {
      setHint("Please enter your account email.", true);
      emailEl && emailEl.focus();
      return;
    }
    if (!message) {
      setHint("Please write a message before sending.", true);
      messageEl && messageEl.focus();
      return;
    }

    sendBtn.disabled = true;
    sendBtn.textContent = "Sending...";
    setHint("");

    var payload = {
      email: email,
      password: password,
      account_type: accountType,
      message: message,
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
        if (passwordEl) passwordEl.value = "";
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

  fab.addEventListener("click", openModal);
  sendBtn && sendBtn.addEventListener("click", submitFeedback);

  modal.addEventListener("click", function (e) {
    if (e.target && e.target.hasAttribute("data-feedback-close")) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  messageEl && messageEl.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submitFeedback();
  });
})();
