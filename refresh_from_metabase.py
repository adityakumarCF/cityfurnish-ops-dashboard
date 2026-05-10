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
ZOHO_DC            = os.environ.get('ZOHO_DC', 'com')  # data center: com | in | eu | com.au | jp

if not METABASE_URL or not API_KEY:
    print('ERROR: METABASE_URL and METABASE_API_KEY env vars required', file=sys.stderr)
    sys.exit(1)

# IST timezone (UTC+5:30) — Trip Ops business runs on IST
IST = timezone(timedelta(hours=5, minutes=30))

DONE_STATUSES   = {'Pickup Done', 'Completed', 'Delivered'}
SR_PATTERN      = re.compile(r'repair|replace|upgrade|relocation|installation', re.IGNORECASE)
EXCL_JOB_TYPES  = {'PO Payment', 'Stock Transfer', 'Refurb Transfer'}
# Only these 5 cities are tracked in ops dashboards. All other cities (Chennai, Hosur,
# Jaipur, Nasik, etc.) are excluded from PROCESSED_EXCEL — they never reach the dashboard.
ALLOWED_CITIES = {'Bangalore', 'Gurgaon', 'Hyderabad', 'Mumbai', 'Pune'}

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
    url = f'https://accounts.zoho.{ZOHO_DC}/oauth/v2/token'
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

def fetch_zoho_reasons(case_ids, cid_to_sd=None):
    """Fetch reschedule reasons from Zoho Desk for the given Case IDs.
    Returns dict keyed by ticketNumber (short) → {reason, subReason, caseId, sd}.
    cid_to_sd maps caseId → scheduledDate (YYYY-MM-DD) so the dashboard can
    filter by date range. Silently skips if Zoho credentials are not configured."""
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
    debug_logged = False  # log raw customFields for first ticket only
    for idx, case_id in enumerate(case_ids):
        url = f'https://desk.zoho.{ZOHO_DC}/api/v1/tickets/{case_id}'
        req = urlreq.Request(url, headers=headers)
        try:
            with urlreq.urlopen(req, timeout=30) as r:
                ticket = json.loads(r.read().decode('utf-8'))
            cf = ticket.get('customFields') or {}
            if not debug_logged:
                print(f'  [zoho] DEBUG first ticket keys: {list(cf.keys())}', flush=True)
                print(f'  [zoho] DEBUG first ticket customFields: {json.dumps(cf, ensure_ascii=False)[:500]}', flush=True)
                debug_logged = True
            tk_num = str(ticket.get('ticketNumber') or '').strip()
            # Try both display name and common Zoho internal field name variants
            reason = (
                cf.get('Reschedule Reason') or
                cf.get('Rescheduled Reason') or
                cf.get('reschedule_reason') or
                cf.get('cf_reschedule_reason') or ''
            ).strip()
            sub_reason = (
                cf.get('Pickup Sub Reason') or
                cf.get('Pickup Reason') or
                cf.get('pickup_sub_reason') or
                cf.get('cf_pickup_sub_reason') or ''
            ).strip()
            if tk_num:
                reasons[tk_num] = {
                    'reason':    reason,
                    'subReason': sub_reason,
                    'caseId':    case_id,
                    'sd':        (cid_to_sd or {}).get(case_id, ''),
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
        "requestedDate":  {"$arrayElemAt": ["$delivery.requestedDate", 0]},
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
        "first Schedule Date":  "$firstScheduleDate",
        "Done Date":            "$doneDate",
        "Adhoc Vehicle":        "$adhoc_vehicle",
        "LOB":                  "$lob",
        "End Trip Time":        "$endTrip",
        "Start Trip Time":      "$startTrip",
        "loginTime":            "$loginTime",
        "logoutTime":           "$logoutTime",
        "rescheduledDate":      "$rescheduledDate",
        "Requested Date":       "$requestedDate",
        "Confirmation Status":  "$Confirmation Status",
    }},
]

