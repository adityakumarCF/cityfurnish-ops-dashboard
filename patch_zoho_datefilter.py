import sys
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', errors='replace', closefd=False)

content = open('Task_Efficiency_Dashboard.html', encoding='utf-8').read()

OLD = """async function loadZohoReasons(){
  var el = document.getElementById('sv-zoho-reasons');
  if(!el) return;
  var map = await fetchZohoReasons();
  // Filter by current date range so daily/weekly/monthly selectors apply
  var range = (typeof resolveCurrentRange==='function') ? resolveCurrentRange('simplified') : null;
  var filtered = {};
  Object.keys(map).forEach(function(tk){
    var sd = map[tk].sd || '';
    if(!range || !sd || (sd >= range.start && sd <= range.end)) filtered[tk] = map[tk];
  });
  var keys = Object.keys(filtered);
  if(!keys.length){
    el.innerHTML = '<p style="color:var(--muted);font-size:12px;text-align:center;padding:12px">No rescheduled tickets in the selected period.</p>';
    return;
  }
  // Aggregate by reason
  var counts = {};
  keys.forEach(function(tk){
    var r = filtered[tk].reason || 'Not specified';
    counts[r] = (counts[r]||0) + 1;
  });
  var total = keys.length;
  var sorted = Object.entries(counts).sort(function(a,b){return b[1]-a[1];});
  var h = '<table class="sv-table"><thead><tr><th>Reschedule Reason</th><th>Count</th><th>% Share</th></tr></thead><tbody>';
  sorted.forEach(function(pair){
    var pct = (pair[1]/total*100).toFixed(1);
    h += '<tr><td style="text-align:left">'+pair[0]+'</td><td>'+pair[1]+'</td><td class="'+(pct>=30?'sv-r':pct>=15?'sv-o':'sv-g')+'">'+pct+'%</td></tr>';
  });
  h += '<tr class="sv-tot"><td style="text-align:left"><strong>Total Rescheduled</strong></td><td><strong>'+total+'</strong></td><td></td></tr>';
  h += '</tbody></table>';
  el.innerHTML = h;
}"""

NEW = """async function loadZohoReasons(){
  var el = document.getElementById('sv-zoho-reasons');
  if(!el) return;
  var map = await fetchZohoReasons();
  // Build ticketNumber -> scheduledDate from PROCESSED_EXCEL_FULL so we can
  // filter by date range even when the Zoho entry has no sd field (Worker KV data)
  var tkToSd = {};
  if(typeof PROCESSED_EXCEL_FULL!=='undefined'){
    var ph=PROCESSED_EXCEL_FULL.headers;
    var tkI=ph.indexOf('Ticket Number'),sdI=ph.indexOf('Scheduled Date');
    if(tkI>=0&&sdI>=0) PROCESSED_EXCEL_FULL.rows.forEach(function(row){
      var tk=String(row[tkI]||'').trim();
      if(tk&&!tkToSd[tk]) tkToSd[tk]=row[sdI]||'';
    });
  }
  var range=(typeof resolveCurrentRange==='function')?resolveCurrentRange('simplified'):null;
  var filtered={};
  Object.keys(map).forEach(function(tk){
    var sd=map[tk].sd||tkToSd[String(tk)]||'';
    if(!range||!sd||(sd>=range.start&&sd<=range.end)) filtered[tk]=map[tk];
  });
  var keys=Object.keys(filtered);
  if(!keys.length){
    el.innerHTML='<p style="color:var(--muted);font-size:12px;text-align:center;padding:12px">No rescheduled tickets in the selected period.</p>';
    return;
  }
  var counts={};
  keys.forEach(function(tk){
    var r=filtered[tk].reason||'Not specified';
    counts[r]=(counts[r]||0)+1;
  });
  var total=keys.length;
  var sorted=Object.entries(counts).sort(function(a,b){return b[1]-a[1];});
  var h='<table class="sv-table"><thead><tr><th>Reschedule Reason</th><th>Count</th><th>% Share</th></tr></thead><tbody>';
  sorted.forEach(function(pair){
    var pct=(pair[1]/total*100).toFixed(1);
    h+='<tr><td style="text-align:left">'+pair[0]+'</td><td>'+pair[1]+'</td><td class="'+(pct>=30?'sv-r':pct>=15?'sv-o':'sv-g')+'">'+pct+'%</td></tr>';
  });
  h+='<tr class="sv-tot"><td style="text-align:left"><strong>Total Rescheduled</strong></td><td><strong>'+total+'</strong></td><td></td></tr>';
  h+='</tbody></table>';
  el.innerHTML=h;
}"""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print('OK: loadZohoReasons now cross-references PROCESSED_EXCEL_FULL for date filtering')
else:
    print('WARN: old function not found')

open('Task_Efficiency_Dashboard.html', 'w', encoding='utf-8').write(content)
