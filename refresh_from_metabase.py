#!/usr/bin/env python3
"""
Refresh the Task Efficiency Dashboard by running the trips data query as a native
MongoDB pipeline against Metabase's /api/dataset endpoint (bypasses card-level
permissions; only needs native-query access on database 6).

Reads:
  METABASE_URL           e.g. https://analytics.rentofurniture.com
  METABASE_API_KEY       Metabase API key (header: X-API-Key)
  METABASE_DATABASE_ID   Metabase database id for Delivery Tracker MongoDB (default: 6)
  DASHBOARD_HTML         path to Task_Efficiency_Dashboard.html (default: ./Task_Efficiency_Dashboard.html)
  REFRESH_FROM_YMD       earliest scheduledDate to fetch (default: 4 months ago, 1st)
  REFRESH_TO_YMD         exclusive upper bound on scheduledDate (default: tomorrow IST)

Writes:
  Updated DASHBOARD_HTML in place with fresh RAW_EXCEL / PROCESSED_EXCEL_FULL / EXCL_ROWS_FULL,
  refreshed MIN/MAX_YMD, calDates pinned to today − 1, and "Last updated" timestamp.

In CI: secrets are already injected by GitHub Actions.
"""
import os, sys, re, json, time
from datetime import datetime, timezone, timedelta, date
from urllib import request as urlreq, error as urlerr

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
METABASE_URL  = os.environ.get('METABASE_URL', '').rstrip('/')
API_KEY       = os.environ.get('METABASE_API_KEY', '')
DATABASE_ID   = int(os.environ.get('METABASE_DATABASE_ID', '6'))
HTML_PATH     = os.environ.get('DASHBOARD_HTML', 'Task_Efficiency_Dashboard.html')

# Zoho Desk OAuth credentials (optional — skip Zoho fetch if not set)
ZOHO_CLIENT_ID     = os.environ.get('ZOHO_CLIENT_ID', '')
ZOHO_CLIENT_SECRET = os.environ.get('ZOHO_CLIENT_SECRET', '')
ZOHO_REFRESH_TOKEN = os.environ.get('ZOHO_REFRESH_TOKEN', '')
ZOHO_ORG_ID        = os.environ.get('ZOHO_ORG_ID', '648392808')

if not METABASE_URL or not API_KEY:
    print('ERROR: METABASE_URL and METABASE_API_KEY env vars required', file=sys.stderr)
    sys.exit(1)

# IST timezone (UTC+5:30) — Trip Ops business runs on IST
IST = timezone(timedelta(hours=5, minutes=30))

DONE_STATUSES   = {'Pickup Done', 'Completed', 'Delivered'}
SR_PATTERN      = re.compile(r'repair|replace|upgrade|relocation|installation', re.IGNORECASE)
EXCL_JOB_TYPES  = {'PO Payment', 'Stock Transfer', 'Refurb Transfer'}

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def m_cat(jt):
    """Map Job Type → Category (Pickup / SR / Delivery)."""
    j = (jt or '').lower()
    if 'pickup' in j: return 'Pickup'
    if SR_PATTERN.search(j): return 'SR'
    return 'Delivery'

def to_ymd(v):
    """Normalize any date-ish value → 'YYYY-MM-DD' or empty string."""
    if v is None or v == '':
        return ''
    if isinstance(v, (datetime, date)):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', s)
    if m: return m.group(1)
    for fmt in ('%d/%m/%Y','%Y/%m/%d','%d-%m-%Y','%m/%d/%Y'):
        try: return datetime.strptime(s.split(' ')[0], fmt).strftime('%Y-%m-%d')
        except Exception: pass
    return s

def normalize_cell(v):
    if v is None: return None
    if isinstance(v, datetime): return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, date): return v.strftime('%Y-%m-%d')
    if isinstance(v, str): return v.strip()
    return v

