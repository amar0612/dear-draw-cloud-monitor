
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
      #dda-account {
        position:fixed; bottom:12px; right:12px;
        z-index:9998; padding:10px 14px;
        border-radius:30px; background:#0f1b29;
        color:white; border:1px solid #334155;
      }
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
      say("Signing in…");
      try {
        await auth.signIn(email.value.trim(), password.value);
      } catch (err) {
        say(err.message || "Sign-in failed.", true);
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

    const account = document.createElement("button");
    account.id = "dda-account";
    account.textContent = "Account · Sign out";
    account.hidden = true;
    account.onclick = async () => {
      if (confirm("Sign out?")) {
        try {
          await auth.signOut();
        } catch (err) {
          alert(err.message);
        }
      }
    };
    document.body.appendChild(account);

    function update(session) {
      gate.hidden = !!session;
      account.hidden = !session;
    }

    auth.getSession().then(update).catch(err => say(err.message, true));
    auth.onAuthChange((_event, session) => update(session));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
