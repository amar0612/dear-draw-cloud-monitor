/**
 * Cloudflare scheduled poller for Nagaland Dear 1PM / 8PM results.
 * Polls once per minute only in the configured IST windows.
 * Secrets required: SAMBAD_API_TOKEN, SUPABASE_SECRET_KEY.
 */
const API_URL = "https://api.sambad.com/v2/dear/result";
const SUPABASE_URL = "https://sxdrqithncjdrokwpkzm.supabase.co";
const EXPECTED = { "1st": 1, "Consolation": 1, "2nd": 10, "3rd": 10, "4th": 10, "5th": 100 };
const PATTERNS = {
  "1st": /^[0-9]{2}[A-Z] [0-9]{5}$/,
  "Consolation": /^[0-9]{5}$/,
  "2nd": /^[0-9]{5}$/,
  "3rd": /^[0-9]{4}$/,
  "4th": /^[0-9]{4}$/,
  "5th": /^[0-9]{4}$/
};
const TIER_MAP = { cons: "Consolation", consolation: "Consolation", "2nd": "2nd", "3rd": "3rd", "4th": "4th", "5th": "5th" };

function istParts(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  }).formatToParts(date);
  return Object.fromEntries(parts.filter(p => p.type !== "literal").map(p => [p.type, p.value]));
}
function targetDraw(parts) {
  const h = Number(parts.hour), m = Number(parts.minute);
  if ((h === 12 && m >= 55) || (h === 13 && m <= 35)) return "1pm";
  if ((h === 19 && m >= 55) || h === 20 || h === 21 || (h === 22 && m <= 5)) return "8pm";
  return null;
}
function validate(record) {
  const errors = [];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(record.date)) errors.push("invalid date");
  if (!["1PM", "8PM"].includes(record.draw)) errors.push("invalid draw");
  for (const [tier, count] of Object.entries(EXPECTED)) {
    const values = record.prizes?.[tier];
    if (!Array.isArray(values) || values.length !== count) {
      errors.push(`${tier}: expected ${count}, got ${Array.isArray(values) ? values.length : "missing"}`);
      continue;
    }
    values.forEach((v, i) => { if (typeof v !== "string" || !PATTERNS[tier].test(v)) errors.push(`${tier} entry ${i + 1} has invalid format`); });
  }
  if (errors.length === 0 && record.prizes["1st"][0].slice(-5) !== record.prizes.Consolation[0]) {
    errors.push("consolation does not match last five digits of 1st prize");
  }
  return errors;
}
async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${body.slice(0, 500)}`);
  return body ? JSON.parse(body) : [];
}
async function fetchAndNormalize(draw, date, token) {
  const [y, mo, d] = date.split("-");
  const params = new URLSearchParams({ date: `${d}-${mo}-${y}`, slot: draw, "access-token": token });
  const payload = await getJson(`${API_URL}?${params}`, { headers: { "User-Agent": "DearDrawAnalyzer/1.0" } });
  if (payload.success !== true || !payload.data || payload.data.status !== "published") {
    throw new Error(`not published (API status: ${payload.data?.status ?? "unknown"})`);
  }
  const data = payload.data;
  if (data.lottery !== "dear" || data.slot !== draw) throw new Error("wrong lottery or draw slot returned");
  const [ay, am, ad] = (data.date || "").split("-").reverse();
  if (`${ay}-${am}-${ad}` !== date) throw new Error("API returned a different draw date");
  if (!data.first || !String(data.first.series || "").trim() || !String(data.first.number || "").trim()) throw new Error("incomplete first prize");
  const prizes = { "1st": [`${String(data.first.series).trim()} ${String(data.first.number).trim()}`], "Consolation": [], "2nd": [], "3rd": [], "4th": [], "5th": [] };
  if (!Array.isArray(data.prizes)) throw new Error("missing API prize list");
  for (const prize of data.prizes) {
    const tier = TIER_MAP[String(prize.tier || "").trim().toLowerCase()];
    if (!tier) continue;
    const expectedMatch = tier === "3rd" || tier === "4th" || tier === "5th" ? "last4" : "number";
    if (prize.match !== expectedMatch) throw new Error(`unexpected matching rule for ${tier}`);
    if (!Array.isArray(prize.numbers)) throw new Error(`${tier} numbers missing`);
    prizes[tier].push(...prize.numbers.map(v => String(v).trim()));
  }
  const record = {
    date, draw: draw === "1pm" ? "1PM" : "8PM", prizes,
    source: "Lottery Sambad API v2",
    verification_status: "API_IMPORTED_NOT_GAZETTE_VERIFIED"
  };
  const errors = validate(record);
  if (errors.length) throw new Error("validation failed: " + errors.join("; "));
  return record;
}
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])]));
  }
  return value;
}
function comparable(row) {
  return JSON.stringify(stable({
    draw_date: row.draw_date, draw_slot: row.draw_slot, prizes: row.prizes,
    source: row.source, verification_status: row.verification_status
  }));
}
async function syncSupabase(record, key) {
  const slot = record.draw;
  const filter = new URLSearchParams({
    select: "id,draw_date,draw_slot,prizes,source,verification_status",
    draw_date: `eq.${record.date}`, draw_slot: `eq.${slot}`
  });
  const base = SUPABASE_URL + "/rest/v1/draws";
  const headers = { apikey: key, Authorization: `Bearer ${key}`, Accept: "application/json", "Content-Type": "application/json" };
  const existing = await getJson(`${base}?${filter}`, { headers });
  const row = {
    id: crypto.randomUUID(), draw_date: record.date, draw_slot: slot,
    prizes: record.prizes, source: record.source,
    verification_status: record.verification_status
  };
  if (existing.length) {
    if (existing.length === 1 && comparable(existing[0]) === comparable(row)) {
      console.log("ALREADY SYNCED", record.date, slot); return "already_synced";
    }
    throw new Error(`CONFLICT: ${record.date} ${slot} already exists with different data; not overwritten`);
  }
  const inserted = await getJson(`${base}?on_conflict=draw_date,draw_slot`, {
    method: "POST", headers: { ...headers, Prefer: "resolution=ignore-duplicates,return=representation" },
    body: JSON.stringify(row)
  });
  if (inserted.length) { console.log("SYNCED", record.date, slot); return "synced"; }
  const raced = await getJson(`${base}?${filter}`, { headers });
  if (raced.length === 1 && comparable(raced[0]) === comparable(row)) return "already_synced";
  throw new Error("insert returned no row; possible concurrent conflict");
}

export default {
  async scheduled(controller, env) {
    const now = new Date();
    const p = istParts(now);
    const draw = targetDraw(p);
    if (!draw) return;
    const date = `${p.year}-${p.month}-${p.day}`;
    if (!env.SAMBAD_API_TOKEN || !env.SUPABASE_SECRET_KEY) throw new Error("Worker secrets are not configured");
    try {
      const record = await fetchAndNormalize(draw, date, env.SAMBAD_API_TOKEN);
      await syncSupabase(record, env.SUPABASE_SECRET_KEY);
    } catch (error) {
      console.log("POLL", date, draw, "not complete:", String(error));
      // A not-yet-published result is expected during the polling window.
      // Cron will try again next minute; no partial record is written.
    }
  },
  async fetch() {
    return new Response("Dear Draw Cloud Poller is running. Scheduled polling is enabled.", {
      headers: { "content-type": "text/plain; charset=utf-8" }
    });
  }
};
