(function () {
  var form = document.getElementById("loginForm");
  var hint = document.getElementById("loginHint");
  var loginStage = document.getElementById("loginStage");
  var welcomeStage = document.getElementById("welcomeStage");
  var btnGuest = document.getElementById("btnGuest");

  if (!form || !window.StressDostAuth) return;

  if (window.StressDostAuth.getUser()) {
    window.location.replace("/");
    return;
  }

  var MOOD_MESSAGES = {
    overwhelmed: "Let's untangle what's on your plate.",
    anxious: "Take a breath — we'll work through it together.",
    scattered: "Let's get you focused, one thing at a time.",
    "burned-out": "You've got this. Small steps from here.",
    "just-checking": "Good to see you. Ready when you are.",
    "": "Ready to vent? The session is all yours.",
  };

  function showWelcome(name, moodKey) {
    var mood = moodKey || "";
    var heading = document.getElementById("welcomeHeading");
    var msg = document.getElementById("welcomeMessage");
    if (heading) heading.textContent = name ? "Hey, " + name : "Hey there";
    if (msg) msg.textContent = MOOD_MESSAGES[mood] || MOOD_MESSAGES[""];
    if (loginStage) {
      loginStage.classList.remove("is-active");
      loginStage.hidden = true;
    }
    if (welcomeStage) {
      welcomeStage.hidden = false;
      welcomeStage.classList.add("is-active");
    }
  }

  function persistMood(mood) {
    try {
      if (mood) localStorage.setItem("sd_mood", mood);
      else localStorage.removeItem("sd_mood");
    } catch (_) {}
  }

  function submitProfile(opts) {
    opts = opts || {};
    if (hint) hint.textContent = "";
    var display_name = opts.display_name != null ? opts.display_name : (document.getElementById("displayName") || {}).value || "";
    var user_id = opts.user_id != null ? opts.user_id : (document.getElementById("userId") || {}).value || "";
    var mood = opts.mood != null ? opts.mood : (document.getElementById("mood") || {}).value || "";
    
    // If user entered a name, check if they have a profile
    if (display_name && display_name.trim()) {
      console.log('[Login] Checking profile for:', display_name.trim());
      fetch("/api/user/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: display_name.trim() })
      })
      .then(res => res.json())
      .then(data => {
        console.log('[Login] API response:', data);
        if (data.error) {
          if (hint) hint.textContent = data.error;
          return;
        }
        
        // Store user profile data
        try {
          window.StressDostAuth.setUser({
            user_id: data.user_id,
            display_name: data.name,
            mood: mood,
            total_sessions: data.total_sessions,
            completed_sessions: data.completed_sessions,
            is_new_user: data.is_new_user
          });
          persistMood(mood);
          
          // Show welcome message with session count for returning users
          var welcomeMsg = data.is_new_user 
            ? MOOD_MESSAGES[mood] || MOOD_MESSAGES[""]
            : "Welcome back! You've completed " + data.completed_sessions + " session" + (data.completed_sessions === 1 ? "" : "s") + ".";
          
          console.log('[Login] Welcome message:', welcomeMsg);
          console.log('[Login] is_new_user:', data.is_new_user, 'total_sessions:', data.total_sessions);
          
          var heading = document.getElementById("welcomeHeading");
          var msg = document.getElementById("welcomeMessage");
          if (heading) heading.textContent = "Hey, " + data.name;
          if (msg) msg.textContent = welcomeMsg;
          
          if (loginStage) {
            loginStage.classList.remove("is-active");
            loginStage.hidden = true;
          }
          if (welcomeStage) {
            welcomeStage.hidden = false;
            welcomeStage.classList.add("is-active");
          }
        } catch (err) {
          console.error('[Login] Error:', err);
          if (hint) hint.textContent = err.message || "Could not continue.";
        }
      })
      .catch(err => {
        console.error('[Login] Network error:', err);
        if (hint) hint.textContent = "Network error. Please try again.";
        console.error("Login error:", err);
      });
    } else {
      // Guest mode - no profile
      try {
        window.StressDostAuth.setUser({
          user_id: user_id,
          display_name: display_name,
          mood: mood,
        });
        persistMood(mood);
        var trimmedName = String(display_name || "").trim();
        showWelcome(trimmedName || "", mood);
      } catch (err) {
        if (hint) hint.textContent = err.message || "Could not continue.";
      }
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submitProfile({});
  });

  if (btnGuest) {
    btnGuest.addEventListener("click", function () {
      var dn = document.getElementById("displayName");
      var uid = document.getElementById("userId");
      var moodEl = document.getElementById("mood");
      if (dn) dn.value = "";
      if (uid) uid.value = "";
      if (moodEl) moodEl.value = "";
      submitProfile({ display_name: "", user_id: "", mood: "" });
    });
  }
})();
