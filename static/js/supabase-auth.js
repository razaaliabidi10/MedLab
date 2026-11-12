/**
 * static/js/supabase-auth.js
 * ==========================
 * Client-side integration for Supabase Auth in MedLab.
 * Uses @supabase/supabase-js (loaded from jsDelivr pinned version).
 *
 * Responsibilities:
 * 1. Attaches to existing "Continue with Google" button on login and signup.
 * 2. Initiates signInWithOAuth({ provider: 'google' }).
 * 3. Handles callback resolution on /auth/callback and posts verified JWT to Flask.
 * 4. Manages "Resend Verification Email" with 60s cooldown timer on /auth/verify-email.
 * 5. Calls supabase.auth.signOut({ scope: 'local' }) so Flask-Login remains the sole session.
 */

(function () {
  "use strict";

  function getClient() {
    if (!window.supabase || !window.MEDLAB_SUPABASE_CONFIG) {
      return null;
    }
    const { url, key } = window.MEDLAB_SUPABASE_CONFIG;
    if (!url || !key) {
      return null;
    }
    if (!window._medlabSupabaseClient) {
      window._medlabSupabaseClient = window.supabase.createClient(url, key, {
        auth: {
          persistSession: true,
          autoRefreshToken: false,
          detectSessionInUrl: true,
          flowType: "pkce"
        }
      });
    }
    return window._medlabSupabaseClient;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 1. Google Sign-In Buttons on Login & Signup Pages
  // ───────────────────────────────────────────────────────────────────────────
  async function performGoogleSignIn(btn) {
    const client = getClient();
    if (!client) {
      alert("Google sign-in is not configured yet. Please check back shortly.");
      return;
    }

    const callbackUrl = window.MEDLAB_SUPABASE_CONFIG?.callbackUrl || 
      `${window.location.origin}/auth/callback`;

    // Visual loading feedback
    let originalContent = "";
    if (btn) {
      originalContent = btn.innerHTML;
      btn.style.pointerEvents = "none";
      btn.style.opacity = "0.7";
    }

    try {
      const { data, error } = await client.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: callbackUrl
        }
      });

      if (error) {
        console.error("Supabase OAuth error:", error);
        alert("Unable to initialize Google Sign-In: " + error.message);
        if (btn) {
          btn.innerHTML = originalContent;
          btn.style.pointerEvents = "auto";
          btn.style.opacity = "1";
        }
      }
    } catch (err) {
      console.error("Sign in exception:", err);
      alert("Sign in failed. Please try again.");
      if (btn) {
        btn.innerHTML = originalContent;
        btn.style.pointerEvents = "auto";
        btn.style.opacity = "1";
      }
    }
  }

  window.medlabGoogleSignIn = performGoogleSignIn;

  function initGoogleButtons() {
    const googleBtns = document.querySelectorAll(
      "#google-signin-btn, a[href*='google_redirect'], a[href*='/auth/google'], [data-action='google-signin']"
    );

    googleBtns.forEach((btn) => {
      // Avoid binding twice
      if (btn.dataset.supabaseBound) return;
      btn.dataset.supabaseBound = "true";

      btn.addEventListener("click", function (e) {
        e.preventDefault();
        performGoogleSignIn(btn);
      });
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 2. Callback Processing on /auth/callback
  // ───────────────────────────────────────────────────────────────────────────
  async function processCallback() {
    const callbackContainer = document.getElementById("supabase-callback-container");
    if (!callbackContainer) return;

    const statusMsg = document.getElementById("callback-status-text");
    const errorBox = document.getElementById("callback-error-box");
    const errorText = document.getElementById("callback-error-text");

    const client = getClient();
    if (!client) {
      showError("Authentication configuration is missing. Please contact support.");
      return;
    }

    function showError(msg) {
      if (statusMsg) statusMsg.style.display = "none";
      if (errorBox) errorBox.classList.remove("hidden");
      if (errorText) errorText.textContent = msg;
    }

    try {
      // Allow supabase-js to process URL fragment or PKCE code
      const { data: { session }, error } = await client.auth.getSession();

      if (error) {
        showError(error.message || "Failed to retrieve authentication session.");
        return;
      }

      if (!session || !session.access_token) {
        // Wait briefly for onAuthStateChange if getSession hasn't caught the hash yet
        const { data: authListener } = client.auth.onAuthStateChange(async (event, currentSession) => {
          if (currentSession && currentSession.access_token) {
            authListener.subscription.unsubscribe();
            await sendTokenToFlask(currentSession.access_token, client);
          }
        });

        // Timeout fallback after 8 seconds
        setTimeout(() => {
          if (!session) {
            showError("Authentication session timed out or was invalid. Please try signing in again.");
          }
        }, 8000);
        return;
      }

      await sendTokenToFlask(session.access_token, client);
    } catch (err) {
      console.error("Callback exception:", err);
      showError("An unexpected error occurred during authentication.");
    }
  }

  async function sendTokenToFlask(accessToken, client) {
    const csrfToken = window.MEDLAB_SUPABASE_CONFIG?.csrfToken || "";
    const statusMsg = document.getElementById("callback-status-text");

    if (statusMsg) {
      statusMsg.textContent = "Verifying security credentials with server...";
    }

    try {
      const response = await fetch("/auth/supabase-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken
        },
        body: JSON.stringify({ access_token: accessToken })
      });

      const result = await response.json();

      // Sign out of client-side Supabase session so Flask-Login remains sole session
      try {
        await client.auth.signOut({ scope: "local" });
      } catch (e) {
        // Ignored
      }

      if (result.success && result.redirect_url) {
        window.location.href = result.redirect_url;
      } else {
        const errorBox = document.getElementById("callback-error-box");
        const errorText = document.getElementById("callback-error-text");
        if (statusMsg) statusMsg.style.display = "none";
        if (errorBox) errorBox.classList.remove("hidden");
        if (errorText) errorText.textContent = result.error || "Authentication rejected.";
      }
    } catch (fetchErr) {
      console.error("Server verification error:", fetchErr);
      const errorBox = document.getElementById("callback-error-box");
      const errorText = document.getElementById("callback-error-text");
      if (statusMsg) statusMsg.style.display = "none";
      if (errorBox) errorBox.classList.remove("hidden");
      if (errorText) errorText.textContent = "Connection failed while contacting server.";
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 3. Email Verification Page & Resend Cooldown
  // ───────────────────────────────────────────────────────────────────────────
  function initEmailVerification() {
    const resendBtn = document.getElementById("resend-otp-btn");
    if (!resendBtn) return;

    const email = resendBtn.getAttribute("data-email");
    const statusText = document.getElementById("resend-status");
    let cooldownRemaining = 0;
    let timer = null;

    resendBtn.addEventListener("click", async function (e) {
      e.preventDefault();
      if (cooldownRemaining > 0) return;

      const client = getClient();
      if (!client) {
        alert("Authentication client not initialized.");
        return;
      }

      const callbackUrl = window.MEDLAB_SUPABASE_CONFIG.callbackUrl || 
        `${window.location.origin}/auth/callback`;

      resendBtn.disabled = true;
      resendBtn.classList.add("opacity-50", "cursor-not-allowed");
      if (statusText) statusText.textContent = "Sending email...";

      try {
        const { error } = await client.auth.signInWithOtp({
          email: email,
          options: {
            emailRedirectTo: callbackUrl,
            shouldCreateUser: true
          }
        });

        if (error) {
          if (statusText) statusText.textContent = `Error: ${error.message}`;
          resendBtn.disabled = false;
          resendBtn.classList.remove("opacity-50", "cursor-not-allowed");
        } else {
          if (statusText) statusText.textContent = "Verification email dispatched! Please check your inbox.";
          startCooldown(60);
        }
      } catch (err) {
        if (statusText) statusText.textContent = "Failed to dispatch email. Please retry in a moment.";
        resendBtn.disabled = false;
        resendBtn.classList.remove("opacity-50", "cursor-not-allowed");
      }
    });

    function startCooldown(seconds) {
      cooldownRemaining = seconds;
      resendBtn.disabled = true;
      resendBtn.classList.add("opacity-50", "cursor-not-allowed");

      if (timer) clearInterval(timer);
      timer = setInterval(() => {
        cooldownRemaining--;
        if (cooldownRemaining <= 0) {
          clearInterval(timer);
          resendBtn.disabled = false;
          resendBtn.classList.remove("opacity-50", "cursor-not-allowed");
          resendBtn.textContent = "Resend Verification Email";
        } else {
          resendBtn.textContent = `Resend available in ${cooldownRemaining}s`;
        }
      }, 1000);
    }
  }

  // Auto-init on DOMContentLoaded
  document.addEventListener("DOMContentLoaded", function () {
    initGoogleButtons();
    processCallback();
    initEmailVerification();
  });
})();