def metabase_post(path, body=None, timeout=300):
    """POST to Metabase with API key. Returns parsed JSON."""
    url = f'{METABASE_URL}{path}'
    data = json.dumps(body or {}).encode('utf-8')
    req = urlreq.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('X-API-Key', API_KEY)
    try:
        with urlreq.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urlerr.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        print(f'ERROR: HTTP {e.code} from {url}\n{err_body}', file=sys.stderr)
        raise

# ─────────────────────────────────────────────────────────────
# Zoho Desk API helpers
# ─────────────────────────────────────────────────────────────
def zoho_access_token():
    """Exchange Zoho refresh token for a short-lived access token."""
    url = 'https://accounts.zoho.in/oauth/v2/token'
    params = (
        f'grant_type=refresh_token'
        f'&client_id={ZOHO_CLIENT_ID}'
        f'&client_secret={ZOHO_CLIENT_SECRET}'
        f'&refresh_token={ZOHO_REFRESH_TOKEN}'
    )
    req = urlreq.Request(url, data=params.encode('utf-8'), method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urlreq.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode('utf-8'))
    if 'access_token' not in resp:
        raise ValueError(f'Zoho token refresh failed: {resp}')
    return resp['access_token']

def fetch_zoho_reasons(case_ids):
    """Fetch reschedule reasons from Zoho Desk for the given Case IDs.
    Returns dict keyed by ticketNumber (short) → {reason, subReason, caseId}.
    Silently skips if Zoho credentials are not configured."""
    if not (ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET and ZOHO_REFRESH_TOKEN):
        print('[zoho] Credentials not set — skipping reschedule reasons', flush=True)
        return {}
    if not case_ids:
        return {}

    print(f'[zoho] Fetching reasons for {len(case_ids)} rescheduled tickets…', flush=True)
    try:
        token = zoho_access_token()
    except Exception as e:
        print(f'[zoho] Token refresh failed: {e}', flush=True)
        return {}

    headers = {
        'Authorization': f'Zoho-oauthtoken {token}',
        'orgId': ZOHO_ORG_ID,
    }
    reasons = {}
    for idx, case_id in enumerate(case_ids):
        url = f'https://desk.zoho.in/api/v1/tickets/{case_id}?include=customFields'
        req = urlreq.Request(url, headers=headers)
        try:
            with urlreq.urlopen(req, timeout=30) as r:
                ticket = json.loads(r.read().decode('utf-8'))
            cf = ticket.get('customFields') or {}
            tk_num = str(ticket.get('ticketNumber') or '').strip()
            if tk_num:
                reasons[tk_num] = {
                    'reason':     (cf.get('Reschedule Reason') or '').strip(),
                    'subReason':  (cf.get('Pickup Sub Reason') or cf.get('Pickup Reason') or '').strip(),
                    'caseId':     case_id,
                }
        except Exception as e:
            print(f'  [zoho] WARN ticket {case_id}: {e}', flush=True)
        if (idx + 1) % 20 == 0:
            print(f'  [zoho] {idx+1}/{len(case_ids)} done', flush=True)
        time.sleep(0.15)   # ~6-7 req/s, well within Zoho's 100 req/min limit

    print(f'[zoho] Done — got reasons for {len(reasons)} tickets', flush=True)
    return reasons

# ─────────────────────────────────────────────────────────────
# Build MongoDB native pipeline (mirrors saved card 280, with dynamic dates)
# ─────────────────────────────────────────────────────────────
today_ist = datetime.now(IST).date()

# Window: 4 calendar months back (1st of that month) → tomorrow (so today's data is included)
def _months_back_first(d, n):
    y, m = d.year, d.month - n
    while m <= 0: y -= 1; m += 12
    return date(y, m, 1)

date_from = os.environ.get('REFRESH_FROM_YMD') or _months_back_first(today_ist, 4).strftime('%Y-%m-%d')
date_to   = os.environ.get('REFRESH_TO_YMD')   or (today_ist + timedelta(days=1)).strftime('%Y-%m-%d')
print(f'[refresh] Date window: {date_from} (incl) → {date_to} (excl)', flush=True)

