
(function () {
  const SUPABASE_URL =
    "https://sxdrqithncjdrokwpkzm.supabase.co";

  const SUPABASE_PUBLISHABLE_KEY =
    "sb_publishable_BWbgsxATJy14BXXL-A3RHw_kTUwFRi9";

  if (!window.supabase?.createClient) {
    console.error("Supabase library failed to load.");
    return;
  }

  window.ddaSupabase = window.supabase.createClient(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY,
    {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true
      }
    }
  );

  window.ddaCloudReady = true;
})();
