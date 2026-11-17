
/* Dear Draw Analyzer — Supabase Authentication */

(function () {
  "use strict";

  function getClient() {
    if (!window.ddaSupabase) {
      throw new Error("Cloud connection is not ready.");
    }
    return window.ddaSupabase;
  }

  function getRedirectURL() {
    return window.location.origin + window.location.pathname;
  }

  window.DDAAuth = {

    // Create a new account
    async signUp(email, password) {
      const { data, error } = await getClient().auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: getRedirectURL()
        }
      });

      if (error) throw error;
      return data;
    },

    // Sign in to an existing account
    async signIn(email, password) {
      const { data, error } = await getClient().auth
        .signInWithPassword({
          email: email.trim(),
          password
        });

      if (error) throw error;
      return data;
    },

    // Sign out
    async signOut() {
      const { error } = await getClient().auth.signOut();
      if (error) throw error;
    },

    // Send password reset email
    async resetPassword(email) {
      const { error } = await getClient().auth
        .resetPasswordForEmail(email.trim(), {
          redirectTo: getRedirectURL()
        });

      if (error) throw error;
    },

    // Get current session
    async getSession() {
      const { data, error } = await getClient().auth
        .getSession();

      if (error) throw error;
      return data.session;
    },

    // Listen for login/logout changes
    onAuthChange(callback) {
      return getClient().auth.onAuthStateChange(
        (event, session) => callback(event, session)
      );
    }
  };

  console.log("Dear Draw Analyzer authentication module loaded.");
})();