PIPELINE = [
    {"$sort": {"createdAt": -1}},
    {"$addFields": {"softDeleteExists": {"$ifNull": ["$softDelete", False]}}},
    {"$match": {"$expr": {"$cond": {
        "if":   {"$eq": ["$softDeleteExists", True]},
        "then": {"$eq": ["$softDelete", False]},
        "else": True,
    }}}},
    {"$match": {"scheduledDate": {
        "$gte": {"$date": f"{date_from}T00:00:00.000Z"},
        "$lt":  {"$date": f"{date_to}T00:00:00.000Z"},
    }}},
    {"$lookup": {"from": "deliveries", "localField": "deliveryId", "foreignField": "_id", "as": "delivery"}},
    {"$addFields": {"scheduledDateForMatch": {"$dateToString": {
        "format": "%d-%m-%Y",
        "date": {"$cond": {
            "if": {"$and": [
                {"$ne": ["$scheduledDate", None]},
                {"$ne": [{"$type": "$scheduledDate"}, "string"]},
            ]},
            "then": {"$toDate": "$scheduledDate"},
            "else": None,
        }}
    }}}},
    {"$lookup": {
        "from": "agenttrips",
        "let": {"id": {"$toObjectId": "$agentId"}, "newDate": "$scheduledDateForMatch"},
        "pipeline": [{"$match": {"$and": [
            {"$expr": {"$eq": ["$agentId", "$$id"]}},
            {"$expr": {"$eq": ["$date", "$$newDate"]}},
        ]}}],
        "as": "agentData",
    }},
    {"$unwind": {"path": "$agentData", "preserveNullAndEmptyArrays": True}},
    {"$addFields": {"loginTime": "$agentData.startLoginTime", "logoutTime": "$agentData.endTiLogouTime"}},
    {"$lookup": {"from": "users", "localField": "agentId", "foreignField": "_id", "as": "agent"}},
    {"$match": {"delivery.createdAt": {"$exists": True, "$ne": None}}},
    {"$project": {
        "_id": 0,
        "agentName":      {"$arrayElemAt": ["$agent.name", 0]},
        "transportId":    1,
        "doneDate":       1,
        "caseId":         {"$arrayElemAt": ["$delivery.caseId", 0]},
        "firstname":      {"$arrayElemAt": ["$delivery.firstName", 0]},
        "lastname":       {"$arrayElemAt": ["$delivery.lastName", 0]},
        "email":          {"$arrayElemAt": ["$delivery.email", 0]},
        "subCategory":    {"$arrayElemAt": ["$delivery.subCategory", 0]},
        "category":       {"$arrayElemAt": ["$delivery.category", 0]},
        "caseUrl":        {"$arrayElemAt": ["$delivery.caseUrl", 0]},
        "city":           {"$arrayElemAt": ["$delivery.city", 0]},
        "invoiceUrl":     {"$arrayElemAt": ["$delivery.invoiceUrl", 0]},
        "jobType":        {"$arrayElemAt": ["$delivery.jobType", 0]},
        "orderId":        {"$arrayElemAt": ["$delivery.orderId", 0]},
        "subject":        {"$arrayElemAt": ["$delivery.subject", 0]},
        "ticketNumber":   {"$arrayElemAt": ["$delivery.ticketNumber", 0]},
        "lob":            {"$arrayElemAt": ["$delivery.lob", 0]},
        "adhoc_vehicle":  1,
        "createdAt":      1,
        "status":         1,
        "scheduledDate":  1,
        "firstScheduleDate": {"$arrayElemAt": ["$delivery.firstScheduleDate", 0]},
        "Confirmation Status": {"$cond": {
            "if": {"$anyElementTrue": {"$map": {
                "input": "$delivery", "as": "del",
                "in": {"$eq": ["$$del.deliveryConfirmStatus", True]},
            }}},
            "then": "Confirm",
            "else": "No response",
        }},
        "deliveryDate":   {"$arrayElemAt": ["$delivery.createdAt", 0]},
        "deliverDate":    {"$arrayElemAt": ["$delivery.deliverDate", 0]},
        "startTrip":      {"$arrayElemAt": ["$delivery.startTrip", 0]},
        "endTrip":        {"$arrayElemAt": ["$delivery.endTrip", 0]},
        "rescheduledDate":{"$arrayElemAt": ["$delivery.rescheduledDate", 0]},
        "loginTime": 1,
        "logoutTime": 1,
    }},
    {"$project": {
        "_id": 0,
        "agentId":              "$agentID",
        "Transport":            "$transportId",
        "Status":               "$status",
        "Case Addigned Date":   "$deliveryDate",
        "Agent Name":           "$agentName",
        "Case ID Number":       "$caseId",
        "First Name":           "$firstname",
        "Last Name ":           "$lastname",
        "Email":                "$email",
        "Sub Category":         "$subCategory",
        "Category":             "$category",
        "Case Url":             "$caseUrl",
        "City":                 "$city",
        "Invoice Url\t":        "$invoiceUrl",
        "Job Type":             "$jobType",
        "Order Id":             "$orderId",
        "Subject":              "$subject",
        "Ticket Number":        "$ticketNumber",
        "Transition Date":      "$createdAt",
        "Scheduled Date":       "$scheduledDate",
        "First Schedule Date":  "$firstScheduleDate",
        "Done Date":            "$doneDate",
        "Adhoc Vehicle":        "$adhoc_vehicle",
        "LOB":                  "$lob",
        "End Trip Time":        "$endTrip",
        "Start Trip Time":      "$startTrip",
        "loginTime":            "$loginTime",
        "logoutTime":           "$logoutTime",
        "rescheduledDate":      "$rescheduledDate",
        "Confirmation Status":  "$Confirmation Status",
    }},
]

