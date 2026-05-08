// ================================================================
// Cityfurnish Ops Dashboard — refresh proxy + Zoho reschedule reasons
//
// Routes:
//   POST /                → trigger GitHub workflow dispatch (Refresh Now button)
//   GET  /                → poll GitHub workflow run status
//   POST /zoho-webhook    → receive Zoho Desk reschedule webhook, store in KV
//   GET  /zoho-reasons    → return all stored reschedule reasons (dashboard reads this)
//
// Secrets (Cloudflare Worker → Settings → Variables and Secrets):
//   GITHUB_PAT           — fine-grained GitHub PAT (already set)
//   ZOHO_WEBHOOK_SECRET  — any random string; paste the same value into Zoho webhook config
//
// KV Binding (Cloudflare Worker → Settings → KV Namespace Bindings):
//   Variable name: RESCH_KV   →   Namespace: RESCH_REASONS  (create this KV namespace first)
// ================================================================

const ALLOWED_ORIGIN  = 'https://adityakumarcf.github.io';
const GITHUB_OWNER    = 'adityakumarCF';
const GITHUB_REPO     = 'cityfurnish-ops-dashboard';
const GITHUB_WORKFLOW = 'scheduled-refresh.yml';

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.replace(/\/+$/, '') || '/';

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    // ── Zoho webhook: receives reschedule events from Zoho Desk ──────────────
    if (path === '/zoho-webhook' && request.method === 'POST') {
      return handleZohoWebhook(request, env);
    }

    // ── Return all stored reschedule reasons to the dashboard ─────────────────
    if (path === '/zoho-reasons' && request.method === 'GET') {
      return handleGetReasons(env);
    }

    // ── Existing: GitHub workflow dispatch / status poll ──────────────────────
    if (!env.GITHUB_PAT) {
      return jsonResponse({ error: 'Worker missing GITHUB_PAT secret' }, 500);
    }

    if (request.method === 'POST') {
      const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`;
      const r = await fetch(url, {
        method: 'POST',
        headers: githubHeaders(env),
        body: JSON.stringify({ ref: 'main' }),
      });
      if (!r.ok) {
        const text = await r.text();
        return jsonResponse({ error: `GitHub ${r.status}`, detail: text.slice(0, 200) }, 502);
      }
      return jsonResponse({ ok: true, dispatched_at: Date.now() }, 202);
    }

    if (request.method === 'GET') {
      const since = parseInt(new URL(request.url).searchParams.get('since') || '0', 10);
      const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/runs?event=workflow_dispatch&per_page=5`;
      const r = await fetch(url, { headers: githubHeaders(env) });
      if (!r.ok) return jsonResponse({ error: `GitHub ${r.status}` }, 502);
      const data = await r.json();
      const ours = (data.workflow_runs || []).find(x => new Date(x.created_at).getTime() >= since);
      if (!ours) return jsonResponse({ status: 'pending' });
      return jsonResponse({ status: ours.status, conclusion: ours.conclusion, html_url: ours.html_url });
    }

    return jsonResponse({ error: 'Method not allowed' }, 405);
  },
};

// ── Zoho webhook handler ───────────────────────────────────────────────────────
async function handleZohoWebhook(request, env) {
  // Verify optional secret — set ZOHO_WEBHOOK_SECRET in Worker secrets
  // and put the same value in Zoho's webhook "authToken" or append ?secret=... to the URL
  if (env.ZOHO_WEBHOOK_SECRET) {
    const headerSecret = request.headers.get('X-Zoho-Webhook-Secret') || '';
    const querySecret  = new URL(request.url).searchParams.get('secret') || '';
    if (headerSecret !== env.ZOHO_WEBHOOK_SECRET && querySecret !== env.ZOHO_WEBHOOK_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }
  }

  let body;
  try { body = await request.json(); }
  catch { return new Response('Bad JSON', { status: 400 }); }

  // Zoho sends the full ticket object — pull what we need
  const ticketNumber = String(body.ticketNumber || '').trim();
  const caseId       = String(body.id || '').trim();
  const cf           = body.customFields || {};

  const reason    = (cf['Reschedule Reason'] || '').trim();
  const subReason = (cf['Pickup Sub Reason'] || '').trim();
  const city      = (cf['City'] || '').trim();

  if (!ticketNumber) return new Response('Missing ticketNumber', { status: 400 });
  if (!env.RESCH_KV) return new Response('KV not bound — add RESCH_KV binding in Cloudflare', { status: 500 });

  // Read → merge → write back
  const raw = await env.RESCH_KV.get('reasons_map');
  const map = raw ? JSON.parse(raw) : {};
  map[ticketNumber] = { reason, subReason, city, caseId, ts: Date.now() };
  await env.RESCH_KV.put('reasons_map', JSON.stringify(map));

  return jsonResponse({ ok: true, ticketNumber, reason });
}

// ── Serve reason map to the dashboard ────────────────────────────────────────
async function handleGetReasons(env) {
  if (!env.RESCH_KV) return jsonResponse({});   // graceful if KV not set up yet
  const raw = await env.RESCH_KV.get('reasons_map');
  return jsonResponse(raw ? JSON.parse(raw) : {});
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function githubHeaders(env) {
  return {
    'Authorization': `Bearer ${env.GITHUB_PAT}`,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
    'User-Agent': 'cityfurnish-dashboard-worker',
  };
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Zoho-Webhook-Secret',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
  });
}
