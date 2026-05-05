import sys
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', errors='replace', closefd=False)

with open('Task_Efficiency_Dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# 1. Add const ZOHO_REASONS = {}; placeholder just before const RAW_EXCEL
#    refresh_from_metabase.py will overwrite this line each run
# ─────────────────────────────────────────────────────────────────────────────
OLD_RAW = 'const RAW_EXCEL = {'
NEW_RAW = 'const ZOHO_REASONS = {};\nconst RAW_EXCEL = {'
if OLD_RAW in content and 'const ZOHO_REASONS' not in content:
    content = content.replace(OLD_RAW, NEW_RAW, 1)
    print('Fix 1 OK: ZOHO_REASONS placeholder added before RAW_EXCEL')
elif 'const ZOHO_REASONS' in content:
    print('Fix 1 SKIP: ZOHO_REASONS already present')
else:
    print('WARN Fix 1: const RAW_EXCEL not found')

# ─────────────────────────────────────────────────────────────────────────────
# 2. Update fetchZohoReasons() to prefer baked-in data over Worker fetch
# ─────────────────────────────────────────────────────────────────────────────
OLD_FETCH = (
    'async function fetchZohoReasons(){\n'
    '  if(_zohoReasonsCache) return _zohoReasonsCache;\n'
    '  if(_zohoReasonsFetching) return {};\n'
    '  _zohoReasonsFetching = true;\n'
    '  try{\n'
    '    var resp = await fetch(window.WORKER_URL + \'/zoho-reasons\');\n'
    '    if(resp.ok) _zohoReasonsCache = await resp.json();\n'
    '    else _zohoReasonsCache = {};\n'
    '  }catch(e){ _zohoReasonsCache = {}; }\n'
    '  _zohoReasonsFetching = false;\n'
    '  return _zohoReasonsCache;\n'
    '}'
)
NEW_FETCH = (
    'async function fetchZohoReasons(){\n'
    '  // Prefer data baked in at refresh time (no extra network call)\n'
    '  if(typeof ZOHO_REASONS!==\'undefined\'&&Object.keys(ZOHO_REASONS).length)\n'
    '    return ZOHO_REASONS;\n'
    '  if(_zohoReasonsCache) return _zohoReasonsCache;\n'
    '  if(_zohoReasonsFetching) return {};\n'
    '  _zohoReasonsFetching = true;\n'
    '  try{\n'
    '    var resp = await fetch(window.WORKER_URL + \'/zoho-reasons\');\n'
    '    if(resp.ok) _zohoReasonsCache = await resp.json();\n'
    '    else _zohoReasonsCache = {};\n'
    '  }catch(e){ _zohoReasonsCache = {}; }\n'
    '  _zohoReasonsFetching = false;\n'
    '  return _zohoReasonsCache;\n'
    '}'
)
if OLD_FETCH in content:
    content = content.replace(OLD_FETCH, NEW_FETCH, 1)
    print('Fix 2 OK: fetchZohoReasons() updated to prefer baked-in ZOHO_REASONS')
else:
    print('WARN Fix 2: fetchZohoReasons() exact match not found')

with open('Task_Efficiency_Dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