# ─────────────────────────────────────────────────────────────
# Fetch from Metabase via /api/dataset (native MongoDB query)
# ─────────────────────────────────────────────────────────────
print(f'[refresh] Querying Metabase /api/dataset (db={DATABASE_ID}, collection=trips)…', flush=True)
t0 = time.time()
result = metabase_post('/api/dataset', body={
    'database': DATABASE_ID,
    'type': 'native',
    'native': {
        'query': json.dumps(PIPELINE),
        'collection': 'trips',
    },
    # Disable the userland 2000-row cap; we want all rows in the date window
    'middleware': {'add-default-userland-constraints?': False, 'userland-query?': True},
    'constraints': {'max-results': 1000000, 'max-results-bare-rows': 1000000},
})
elapsed = time.time() - t0
print(f'[refresh] Metabase responded in {elapsed:.1f}s', flush=True)

if 'data' not in result or 'rows' not in result['data']:
    print(f'ERROR: unexpected Metabase response shape: keys={list(result.keys())}', file=sys.stderr)
    sys.exit(2)

cols = [c.get('name') or c.get('display_name') for c in result['data']['cols']]
rows_raw = result['data']['rows']
print(f'[refresh] Got {len(rows_raw)} rows × {len(cols)} cols', flush=True)
print(f'[refresh] Columns: {cols[:10]}{"…" if len(cols)>10 else ""}', flush=True)

# ─────────────────────────────────────────────────────────────
# Build column index map (be tolerant of name variations)
# ─────────────────────────────────────────────────────────────
def find_col(*candidates):
    """Return index of first matching column name (case-insensitive). -1 if none."""
    lower = [c.lower() if c else '' for c in cols]
    for cand in candidates:
        try:
            return lower.index(cand.lower())
        except ValueError:
            pass
    return -1