# ─────────────────────────────────────────────────────────────
# Item-level (barcode) pipeline — deliveries collection, same date window, all cities
# ─────────────────────────────────────────────────────────────
ITEM_PIPELINE = [
    {"$addFields": {"name": {"$concat": [
        {"$ifNull": ["$firstName", ""]}, " ", {"$ifNull": ["$lastName", ""]},
    ]}}},
    # Date window — replaces the Gurgaon-only test filter from the source query.
    {"$match": {"scheduledDate": {
        "$gte": {"$date": f"{date_from}T00:00:00.000Z"},
        "$lt":  {"$date": f"{date_to}T00:00:00.000Z"},
    }}},
    {"$addFields": {"id": {"$toObjectId": "$agentId"}}},
    {"$lookup": {"from": "users", "localField": "id", "foreignField": "_id", "as": "agent"}},
    {"$lookup": {
        "from": "orderfromcityfurnishes",
        "let": {"id": {"$toObjectId": "$_id"}},
        "pipeline": [{"$match": {"$or": [
            {"$expr": {"$eq": ["$pickup_deliveryId", "$$id"]}},
            {"$expr": {"$eq": ["$deliveryId", "$$id"]}},
        ]}}],
        "as": "result",
    }},
    {"$sort": {"createdAt": -1}},
    {"$addFields": {"resultCount": {"$size": "$result"}}},
    {"$match": {"resultCount": {"$gt": 0}}},
    {"$unwind": {"path": "$agent",  "preserveNullAndEmptyArrays": True}},
    {"$unwind": {"path": "$result", "preserveNullAndEmptyArrays": True}},
    {"$addFields": {"odooId": "$cf_odoo_id"}},
    # Projection mirrors the user's verified Mongo query (which returns populated barcodes).
    {"$project": {
        "_id": 0,
        "Scheduled Date": {"$dateToString": {"format": "%d/%m/%Y", "date": "$scheduledDate"}},
        "Transition date": {"$dateToString": {"format": "%d/%m/%Y  %H:%M", "date": "$result.updatedAt"}},
        "City": "$city",
        "SO Number": {"$ifNull": ["$result.Sale_Order", "$odooId"]},
        "Ticket ID": "$ticketNumber",
        "Customer Name": {"$concat": [{"$ifNull": ["$firstName", ""]}, " ", {"$ifNull": ["$lastName", ""]}]},
        "Job Type": "$jobType",
        "Product Name": "$result.Product_name",
        "movement": "$Movement",
        "Movement": {"$switch": {
            "branches": [
                {"case": {"$eq": ["$category", "Order"]}, "then": "OUT"},
                {"case": {"$eq": ["$jobType", "Pickup and Refund"]}, "then": "In"},
                {"case": {"$eq": ["$jobType", "PO Payment"]}, "then": "In"},
                {"case": {"$eq": ["$jobType", "Refurb Transfer"]}, "then": "$movement"},
                {"case": {"$eq": ["$jobType", "Stock Transfer"]}, "then": "$movement"},
                {"case": {"$and": [
                    {"$or": [{"$eq": ["$subCategory", "Replace"]}, {"$eq": ["$subCategory", "Repair"]}]},
                    {"$eq": ["$result.client_Status", "Delivery Pending"]},
                ]}, "then": "OUT"},
                {"case": {"$and": [
                    {"$or": [{"$eq": ["$subCategory", "Replace"]}, {"$eq": ["$subCategory", "Repair"]}]},
                    {"$eq": ["$result.client_Status", "Replacement In"]},
                ]}, "then": "In"},
                {"case": {"$and": [
                    {"$eq": ["$subCategory", "Upgrade"]},
                    {"$cond": [{"$gt": [{"$ifNull": ["$result.deliveryId", None]}, None]}, True, False]},
                ]}, "then": "Out"},
                {"case": {"$and": [
                    {"$eq": ["$subCategory", "Upgrade"]},
                    {"$cond": [{"$gt": [{"$ifNull": ["$result.pickup_deliveryId", None]}, None]}, True, False]},
                ]}, "then": "in"},
            ],
            "default": "=",
        }},
        "Quantity":             {"$ifNull": ["$result.agentMarkqty", ""]},
        "Physical Status":      {"$ifNull": ["$result.status", ""]},
        # Wrap in $ifNull so Metabase always emits the column in its schema,
        # even when the first sampled rows happen to have a null barcode.
        # Without this, Metabase prunes the Barcode column entirely and the
        # Python extractor's find_icol('Barcode') returns -1 → all rows blank.
        "Barcode":              {"$ifNull": ["$result.barcode", ""]},
        "Tried Barcode":        {"$ifNull": ["$result.triedBarcode", ""]},
        "Not scanning reasons": {"$ifNull": ["$result.message", ""]},
        "Odoo Status": "",
        "Vehicle Number": {"$cond": {
            "if":   {"$eq": ["$transport", ""]},
            "then": "$adhoc_vehicle",
            "else": "$transport",
        }},
        "Agent Name": "$agent.name",
        "status": 1,
        "Status": "$result.status",
        "Expected Shipment Date": "$result.esd",
    }},
    {"$addFields": {"Movement": {"$ifNull": ["$Movement", "$movement"]}}},
    {"$project": {"movement": 0}},
    {"$addFields": {
        "Physical Status": {"$cond": {
            "if":   {"$eq": ["$Physical Status", "3"]},
            "then": "Not Done",
            "else": {"$cond": {
                "if":   {"$eq": ["$Physical Status", "2"]},
                "then": "Done",
                "else": "$Physical Status",
            }},
        }},
        "matchStatus": {"$cond": {
            "if":   {"$eq": ["$Barcode", "$Tried Barcode"]},
            "then": "match",
            "else": "non match",
        }},
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
    'RD':           find_col('Requested Date', 'requestedDate', 'requested_date'),
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
    if i['RD']>=0:  norm[i['RD']]  = to_ymd(row[i['RD']])
    if i['Del']>=0: norm[i['Del']] = to_ymd(row[i['Del']]) or norm[i['Del']]
    raw_rows.append(norm)

    status = (norm[i['Status']] or '') if i['Status']>=0 else ''
    city   = (norm[i['City']] or '')   if i['City']>=0 else ''
    # Skip rows from non-allowed cities (Chennai, Hosur, Jaipur, Nasik, etc.)
    if city not in ALLOWED_CITIES:
        continue
    jt     = (norm[i['JobType']] or '') if i['JobType']>=0 else ''
    fs     = norm[i['FSD']] if i['FSD']>=0 else ''
    rd     = norm[i['RD']]  if i['RD']>=0  else ''
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
    # FSD: Met = Sched Date <= Requested Date (fallback: First Scheduled Date)
    # Not Met = Sched Date > reference. MISSING = Done but no reference date at all.
    ref = rd or fs
    if done != 'Done':
        fsd_flag = 'NoFS'
    elif not ref:
        fsd_flag = 'MISSING'   # data issue — should not happen; flagged for QA
    else:
        fsd_flag = 'True' if sd_ymd <= ref else 'False'

    if jt in EXCL_JOB_TYPES:
        exclusion_rows.append([jt, city, cat, status, agent, sd_ymd])
        # Excluded job types live ONLY in EXCL_ROWS_FULL — never pollute PROCESSED_EXCEL_FULL.
        continue

    processed_rows.append([
        city, jt, cat, done, veh_type, agent, del_d, sd_ymd,
        trans, adh, veh_concat, oid, tkt, fs, fsd_flag, rd
    ])

print(f'[refresh] Kept {n_kept}, dropped {n_drop_future} future, {n_drop_no_sd} no-SD', flush=True)
print(f'[refresh] Range: {min_dt} → {max_dt} | exclusion rows: {len(exclusion_rows)}', flush=True)

# ─────────────────────────────────────────────────────────────
# Collect rescheduled Case IDs → fetch Zoho reasons
# ─────────────────────────────────────────────────────────────
CASE_ID_COL = find_col('Case ID Number', 'caseId', 'case_id')
RESCH_COL   = find_col('rescheduledDate', 'Rescheduled Date', 'rescheduled_date')

rescheduled_case_ids = []
cid_to_sd = {}   # Case ID → Scheduled Date (YYYY-MM-DD) for date-range filtering in the dashboard
seen_cids = set()
if CASE_ID_COL >= 0 and RESCH_COL >= 0:
    # Sort rows by scheduled date descending so most-recent rescheduled go first
    for row in sorted(raw_rows, key=lambda r: r[i['SD']] or '', reverse=True):
        if row[RESCH_COL]:   # non-null rescheduledDate = ticket was rescheduled
            cid = str(row[CASE_ID_COL] or '').strip()
            if cid and cid not in seen_cids:
                seen_cids.add(cid)
                rescheduled_case_ids.append(cid)
                cid_to_sd[cid] = row[i['SD']] or ''
    # Cap at 250 to keep the refresh under ~40 seconds of Zoho API calls
    if len(rescheduled_case_ids) > 250:
        print(f'[zoho] Capping at 250 most-recent rescheduled (total: {len(rescheduled_case_ids)})', flush=True)
        rescheduled_case_ids = rescheduled_case_ids[:250]
print(f'[refresh] Rescheduled tickets to look up: {len(rescheduled_case_ids)}', flush=True)

zoho_reasons = fetch_zoho_reasons(rescheduled_case_ids, cid_to_sd)

# ─────────────────────────────────────────────────────────────
# Fetch item-level (barcode) data — deliveries collection
# ─────────────────────────────────────────────────────────────
ITEM_HEADERS = [
    'City', 'Job Type', 'Category', 'Physical Status', 'Vehicle Number',
    'Agent Name', 'Scheduled Date', 'Ticket ID', 'SO Number',
    'Product Name', 'Barcode', 'matchStatus', 'Movement',
]
item_processed_rows = []

print(f'[refresh] Querying item-level data (db={DATABASE_ID}, collection=deliveries)…', flush=True)
t_item = time.time()
try:
    item_result = metabase_post('/api/dataset', body={
        'database': DATABASE_ID,
        'type': 'native',
        'native': {'query': json.dumps(ITEM_PIPELINE), 'collection': 'deliveries'},
        'middleware': {'add-default-userland-constraints?': False, 'userland-query?': True},
        'constraints': {'max-results': 1000000, 'max-results-bare-rows': 1000000},
    })
    print(f'[refresh] Item query responded in {time.time()-t_item:.1f}s', flush=True)

    if 'data' in item_result and 'rows' in item_result['data']:
        icols    = [c.get('name') or c.get('display_name') for c in item_result['data']['cols']]
        irows_raw = item_result['data']['rows']
        print(f'[refresh] Item data: {len(irows_raw)} rows × {len(icols)} cols', flush=True)

        def find_icol(*candidates):
            lower = [c.lower() if c else '' for c in icols]
            for cand in candidates:
                try: return lower.index(cand.lower())
                except ValueError: pass
            return -1

        ii = {
            'City':    find_icol('City', 'city'),
            'JT':      find_icol('Job Type', 'jobType'),
            'Status':  find_icol('Physical Status'),
            'Veh':     find_icol('Vehicle Number'),
            'Agent':   find_icol('Agent Name'),
            'SD':      find_icol('Scheduled Date'),
            'TKT':     find_icol('Ticket ID'),
            'SO':      find_icol('SO Number'),
            'Product': find_icol('Product Name'),
            'Barcode': find_icol('Barcode'),
            'Match':   find_icol('matchStatus'),
            'Move':    find_icol('Movement'),
        }

        for row in irows_raw:
            sd_raw = row[ii['SD']] if ii['SD'] >= 0 else None
            sd_ymd = to_ymd(sd_raw) if sd_raw else ''
            if not sd_ymd or not re.match(r'^\d{4}-\d{2}-\d{2}$', sd_ymd):
                continue
            try:    d_ = datetime.strptime(sd_ymd, '%Y-%m-%d').date()
            except Exception: continue
            if d_ > max_data_date:
                continue

            city    = str(row[ii['City']]    or '').strip() if ii['City']    >= 0 else ''
            jt      = str(row[ii['JT']]      or '').strip() if ii['JT']      >= 0 else ''
            status  = str(row[ii['Status']]  or '').strip() if ii['Status']  >= 0 else ''
            veh     = str(row[ii['Veh']]     or '').strip() if ii['Veh']     >= 0 else ''
            agent   = str(row[ii['Agent']]   or '').strip() if ii['Agent']   >= 0 else ''
            tkt     = str(row[ii['TKT']]     or '').strip() if ii['TKT']     >= 0 else ''
            so      = str(row[ii['SO']]      or '').strip() if ii['SO']      >= 0 else ''
            product = str(row[ii['Product']] or '').strip() if ii['Product'] >= 0 else ''
            barcode = str(row[ii['Barcode']] or '').strip() if ii['Barcode'] >= 0 else ''
            match   = str(row[ii['Match']]   or '').strip() if ii['Match']   >= 0 else ''
            move    = str(row[ii['Move']]    or '').strip() if ii['Move']    >= 0 else ''

            item_processed_rows.append([
                city, jt, m_cat(jt), status, veh, agent, sd_ymd,
                tkt, so, product, barcode, match, move,
            ])

        print(f'[refresh] Item processed: {len(item_processed_rows)} rows', flush=True)
    else:
        print(f'[refresh] WARN: Item query returned no data', flush=True)
except Exception as e:
    print(f'[refresh] WARN: Item data fetch failed: {e}', flush=True)

# ─────────────────────────────────────────────────────────────
# Build JS constants
# ─────────────────────────────────────────────────────────────
processed_headers = [
    'City','Job Type','Category','Done','VehicleType','Agent Name','Deliver Date',
    'Scheduled Date','Transport','Adhoc Vehicle','VehicleConcat','Order Id',
    'Ticket Number','first Schedule Date','FSD','Requested Date'
]
exclusion_headers = ['Job Type','City','Category','Status','Agent Name','Scheduled Date']

raw_js    = 'const RAW_EXCEL = '            + json.dumps({'headers':cols,'rows':raw_rows}, ensure_ascii=False, separators=(',',':')) + ';'
proc_js   = 'const PROCESSED_EXCEL = '      + json.dumps({'headers':processed_headers,'rows':[]}, ensure_ascii=False, separators=(',',':')) + ';'
pfull_js  = 'const PROCESSED_EXCEL_FULL = ' + json.dumps({'headers':processed_headers,'rows':processed_rows}, ensure_ascii=False, separators=(',',':')) + ';'
excl_js   = 'var EXCL_ROWS_FULL = '         + json.dumps({'headers':exclusion_headers,'rows':exclusion_rows}, ensure_ascii=False, separators=(',',':')) + ';'
zoho_js      = 'const ZOHO_REASONS = '         + json.dumps(zoho_reasons, ensure_ascii=False, separators=(',',':')) + ';'
item_js      = 'const ITEM_EXCEL = '          + json.dumps({'headers': ITEM_HEADERS, 'rows': []}, ensure_ascii=False, separators=(',',':')) + ';'
item_full_js = 'const ITEM_EXCEL_FULL = '     + json.dumps({'headers': ITEM_HEADERS, 'rows': item_processed_rows}, ensure_ascii=False, separators=(',',':')) + ';'

print(f'[refresh] JS sizes: raw={len(raw_js)/1024/1024:.2f}MB, pfull={len(pfull_js)/1024/1024:.2f}MB, item_full={len(item_full_js)/1024/1024:.2f}MB, zoho_reasons={len(zoho_reasons)}', flush=True)

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
html = repl_line(html, r'^const PROCESSED_EXCEL_FULL = \{[^\n]*\};\s*$', pfull_js,     'PROCESSED_EXCEL_FULL')
html = repl_line(html, r'^var EXCL_ROWS_FULL = \{[^\n]*\};\s*$',         excl_js,      'EXCL_ROWS_FULL')
html = repl_line(html, r'^const ITEM_EXCEL = \{[^\n]*\};\s*$',           item_js,      'ITEM_EXCEL')
html = repl_line(html, r'^const ITEM_EXCEL_FULL = \{[^\n]*\};\s*$',      item_full_js, 'ITEM_EXCEL_FULL')

# Date globals
new_min = min_dt.strftime('%Y-%m-%d') if min_dt else max_data_date.strftime('%Y-%m-%d')
new_max = max_dt.strftime('%Y-%m-%d') if max_dt else max_data_date.strftime('%Y-%m-%d')
html = re.sub(r"var MIN_YMD='[^']+',MAX_YMD='[^']+';", f"var MIN_YMD='{new_min}',MAX_YMD='{new_max}';", html, count=1)
html = re.sub(r"var MAX_YMD_GLOBAL = '[^']+';", f"var MAX_YMD_GLOBAL = '{new_max}';", html, count=1)
html = re.sub(r"var MIN_YMD_GLOBAL = '[^']+';", f"var MIN_YMD_GLOBAL = '{new_min}';", html, count=1)

# Default selected date = max date.
# Must include EVERY report key that uses resolveCurrentRange — missing keys fall back
# to the hardcoded default in JS (May 2) which causes count mismatches across tabs.
y, mo, dy = max_dt.year, max_dt.month-1, max_dt.day
date_str = f"new Date({y},{mo},{dy})"
cd_new = (
    f"var calDates={{task:{date_str},fad:{date_str},"
    f"fsd:{date_str},tat:{date_str},trip:{date_str},overview:{date_str},"
    f"kpitrend:{date_str},benchmark:{date_str},action:{date_str},simplified:{date_str}}};"
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
