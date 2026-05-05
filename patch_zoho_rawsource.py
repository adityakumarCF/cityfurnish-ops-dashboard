import sys
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', errors='replace', closefd=False)

content = open('Task_Efficiency_Dashboard.html', encoding='utf-8').read()

# ── Find and replace loadZohoReasons ─────────────────────────────────────────
START_MARKER = 'async function loadZohoReasons(){'
END_MARKER   = '\n\n// Enhance rescheduled drill table with Zoho reason column'

start = content.find(START_MARKER)
end   = content.find(END_MARKER, start)

if start < 0 or end < 0:
    print('WARN: could not locate loadZohoReasons')
    sys.exit(1)

OLD_FN = content[start:end]

NEW_FN = """async function loadZohoReasons(){
  var el = document.getElementById('sv-zoho-reasons');
  if(!el) return;

  // Step 1: find rescheduled tickets in RAW_EXCEL for the current date range
  var range = (typeof resolveCurrentRange==='function') ? resolveCurrentRange('simplified') : null;
  var reschTks = {};  // ticketNumber -> true
  if(typeof RAW_EXCEL !== 'undefined' && range){
    var rh = RAW_EXCEL.headers;
    var tkI  = rh.indexOf('Ticket Number');
    var sdI  = rh.indexOf('Scheduled Date');
    var rdI  = rh.indexOf('rescheduledDate');
    if(tkI>=0 && sdI>=0 && rdI>=0){
      RAW_EXCEL.rows.forEach(function(row){
        var sd = (row[sdI] || '').slice(0,10);   // YYYY-MM-DD
        var rd = row[rdI];
        var tk = String(row[tkI] || '').trim();
        if(tk && rd && sd && sd >= range.start && sd <= range.end){
          reschTks[tk] = true;
        }
      });
    }
  }

  var total = Object.keys(reschTks).length;
  if(!total){
    el.innerHTML = '<p style="color:var(--muted);font-size:12px;text-align:center;padding:12px">No rescheduled tickets in the selected period.</p>';
    return;
  }

  // Step 2: join with Zoho reasons map for reason text
  var zohoMap = await fetchZohoReasons();
  var counts  = {};
  Object.keys(reschTks).forEach(function(tk){
    var reason = (zohoMap[tk] && zohoMap[tk].reason) ? zohoMap[tk].reason : 'Not specified';
    counts[reason] = (counts[reason] || 0) + 1;
  });

  // Step 3: render table
  var sorted = Object.entries(counts).sort(function(a,b){ return b[1]-a[1]; });
  var h = '<table class="sv-table"><thead><tr><th>Reschedule Reason</th><th>Count</th><th>% Share</th></tr></thead><tbody>';
  sorted.forEach(function(pair){
    var pct = (pair[1]/total*100).toFixed(1);
    var cls = pct>=30?'sv-r':pct>=15?'sv-o':'sv-g';
    h += '<tr><td style="text-align:left">'+pair[0]+'</td><td>'+pair[1]+'</td><td class="'+cls+'">'+pct+'%</td></tr>';
  });
  h += '<tr class="sv-tot"><td style="text-align:left"><strong>Total Rescheduled</strong></td><td><strong>'+total+'</strong></td><td></td></tr>';
  h += '</tbody></table>';
  el.innerHTML = h;
}"""

content = content[:start] + NEW_FN + content[end:]
print('OK: loadZohoReasons rewritten — driven from RAW_EXCEL, joined with Zoho reasons')

open('Task_Efficiency_Dashboard.html', 'w', encoding='utf-8').write(content)