i = {
    'Status':       find_col('Status', 'status'),
    'City':         find_col('City', 'city'),
    'JobType':      find_col('Job Type', 'jobType', 'job_type'),
    'SD':           find_col('Scheduled Date', 'scheduledDate', 'scheduled_date'),
    'FSD':          find_col('first Schedule Date', 'firstScheduleDate', 'first_schedule_date'),
    'ASD':          find_col('Case Addigned Date', 'Case Assigned Date', 'caseAssignedDate'),
    'Adhoc':        find_col('Adhoc Vehicle', 'adhoc_vehicle', 'adhocVehicle'),
    'Transport':    find_col('Transport', 'transport', 'transportId'),
    'Agent':        find_col('Agent Name', 'agent_name', 'agentName'),
    'OID':          find_col('Order Id', 'orderId', 'order_id'),
    'TKT':          find_col('Ticket Number', 'ticketNumber', 'ticket_number'),
    'Del':          find_col('Deliver Date', 'deliverDate', 'deliver_date'),
}
missing = [k for k,v in i.items() if v < 0 and k in ('Status','City','JobType','SD','OID')]
if missing:
    print(f'ERROR: required columns missing in Metabase response: {missing}', file=sys.stderr)
    print(f'  Available: {cols}', file=sys.stderr)
    sys.exit(3)

# ─────────────────────────────────────────────────────────────
# Determine date window: today − 1 IST (for the dashboard's display window)
# ─────────────────────────────────────────────────────────────
max_data_date = today_ist - timedelta(days=1)
print(f'[refresh] Today (IST) = {today_ist}, max data date = {max_data_date}', flush=True)

# ─────────────────────────────────────────────────────────────
# Transform rows → RAW / PROCESSED_FULL / EXCL_ROWS_FULL
# ─────────────────────────────────────────────────────────────
raw_rows, processed_rows, exclusion_rows = [], [], []
n_kept = 0; n_drop_future = 0; n_drop_no_sd = 0
min_dt, max_dt = None, None

for row in rows_raw:
    sd_ymd = to_ymd(row[i['SD']]) if i['SD']>=0 else ''
    if not sd_ymd or not re.match(r'^\d{4}-\d{2}-\d{2}$', sd_ymd):
        n_drop_no_sd += 1; continue
    try: d_ = datetime.strptime(sd_ymd, '%Y-%m-%d').date()
    except Exception: n_drop_no_sd += 1; continue
    if d_ > max_data_date:
        n_drop_future += 1; continue
    n_kept += 1
    if min_dt is None or d_ < min_dt: min_dt = d_
    if max_dt is None or d_ > max_dt: max_dt = d_

    norm = [normalize_cell(c) for c in row]
    norm[i['SD']] = sd_ymd
    if i['FSD']>=0: norm[i['FSD']] = to_ymd(row[i['FSD']])
    if i['Del']>=0: norm[i['Del']] = to_ymd(row[i['Del']]) or norm[i['Del']]
    raw_rows.append(norm)

    status = (norm[i['Status']] or '') if i['Status']>=0 else ''
    city   = (norm[i['City']] or '')   if i['City']>=0 else ''
    jt     = (norm[i['JobType']] or '') if i['JobType']>=0 else ''
    fs     = norm[i['FSD']] if i['FSD']>=0 else ''
    adh    = (norm[i['Adhoc']] or '')   if i['Adhoc']>=0 else ''
    trans  = (norm[i['Transport']] or '') if i['Transport']>=0 else ''
    agent  = (norm[i['Agent']] or '')   if i['Agent']>=0 else ''
    oid    = norm[i['OID']]             if i['OID']>=0 else None
    tkt    = norm[i['TKT']]             if i['TKT']>=0 else None
    del_d  = norm[i['Del']] or ''       if i['Del']>=0 else ''

    cat  = m_cat(jt)
    done = 'Done' if status in DONE_STATUSES else 'Not Done'
    if adh:        veh_type, veh_concat = 'Adhoc Vehicle',  adh
    elif trans:    veh_type, veh_concat = 'Regular Vehicle', trans
    else:          veh_type, veh_concat = '', ''
    if   done == 'Done' and fs and sd_ymd == fs: fsd_flag = 'True'
    elif done == 'Done' and fs and sd_ymd != fs: fsd_flag = 'False'
    else:                                         fsd_flag = 'NoFS'

    if jt in EXCL_JOB_TYPES:
        exclusion_rows.append([jt, city, cat, status, agent, sd_ymd])
        # Excluded job types live ONLY in EXCL_ROWS_FULL — never pollute PROCESSED_EXCEL_FULL.
        continue

    processed_rows.append([
        city, jt, cat, done, veh_type, agent, del_d, sd_ymd,
        trans, adh, veh_concat, oid, tkt, fs, fsd_flag
    ])

