// ========================================================================
// Question-Level Triggers - Using EXISTING Beautiful CSS Classes
// ========================================================================

// Q1 → SPOTLIGHT_HUNT
function triggerSpotlightHunt() {
  if (!questionBody) return null;
  
  const spotlight = document.createElement('div');
  spotlight.className = 'stress-spotlight-overlay';
  
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
    durationMs: 0,
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
  
  // Step 1: Beautiful rating popup using existing classes
  const overlay = document.createElement('div');
  overlay.className = 'stress-difficulty-check-overlay';
  overlay.innerHTML = `
    <div class="stress-difficulty-check-card">
      <div class="stress-difficulty-check-emoji">🤔</div>
      <div class="stress-difficulty-check-title">Rate Previous Question</div>
      <div class="stress-difficulty-check-sub">How difficult was it for you?</div>
      <div class="stress-difficulty-check-options" style="grid-template-columns: repeat(3, 1fr);">
        <button class="stress-difficulty-check-option easy">
          <div class="stress-difficulty-check-emoji">😊</div>
          <div style="font-size: 18px; font-weight: 700;">Easy</div>
        </button>
        <button class="stress-difficulty-check-option medium">
          <div class="stress-difficulty-check-emoji">😐</div>
          <div style="font-size: 18px; font-weight: 700;">Medium</div>
        </button>
        <button class="stress-difficulty-check-option" style="border-color: rgba(255, 99, 132, 0.72); color: #ff6384;">
          <div class="stress-difficulty-check-emoji">😰</div>
          <div style="font-size: 18px; font-weight: 700;">Hard</div>
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  
  const continueSequence = () => {
    overlay.remove();
    
    timers.push(setTimeout(() => {
      // Warning popup
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
        warningOverlay.remove();
        
        // Countdown timer
        stressCountdown = document.createElement('div');
        stressCountdown.className = 'trigger-countdown';
        document.body.appendChild(stressCountdown);
        
        let timeLeft = 30;
        stressCountdown.textContent = `⏱️ ${timeLeft}s`;
        
        const countdownInterval = setInterval(() => {
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
    btn.addEventListener('click', continueSequence);
  });
  
  return {
    durationMs: 0,
    cleanup: () => {
      timers.forEach(t => clearTimeout(t));
      overlay.remove();
      if (fogElement) fogElement.remove();
      if (stressCountdown) stressCountdown.remove();
    },
  };
}

// Q3 → FLIP_CYCLE
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
      setTimeout(doFlip, 5000);
    }
  };
  
  doFlip();
  
  return {
    durationMs: 0,
    cleanup: () => {
      // Leave final flip state
    },
  };
}

// Q4 → ACCURACY_TEST
function triggerAccuracyTest() {
  if (!questionBody) return null;
  
  const timers = [];
  let shakeInterval = null;
  
  // Intro popup
  const overlay = document.createElement('div');
  overlay.className = 'stress-difficulty-check-overlay';
  overlay.innerHTML = `
    <div class="stress-difficulty-check-card">
      <div class="stress-difficulty-check-emoji">⚠️</div>
      <div class="stress-difficulty-check-title">Accuracy Challenge</div>
      <div class="stress-difficulty-check-sub">Can you read through a shaking screen?</div>
      <div class="binary-actions">
        <button class="binary-btn" id="accuracy-yes" style="background: rgba(26, 215, 181, 0.15); border-color: rgba(26, 215, 181, 0.5); color: #28d8af; font-size: 18px; font-weight: 700; padding: 16px; border-radius: 12px; cursor: pointer; border: 1px solid; transition: all 140ms ease;">
          Yes, I can
        </button>
        <button class="binary-btn" id="accuracy-no" style="background: rgba(255, 99, 132, 0.15); border-color: rgba(255, 99, 132, 0.5); color: #ff6384; font-size: 18px; font-weight: 700; padding: 16px; border-radius: 12px; cursor: pointer; border: 1px solid; transition: all 140ms ease;">
          No, skip it
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  
  const applyTimePenalty = () => {
    if (state.questionStartedAt) {
      state.questionStartedAt -= 10000;
    }
  };
  
  const showRoast = (message, callback) => {
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
      if (callback) callback();
    }, 4500);
  };
  
  document.getElementById('accuracy-yes').addEventListener('click', () => {
    overlay.remove();
    
    const shell = getAppShell();
    if (shell) {
      let shakeTime = 0;
      shakeInterval = setInterval(() => {
        const x = (Math.random() - 0.5) * 10;
        const y = (Math.random() - 0.5) * 10;
        shell.style.transform = `translate(${x}px, ${y}px)`;
        shakeTime += 100;
        
        if (shakeTime >= 60000) {
          clearInterval(shakeInterval);
          shell.style.transform = '';
          
          const postOverlay = document.createElement('div');
          postOverlay.className = 'stress-difficulty-check-overlay';
          postOverlay.innerHTML = `
            <div class="stress-difficulty-check-card">
              <div class="stress-difficulty-check-title">Could you read it?</div>
              <div class="binary-actions">
                <button class="binary-btn" id="post-yes">Yes, I could</button>
                <button class="binary-btn" id="post-no">No, I couldn't</button>
              </div>
            </div>
          `;
          document.body.appendChild(postOverlay);
          
          document.getElementById('post-yes').addEventListener('click', () => {
            postOverlay.remove();
            const explainOverlay = document.createElement('div');
            explainOverlay.className = 'stress-difficulty-check-overlay';
            explainOverlay.innerHTML = `
              <div class="stress-difficulty-check-card">
                <div class="stress-difficulty-check-title">Impressive! Explain how:</div>
                <textarea class="trigger-textarea" placeholder="Type your explanation..."></textarea>
                <button class="binary-btn" id="explain-submit" style="width: 100%;">Submit</button>
              </div>
            `;
            document.body.appendChild(explainOverlay);
            
            document.getElementById('explain-submit').addEventListener('click', () => {
              explainOverlay.remove();
            });
          });
          
          document.getElementById('post-no').addEventListener('click', () => {
            postOverlay.remove();
            showRoast("Honesty appreciated. But you still get a time penalty! 😈", applyTimePenalty);
          });
        }
      }, 100);
    }
  });
  
  document.getElementById('accuracy-no').addEventListener('click', () => {
    overlay.remove();
    showRoast("Smart choice to decline. But you still pay the price! ⏱️", applyTimePenalty);
  });
  
  return {
    durationMs: 0,
    cleanup: () => {
      timers.forEach(t => clearTimeout(t));
      if (shakeInterval) clearInterval(shakeInterval);
      overlay.remove();
      const shell = getAppShell();
      if (shell) shell.style.transform = '';
    },
  };
}

