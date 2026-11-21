const OWNER = "amar0612";
const REPO = "dear-draw-cloud-monitor";
const WORKFLOW = "archive-official-sources.yml";
const API = "https://api.github.com";

function response(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" }
  });
}

async function github(path, token, init = {}) {
  const res = await fetch(API + path, {
    ...init,
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "DearDrawCloudRecovery",
      ...(init.headers || {})
    }
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub API ${res.status}: ${text.slice(0, 500)}`);
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

async function dispatch(env, source) {
  if (!env.GITHUB_TOKEN) throw new Error("Missing GITHUB_TOKEN Worker secret");

  // Do not enqueue duplicate campaign runs while an earlier batch is active or queued.
  const path = `/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10`;
  const [running, queued] = await Promise.all([
    github(path + "&status=in_progress", env.GITHUB_TOKEN),
    github(path + "&status=queued", env.GITHUB_TOKEN)
  ]);
  const activeRuns = [
    ...(running.body?.workflow_runs || []),
    ...(queued.body?.workflow_runs || [])
  ];
  if (activeRuns.length) {
    const run = activeRuns[0];
    console.log("RECOVERY_DISPATCH_SKIPPED", JSON.stringify({
      reason: "workflow_already_active",
      run_id: run.id,
      status: run.status,
      html_url: run.html_url
    }));
    return { dispatched: false, reason: "workflow_already_active", run_id: run.id };
  }

  await github(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    env.GITHUB_TOKEN,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref: "main",
        inputs: { batch_size: "25", max_batches: "1" }
      })
    }
  );
  console.log("RECOVERY_DISPATCHED", JSON.stringify({ source, batch_size: 25, max_batches: 1 }));
  return { dispatched: true, batch_size: 25, max_batches: 1 };
}

export default {
  async scheduled(controller, env) {
    if (env.HISTORICAL_CRON_ENABLED !== "true") {
      console.log("HISTORICAL_CRON_PAUSED: set HISTORICAL_CRON_ENABLED=true after migration test");
      return;
    }
    try {
      await dispatch(env, "cloudflare_cron");
    } catch (error) {
      console.error("HISTORICAL_DISPATCH_FAILED", String(error));
      throw error;
    }
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "GET") return response({ error: "Method not allowed" }, 405);

    if (url.pathname === "/health") {
      return response({
        worker: "dear-draw-historical-dispatcher",
        status: "online",
        scheduler: env.HISTORICAL_CRON_ENABLED === "true" ? "enabled" : "paused",
        schedule_utc: "12,27,42,57 * * * *",
        batch_size: 25,
        max_batches_per_run: 1,
        checkpoint_store: "Cloudflare R2 via existing GitHub recovery controller",
        execution_engine: "GitHub Actions Python/PDF pipeline"
      });
    }

    // Read-only credential check: verifies access to the target workflow without dispatching it.
    if (url.pathname === "/validate") {
      if (!env.GITHUB_TOKEN) return response({ ok: false, error: "GITHUB_TOKEN secret is missing" }, 503);
      try {
        const result = await github(
          `/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`,
          env.GITHUB_TOKEN
        );
        return response({
          ok: true,
          credential: "accepted",
          repository: `${OWNER}/${REPO}`,
          workflow: result.body?.path || WORKFLOW,
          workflow_state: result.body?.state || "unknown",
          dispatch_test: "not performed",
          recovery_started: false
        });
      } catch (error) {
        console.error("GITHUB_CREDENTIAL_VALIDATION_FAILED", String(error));
        return response({
          ok: false,
          credential: "not validated",
          error: String(error).slice(0, 300),
          recovery_started: false
        }, 502);
      }
    }

    return response({ error: "Not found" }, 404);
  }
};