print(f'[refresh] Kept {n_kept}, dropped {n_drop_future} future, {n_drop_no_sd} no-SD', flush=True)
print(f'[refresh] Range: {min_dt} → {max_dt} | exclusion rows: {len(exclusion_rows)}', flush=True)

# ─────────────────────────────────────────────────────────────
# Collect rescheduled Case IDs → fetch Zoho reasons
# ─────────────────────────────────────────────────────────────
CASE_ID_COL = find_col('Case ID Number', 'caseId', 'case_id')
RESCH_COL   = find_col('rescheduledDate', 'Rescheduled Date', 'rescheduled_date')

rescheduled_case_ids = []
seen_cids = set()
if CASE_ID_COL >= 0 and RESCH_COL >= 0:
    # Sort rows by scheduled date descending so most-recent rescheduled go first
    for row in sorted(raw_rows, key=lambda r: r[i['SD']] or '', reverse=True):
        if row[RESCH_COL]:   # non-null rescheduledDate = ticket was rescheduled
            cid = str(row[CASE_ID_COL] or '').strip()
            if cid and cid not in seen_cids:
                seen_cids.add(cid)
                rescheduled_case_ids.append(cid)
    # Cap at 250 to keep the refresh under ~40 seconds of Zoho API calls
    if len(rescheduled_case_ids) > 250:
        print(f'[zoho] Capping at 250 most-recent rescheduled (total: {len(rescheduled_case_ids)})', flush=True)
        rescheduled_case_ids = rescheduled_case_ids[:250]
print(f'[refresh] Rescheduled tickets to look up: {len(rescheduled_case_ids)}', flush=True)

zoho_reasons = fetch_zoho_reasons(rescheduled_case_ids)

# ─────────────────────────────────────────────────────────────
# Build JS constants
# ─────────────────────────────────────────────────────────────
processed_headers = [
    'City','Job Type','Category','Done','VehicleType','Agent Name','Deliver Date',
    'Scheduled Date','Transport','Adhoc Vehicle','VehicleConcat','Order Id',
    'Ticket Number','first Schedule Date','FSD'
]
exclusion_headers = ['Job Type','City','Category','Status','Agent Name','Scheduled Date']

raw_js    = 'const RAW_EXCEL = '            + json.dumps({'headers':cols,'rows':raw_rows}, ensure_ascii=False, separators=(',',':')) + ';'
proc_js   = 'const PROCESSED_EXCEL = '      + json.dumps({'headers':processed_headers,'rows':[]}, ensure_ascii=False, separators=(',',':')) + ';'
pfull_js  = 'const PROCESSED_EXCEL_FULL = ' + json.dumps({'headers':processed_headers,'rows':processed_rows}, ensure_ascii=False, separators=(',',':')) + ';'
excl_js   = 'var EXCL_ROWS_FULL = '         + json.dumps({'headers':exclusion_headers,'rows':exclusion_rows}, ensure_ascii=False, separators=(',',':')) + ';'
zoho_js   = 'const ZOHO_REASONS = '         + json.dumps(zoho_reasons, ensure_ascii=False, separators=(',',':')) + ';'

print(f'[refresh] JS sizes: raw={len(raw_js)/1024/1024:.2f}MB, pfull={len(pfull_js)/1024/1024:.2f}MB, zoho_reasons={len(zoho_reasons)}', flush=True)