// Q5 → READING_TEST
function triggerReadingTest() {
  if (!questionBody) return null;
  
  const timers = [];
  
  // Pointing finger
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
              <button class="binary-btn" id="reading-giveup" style="background: rgba(160, 190, 255, 0.1); border-color: rgba(160, 190, 255, 0.3);">I gave up</button>
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
  let interceptionCount = 0;
  const maxInterceptions = 2;
  
  // Same beautiful pre-sequence as Q2
  const overlay = document.createElement('div');
  overlay.className = 'stress-difficulty-check-overlay';
  overlay.innerHTML = `
    <div class="stress-difficulty-check-card">
      <div class="stress-difficulty-check-emoji">🤔</div>
      <div class="stress-difficulty-check-title">Rate Previous Question</div>
      <div class="stress-difficulty-check-sub">How difficult was it for you?</div>
      <div class="stress-difficulty-check-options" style="grid-template-columns: repeat(3, 1fr);">
        <button class="stress-difficulty-check-option easy">
          <div class="stress-difficulty-check-emoji">😊</div>
          <div style="font-size: 18px; font-weight: 700;">Easy</div>
        </button>
        <button class="stress-difficulty-check-option medium">
          <div class="stress-difficulty-check-emoji">😐</div>
          <div style="font-size: 18px; font-weight: 700;">Medium</div>
        </button>
        <button class="stress-difficulty-check-option" style="border-color: rgba(255, 99, 132, 0.72); color: #ff6384;">
          <div class="stress-difficulty-check-emoji">😰</div>
          <div style="font-size: 18px; font-weight: 700;">Hard</div>
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  
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
        
        const countdownInterval = setInterval(() => {
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
    btn.addEventListener('click', continueSequence);
  });
  
  // Submission interception
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
  
  // Pre-roast
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
      
      card.style.position = 'fixed';
      card.style.width = '600px';
      card.style.transform = 'scale(0.5)';
      card.style.transformOrigin = 'top left';
      card.style.zIndex = '9999';
      card.style.transition = 'none';
      
      const cardWidth = 300;
      const cardHeight = 250;
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
