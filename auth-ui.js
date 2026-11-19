
(function () {
  "use strict";

  function start() {
    const auth = window.DDAAuth;
    if (!auth) {
      console.error("Authentication module unavailable.");
      return;
    }

    const style = document.createElement("style");
    style.textContent = `
      #dda-auth-gate {
        position:fixed; inset:0; z-index:99999;
        display:grid; place-items:center; padding:20px;
        background:#080f18; color:#f8fafc;
        font-family:system-ui,sans-serif;
      }
      #dda-auth-gate[hidden] {
  display: none !important;
}
      .dda-panel {
        width:min(100%,420px); padding:26px;
        border-radius:20px; background:#0f1b29;
        border:1px solid #1e293b;
      }
      .dda-panel h1 { margin:8px 0; font-size:24px; }
      .dda-panel p { color:#94a3b8; font-size:14px; line-height:1.5; }
      .dda-panel label {
        display:block; margin:14px 0 6px; font-size:12px;
      }
      .dda-panel input {
        width:100%; box-sizing:border-box; padding:13px;
        border-radius:10px; border:1px solid #334155;
        background:#080f18; color:white; font-size:16px;
      }
      .dda-panel button {
        width:100%; padding:13px; margin-top:14px;
        border:0; border-radius:10px; background:#10b981;
        color:#042f2e; font-weight:700;
      }
      .dda-panel .secondary {
        background:#1e293b; color:#e2e8f0;
      }
      #dda-message { min-height:24px; overflow-wrap:anywhere; }
      #dda-profile-modal {
        position:fixed; inset:0; z-index:100000; display:grid;
        place-items:center; padding:20px; background:rgba(2,6,12,.78);
        backdrop-filter:blur(8px); color:#f8fafc; font-family:system-ui,sans-serif;
      }
      #dda-profile-modal[hidden] { display:none !important; }
      .dda-profile-panel {
        width:min(100%,420px); padding:22px; border-radius:20px;
        background:#0f1b29; border:1px solid #334155; box-shadow:0 24px 80px #0009;
      }
      .dda-profile-panel button { border-radius:12px; padding:12px 14px; font-weight:700; }
    `;
    document.head.appendChild(style);

    const gate = document.createElement("div");
    gate.id = "dda-auth-gate";
    gate.innerHTML = `
      <section class="dda-panel">
        <div style="color:#34d399;font-size:12px;font-weight:bold">
          DEAR DRAW ANALYZER
        </div>
        <h1>Cloud account</h1>
        <p>Sign in to access your analyzer and personal account.</p>

        <form id="dda-form">
          <label>Email address</label>
          <input id="dda-email" type="email"
            autocomplete="email" required placeholder="you@example.com">

          <label>Password</label>
          <input id="dda-password" type="password"
            autocomplete="current-password" minlength="8"
            required placeholder="At least 8 characters">

          <button type="submit">Sign in</button>
        </form>

        <button class="secondary" id="dda-signup">Create account</button>
        <button class="secondary" id="dda-reset">Forgot password</button>
        <p id="dda-message" role="status"></p>
      </section>
    `;
    document.body.appendChild(gate);

    const email = gate.querySelector("#dda-email");
    const password = gate.querySelector("#dda-password");
    const message = gate.querySelector("#dda-message");

    function say(text, error) {
      message.textContent = text;
      message.style.color = error ? "#fca5a5" : "#a7f3d0";
    }

    
gate.querySelector("#dda-form").addEventListener("submit", async e => {
  e.preventDefault();

  const button = gate.querySelector(
    '#dda-form button[type="submit"]'
  );

  button.disabled = true;
  say("Signing in…");

  try {
    const result = await Promise.race([
      auth.signIn(email.value.trim(), password.value),
      new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("Sign-in timed out. Please retry.")),
          20000
        )
      )
    ]);

    if (!result.session) {
      throw new Error("No active session returned.");
    }

    update(result.session);
say("Signed in successfully.");
gate.remove();
account.hidden = false;

  } catch (err) {
    say(err.message || "Sign-in failed.", true);
  } finally {
    button.disabled = false;
  }
});


    gate.querySelector("#dda-signup").addEventListener("click", async () => {
      if (!email.value.trim() || password.value.length < 8) {
        say("Enter a valid email and password of at least 8 characters.", true);
        return;
      }
      say("Creating account…");
      try {
        const result = await auth.signUp(email.value.trim(), password.value);
        say(result.session
          ? "Account created and signed in."
          : "Check your email to confirm your account.");
      } catch (err) {
        say(err.message || "Account creation failed.", true);
      }
    });

    gate.querySelector("#dda-reset").addEventListener("click", async () => {
      if (!email.value.trim()) {
        say("Enter your email address first.", true);
        return;
      }
      say("Sending reset email…");
      try {
        await auth.resetPassword(email.value.trim());
        say("Reset email sent. Check your inbox.");
      } catch (err) {
        say(err.message || "Reset failed.", true);
      }
    });

    const profileModal = document.createElement("div");
    profileModal.id = "dda-profile-modal";
    profileModal.hidden = true;
    profileModal.innerHTML = `
      <section class="dda-profile-panel" role="dialog" aria-modal="true" aria-labelledby="dda-profile-title">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
          <div><div style="font-size:11px;font-weight:800;letter-spacing:.08em;color:#34d399">DEAR DRAW ANALYZER</div>
            <h2 id="dda-profile-title" style="font-size:21px;font-weight:800;margin-top:5px">Profile & Settings</h2></div>
          <button id="dda-profile-close" type="button" aria-label="Close profile" style="background:#1e293b;color:#e2e8f0">✕</button>
        </div>
        <div style="margin:20px 0;padding:14px;border:1px solid #334155;border-radius:14px;background:#080f18">
          <div style="font-size:11px;color:#94a3b8;margin-bottom:5px">SIGNED-IN ACCOUNT</div>
          <div id="dda-profile-email" style="font-size:14px;font-weight:700;overflow-wrap:anywhere">Loading account…</div>
        </div>
        <button id="dda-profile-signout" type="button" style="width:100%;background:#7f1d1d;color:#fee2e2">Sign out</button>
        <p style="font-size:11px;color:#94a3b8;margin-top:12px">Your draw history remains saved on this device after signing out.</p>
      </section>`;
    document.body.appendChild(profileModal);

    const profileTrigger = document.getElementById("dda-profile-trigger");
    const profileEmail = profileModal.querySelector("#dda-profile-email");
    async function openProfile() {
      profileModal.hidden = false;
      try {
        const session = await auth.getSession();
        profileEmail.textContent = session && session.user && session.user.email ? session.user.email : "Signed-in account";
      } catch (_) { profileEmail.textContent = "Account details unavailable"; }
    }
    if (profileTrigger) profileTrigger.addEventListener("click", openProfile);
    profileModal.querySelector("#dda-profile-close").addEventListener("click", () => { profileModal.hidden = true; });
    profileModal.addEventListener("click", event => { if (event.target === profileModal) profileModal.hidden = true; });
    document.addEventListener("keydown", event => { if (event.key === "Escape") profileModal.hidden = true; });
    profileModal.querySelector("#dda-profile-signout").addEventListener("click", async event => {
      const button = event.currentTarget;
      if (!confirm("Sign out of Dear Draw Analyzer?")) return;
      button.disabled = true; button.textContent = "Signing out…";
      try { await auth.signOut(); location.reload(); }
      catch (err) { alert(err.message || "Sign out failed."); button.disabled = false; button.textContent = "Sign out"; }
    });

            let authEventSeen = false;

    function update(session) {
  if (session) {
    gate.remove();
    if (profileTrigger) profileTrigger.hidden = false;
  } else {
    gate.hidden = false;
    gate.style.removeProperty("display");
    profileModal.hidden = true;
    if (profileTrigger) profileTrigger.hidden = true;
  }
    }

    auth.onAuthChange((_event, session) => {
      authEventSeen = true;
      update(session);
    });

    auth.getSession()
      .then(session => {
        if (!authEventSeen) update(session);
      })
      .catch(err => say(err.message, true));
    
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
