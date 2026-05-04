// ================================================================
// Cityfurnish Ops Dashboard — refresh proxy
//
// Sits between the dashboard page and GitHub. The page POSTs here when
// someone clicks "Refresh Now"; this Worker uses a stored GitHub PAT to
// trigger the workflow, then proxies status polls back to the page.
//
// The PAT lives only here (as a Wrangler/dashboard secret named GITHUB_PAT)
// and is never exposed to the browser.
//
// Deploy via Cloudflare dashboard:
//   1. Workers & Pages → Create → Worker → "Hello World"
//   2. Replace the boilerplate with this file's contents → Deploy
//   3. Open the deployed Worker → Settings → Variables and Secrets
//   4. Add a Secret named  GITHUB_PAT  with your fine-grained PAT value
//   5. Copy the Worker URL (looks like https://<name>.<account>.workers.dev)
// ================================================================

const ALLOWED_ORIGIN = 'https://adityakumarcf.github.io';
const GITHUB_OWNER   = 'adityakumarCF';
const GITHUB_REPO    = 'cityfurnish-ops-dashboard';
const GITHUB_WORKFLOW = 'scheduled-refresh.yml';

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (!env.GITHUB_PAT) {
      return jsonResponse({ error: 'Worker missing GITHUB_PAT secret' }, 500);
    }

    // Trigger workflow
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

    // Poll for run status; expects ?since=<unix-ms> to ignore older runs
    if (request.method === 'GET') {
      const since = parseInt(new URL(request.url).searchParams.get('since') || '0', 10);
      const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/runs?event=workflow_dispatch&per_page=5`;
      const r = await fetch(url, { headers: githubHeaders(env) });
      if (!r.ok) return jsonResponse({ error: `GitHub ${r.status}` }, 502);
      const data = await r.json();
      const ours = (data.workflow_runs || []).find(x => new Date(x.created_at).getTime() >= since);
      if (!ours) return jsonResponse({ status: 'pending' });
      return jsonResponse({
        status: ours.status,
        conclusion: ours.conclusion,
        html_url: ours.html_url,
      });
    }

    return jsonResponse({ error: 'Method not allowed' }, 405);
  },
};

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
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
  });
}