# ─────────────────────────────────────────────────────────────
# Patch HTML
# ─────────────────────────────────────────────────────────────
print(f'[refresh] Reading {HTML_PATH}', flush=True)
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

def repl_line(html, pat, new, label):
    p = re.compile(pat, re.MULTILINE)
    m = p.search(html)
    if not m:
        print(f'  [WARN] {label} pattern not found — skipping', flush=True)
        return html
    return html[:m.start()] + new + html[m.end():]

html = repl_line(html, r'^const ZOHO_REASONS = \{[^\n]*\};\s*$',         zoho_js,  'ZOHO_REASONS')
html = repl_line(html, r'^const RAW_EXCEL = \{[^\n]*\};\s*$',            raw_js,   'RAW_EXCEL')
html = repl_line(html, r'^const PROCESSED_EXCEL = \{[^\n]*\};\s*$',      proc_js,  'PROCESSED_EXCEL')
html = repl_line(html, r'^const PROCESSED_EXCEL_FULL = \{[^\n]*\};\s*$', pfull_js, 'PROCESSED_EXCEL_FULL')
html = repl_line(html, r'^var EXCL_ROWS_FULL = \{[^\n]*\};\s*$',         excl_js,  'EXCL_ROWS_FULL')

# Date globals
new_min = min_dt.strftime('%Y-%m-%d') if min_dt else max_data_date.strftime('%Y-%m-%d')
new_max = max_dt.strftime('%Y-%m-%d') if max_dt else max_data_date.strftime('%Y-%m-%d')
html = re.sub(r"var MIN_YMD='[^']+',MAX_YMD='[^']+';", f"var MIN_YMD='{new_min}',MAX_YMD='{new_max}';", html, count=1)
html = re.sub(r"var MAX_YMD_GLOBAL = '[^']+';", f"var MAX_YMD_GLOBAL = '{new_max}';", html, count=1)
html = re.sub(r"var MIN_YMD_GLOBAL = '[^']+';", f"var MIN_YMD_GLOBAL = '{new_min}';", html, count=1)

# Default selected date = max date
y, mo, dy = max_dt.year, max_dt.month-1, max_dt.day
cd_new = (
    f"var calDates={{task:new Date({y},{mo},{dy}),fad:new Date({y},{mo},{dy}),"
    f"fsd:new Date({y},{mo},{dy}),tat:new Date({y},{mo},{dy}),"
    f"trip:new Date({y},{mo},{dy}),overview:new Date({y},{mo},{dy})}};"
)
html = re.sub(r"var calDates=\{[^}]+\};", cd_new, html, count=1)
html = re.sub(r"var calMonth=\d+,calYear=\d+,calSelectedDate=", f"var calMonth={mo},calYear={y},calSelectedDate=", html, count=1)

# "Last updated" badge — IST timestamp
last_updated_str = datetime.now(IST).strftime('%d %b %Y, %H:%M IST')
# Replace the date-badge content (header) — preserves the gen-time span
html = re.sub(
    r'<div class="date-badge">[^<]*&middot;[^<]*<span id="gen-time">[^<]*</span></div>',
    f'<div class="date-badge">Data: {new_max} &middot; <span id="gen-time">Updated {last_updated_str}</span></div>',
    html, count=1
)
# Update the static tv-range-text labels to point at new max date (e.g. "May 3, 2026")
human_max = max_dt.strftime('%b %-d, %Y') if hasattr(max_dt, 'strftime') else new_max
# Cross-platform %-d (Windows uses %#d)
try: human_max = max_dt.strftime('%b %-d, %Y')
except Exception: human_max = max_dt.strftime('%b %#d, %Y')
html = re.sub(r'<span class="tv-range-text">[^<]+</span>', f'<span class="tv-range-text">{human_max}</span>', html)

# Save
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'[refresh] Done. HTML now {len(html)/1024/1024:.2f} MB | last updated = {last_updated_str}', flush=True)
