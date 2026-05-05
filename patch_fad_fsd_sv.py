import sys, io, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Task_Efficiency_Dashboard.html')
content = open(HTML, encoding='utf-8').read()
changes = []

# ── 1. Fix sv-cat-hdr CSS: nth-child(even) overrides it for Pickup row ────────
OLD_CSS = 'sv-cat-hdr td{background:#2e5fa3;color:#fff;font-weight:700;padding:5px 10px}'
NEW_CSS = 'sv-cat-hdr td{background:#2e5fa3!important;color:#fff!important;font-weight:700;padding:5px 10px}'
if OLD_CSS in content:
    content = content.replace(OLD_CSS, NEW_CSS, 1)
    changes.append('1. FSD heading: !important on sv-cat-hdr background')
else:
    print('WARN 1: sv-cat-hdr CSS not found')

# ── 2. Fix FAD calculation: global OID count + FAD only from Done orders ──────
OLD_FAD = """// First pass — track vehicle-days (row-level) and build per-order info
  var orderInfo={}; // oid -> {cat, city, count, hasDone, vehicleConcat}
  rows.forEach(function(r){
    var cat=r[CAI],city=r[CI],done=r[DI],sd=r[SDI],vc=r[VCI],vt=r[VTI],oid=r[OI];
    if(!cat||!city)return;
    // vehicle-day tracking stays at row level
    if(vc){
      if(vt==='Regular Vehicle'){fvReg[city].add(vc);if(!fvDayReg[city][sd])fvDayReg[city][sd]=new Set();fvDayReg[city][sd].add(vc);}
      else if(vt==='Adhoc Vehicle'){fvAdh[city].add(vc);if(!fvDayAdh[city][sd])fvDayAdh[city][sd]=new Set();fvDayAdh[city][sd].add(vc);}
      if(done==='Done')fvDone[city]++;
    }
    if(oid===null||oid===undefined||oid===''){
      // Row has no Order ID — treat as a unique standalone order (count=1 → FAD-true)
      var syntheticKey='__norowid_'+(r[hdr.indexOf('Ticket Number')]||Math.random());
      orderInfo[syntheticKey]={cat:cat,city:city,count:1,hasDone:done==='Done',vehicleConcat:vc||null};
      return;
    }
    if(!orderInfo[oid]){
      orderInfo[oid]={cat:cat,city:city,count:0,hasDone:false,vehicleConcat:vc||null};
    }
    orderInfo[oid].count++;
    if(done==='Done')orderInfo[oid].hasDone=true;
    if(!orderInfo[oid].vehicleConcat&&vc)orderInfo[oid].vehicleConcat=vc;
  });
  // Second pass — classify each unique order into fadData and tally fvFad
  Object.keys(orderInfo).forEach(function(oid){
    var info=orderInfo[oid];
    var cat=info.cat,city=info.city;
    if(!fadData[cat])fadData[cat]={};
    if(!fadData[cat][city])fadData[cat][city]={assigned:0,done:0,fad:0,pct:0};
    fadData[cat][city].assigned++;
    if(info.hasDone)fadData[cat][city].done++;
    if(info.count===1){
      fadData[cat][city].fad++;
      if(info.vehicleConcat)fvFad[city]++;
    }
  });
  CATS.forEach(function(cat){newCities.forEach(function(c){
    var d=fadData[cat][c];
    // FAD% = FAD-true orders / total orders × 100  (NEW: was FAD/Done, now FAD/Total)
    d.pct=d.assigned?+((d.fad/d.assigned)*100).toFixed(1):0;
  });});"""

NEW_FAD = """// Build global Order ID count across entire 4-month dataset (not just current range)
  // An OID appearing >1 time globally was rescheduled at some point — NOT FAD
  var globalOidCount={};
  PROCESSED_EXCEL_FULL.rows.forEach(function(r){
    var oid=r[OI];
    if(oid!==null&&oid!==undefined&&oid!=='') globalOidCount[oid]=(globalOidCount[oid]||0)+1;
  });

  // First pass — track vehicle-days (row-level) and build per-order info
  var orderInfo={}; // oid -> {cat, city, hasDone, vehicleConcat}
  rows.forEach(function(r){
    var cat=r[CAI],city=r[CI],done=r[DI],sd=r[SDI],vc=r[VCI],vt=r[VTI],oid=r[OI];
    if(!cat||!city)return;
    // vehicle-day tracking stays at row level
    if(vc){
      if(vt==='Regular Vehicle'){fvReg[city].add(vc);if(!fvDayReg[city][sd])fvDayReg[city][sd]=new Set();fvDayReg[city][sd].add(vc);}
      else if(vt==='Adhoc Vehicle'){fvAdh[city].add(vc);if(!fvDayAdh[city][sd])fvDayAdh[city][sd]=new Set();fvDayAdh[city][sd].add(vc);}
      if(done==='Done')fvDone[city]++;
    }
    if(oid===null||oid===undefined||oid===''){
      var syntheticKey='__norowid_'+(r[hdr.indexOf('Ticket Number')]||Math.random());
      orderInfo[syntheticKey]={cat:cat,city:city,hasDone:done==='Done',vehicleConcat:vc||null,synthetic:true};
      return;
    }
    if(!orderInfo[oid]){
      orderInfo[oid]={cat:cat,city:city,hasDone:false,vehicleConcat:vc||null,synthetic:false};
    }
    if(done==='Done')orderInfo[oid].hasDone=true;
    if(!orderInfo[oid].vehicleConcat&&vc)orderInfo[oid].vehicleConcat=vc;
  });
  // Second pass: assigned = all unique OIDs in range; done = Done OIDs; fad = Done + globally unique
  Object.keys(orderInfo).forEach(function(oid){
    var info=orderInfo[oid];
    var cat=info.cat,city=info.city;
    if(!fadData[cat])fadData[cat]={};
    if(!fadData[cat][city])fadData[cat][city]={assigned:0,done:0,fad:0,pct:0};
    fadData[cat][city].assigned++;
    if(info.hasDone){
      fadData[cat][city].done++;
      // FAD = done in current range AND order ID never appeared on any other date globally
      var isUnique=info.synthetic||(globalOidCount[oid]||0)===1;
      if(isUnique){
        fadData[cat][city].fad++;
        if(info.vehicleConcat)fvFad[city]++;
      }
    }
  });
  CATS.forEach(function(cat){newCities.forEach(function(c){
    var d=fadData[cat][c];
    // FAD% = FAD / Total Done (only done orders can be FAD)
    d.pct=d.done?+((d.fad/d.done)*100).toFixed(1):0;
  });});"""

if OLD_FAD in content:
    content = content.replace(OLD_FAD, NEW_FAD, 1)
    changes.append('2. FAD: global OID count, FAD only from Done, FAD%=FAD/Done')
else:
    print('WARN 2: FAD calculation block not found')

# ── 3. Fix renderFadPage: Overall FAD% formula and subtitle ───────────────────
OLD_FAD_KPI = "const overallFad = totalAssigned?((totalFad/totalAssigned)*100).toFixed(1):'0.0';"
NEW_FAD_KPI = "const overallFad = totalDone?((totalFad/totalDone)*100).toFixed(1):'0.0';"
if OLD_FAD_KPI in content:
    content = content.replace(OLD_FAD_KPI, NEW_FAD_KPI, 1)
    changes.append('3. renderFadPage: Overall FAD% = FAD/Total Done')
else:
    print('WARN 3: overallFad formula not found')

OLD_FAD_SUB = "s:'FAD / Total Assigned'"
NEW_FAD_SUB = "s:'FAD / Total Done'"
if OLD_FAD_SUB in content:
    content = content.replace(OLD_FAD_SUB, NEW_FAD_SUB, 1)
    changes.append('3b. renderFadPage: subtitle FAD/Total Done')
else:
    print('WARN 3b: FAD subtitle not found')

# ── 4. Add svRenderTask function (before svRenderTrip) ────────────────────────
SV_TASK_FN = """function svRenderTask(cities,dateLabel){
  var cats=TASK.categories||['Delivery','Pickup','SR'];
  var dataCities=cities.filter(function(c){
    return cats.some(function(cat){return TASK.task[cat]&&TASK.task[cat][c];});
  });
  if(!dataCities.length) return '';

  var h='<div class="sv-section">';
  h+='<div class="sv-report-title">TASK EFFICIENCY DETAILS &mdash; '+dateLabel+'</div>';
  h+='<table class="sv-table"><thead><tr><th class="sv-thl">Category</th><th>Metric</th>';
  dataCities.forEach(function(c){h+='<th>'+c+'</th>';});
  h+='<th>Total</th></tr></thead><tbody>';

  cats.forEach(function(cat,ci){
    var span=2+dataCities.length+1;
    h+='<tr class="sv-cat-hdr"><td colspan="'+span+'">'+cat+'</td></tr>';
    var totD=0,totN=0,totA=0;
    dataCities.forEach(function(c){
      var d=(TASK.task[cat]&&TASK.task[cat][c])||{done:0,not_done:0,total:0};
      totD+=d.done;totN+=d.not_done;totA+=d.total;
    });
    function taskRow(label,getFn,tot,colorFn){
      h+='<tr><td></td><td class="sv-tdl">'+label+'</td>';
      dataCities.forEach(function(c){
        var d=(TASK.task[cat]&&TASK.task[cat][c])||{done:0,not_done:0,total:0,pct:0};
        var val=getFn(d);
        var cls=colorFn?colorFn(val):'';
        h+='<td class="'+cls+'">'+val+'</td>';
      });
      var tc=colorFn?colorFn(tot):'';
      h+='<td class="'+tc+'">'+tot+'</td></tr>';
    }
    taskRow('Done',function(d){return d.done;},totD,null);
    taskRow('Not Done',function(d){return d.not_done;},totN,null);
    taskRow('Done %',
      function(d){var p=d.total?(d.done/d.total*100):0;return p.toFixed(2)+'%';},
      totA?(totD/totA*100).toFixed(2)+'%':'0.00%',
      function(val){var p=parseFloat(val);return p>=90?'sv-g':p>=75?'sv-o':'sv-r';});
    taskRow('Total Assigned',function(d){return d.total;},totA,null);
    if(ci<cats.length-1) h+='<tr class="sv-spacer"><td colspan="'+span+'"></td></tr>';
  });

  // Vehicle rows (scheduled efficiency)
  var span2=2+dataCities.length+1;
  h+='<tr class="sv-spacer"><td colspan="'+span2+'"></td></tr>';
  function vehRow(label,getFn,totFn,colorFn){
    h+='<tr><td></td><td class="sv-tdl">'+label+'</td>';
    var tot=0;
    dataCities.forEach(function(c){
      var v=TASK.vehicle[c]||{};
      var val=getFn(v);
      tot=totFn?totFn(tot,v):tot+val;
      var cls=colorFn?colorFn(v,val):'';
      h+='<td class="'+cls+'">'+(typeof val==='number'&&!Number.isInteger(val)?val.toFixed(2):val)+'</td>';
    });
    var totDisp=typeof tot==='number'&&!Number.isInteger(tot)?tot.toFixed(2):tot;
    h+='<td>'+totDisp+'</td></tr>';
  }

  // Aggregate vehicle totals
  var aggReg=0,aggAdh=0,aggVeh=0,aggVD=0,aggSched=0,aggDone=0,aggFadC=0;
  dataCities.forEach(function(c){
    var v=TASK.vehicle[c]||{};
    aggReg+=v.regular||0;aggAdh+=v.adhoc||0;aggVeh+=v.total_vehicles||0;
    aggVD+=v.vehicle_days||0;aggSched+=v.total_scheduled||0;aggDone+=v.total_done||0;
  });

  h+='<tr class="sv-tot"><td></td><td class="sv-tdl"><strong>Total Scheduled</strong></td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td><strong>'+(v.total_scheduled||0)+'</strong></td>';});
  h+='<td><strong>'+aggSched+'</strong></td></tr>';

  h+='<tr><td></td><td class="sv-tdl">Reg Vehicles</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td>'+(v.regular||0)+'</td>';});
  h+='<td>'+aggReg+'</td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Ad-hoc Vehicles</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td>'+(v.adhoc||0)+'</td>';});
  h+='<td>'+aggAdh+'</td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Total Vehicles</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td>'+(v.total_vehicles||0)+'</td>';});
  h+='<td>'+aggVeh+'</td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Efficiency</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};var e=v.sched_eff||0;var ok=e>=(v.threshold||6);h+='<td><span class="badge '+(ok?'badge-green':'badge-red')+'">'+e.toFixed(2)+'</span></td>';});
  var totE=aggVD?+(aggSched/aggVD).toFixed(2):0;
  h+='<td>'+totE.toFixed(2)+'</td></tr>';

  h+='<tr class="sv-spacer"><td colspan="'+span2+'"></td></tr>';

  h+='<tr class="sv-tot"><td></td><td class="sv-tdl"><strong>Total Done</strong></td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td><strong>'+(v.total_done||0)+'</strong></td>';});
  h+='<td><strong>'+aggDone+'</strong></td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Efficiency</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};var e=v.done_eff||0;var ok=e>=(v.threshold||6);h+='<td><span class="badge '+(ok?'badge-green':'badge-red')+'">'+e.toFixed(2)+'</span></td>';});
  var doneE=aggVD?+(aggDone/aggVD).toFixed(2):0;
  h+='<td>'+doneE.toFixed(2)+'</td></tr>';

  h+='<tr class="sv-spacer"><td colspan="'+span2+'"></td></tr>';

  h+='<tr><td></td><td class="sv-tdl">Required Task</td>';
  var reqTot=0;
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};var r=(v.threshold||6)*(v.total_vehicles||0);reqTot+=r;h+='<td>'+r+'</td>';});
  h+='<td>'+reqTot+'</td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Total Vehicles</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td>'+(v.total_vehicles||0)+'</td>';});
  h+='<td>'+aggVeh+'</td></tr>';
  h+='<tr><td></td><td class="sv-tdl">Per Vehicle Task</td>';
  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td>'+(v.threshold||6)+'</td>';});
  var avgThr=dataCities.length?+(dataCities.reduce(function(s,c){var v=TASK.vehicle[c]||{};return s+(v.threshold||6);},0)/dataCities.length).toFixed(1):0;
  h+='<td>'+avgThr+'</td></tr>';

  h+='</tbody></table></div>';
  return h;
}

"""

# Insert svRenderTask before svRenderTrip
INSERT_BEFORE = 'function svRenderTrip('
if INSERT_BEFORE in content:
    content = content.replace(INSERT_BEFORE, SV_TASK_FN + INSERT_BEFORE, 1)
    changes.append('4. Added svRenderTask function')
else:
    print('WARN 4: svRenderTrip not found')

# ── 5. Reorder renderSimplifiedView: Task first, Trip last ────────────────────
OLD_SV_ORDER = (
    '    html+=svRenderTrip(cities,dateLabel);\n'
    '    html+=svRenderFad(cities,dateLabel);\n'
    '    html+=svRenderFsd(cities,dateLabel);\n'
    '    html+=svRenderTat(cities,dateLabel);'
)
NEW_SV_ORDER = (
    '    html+=svRenderTask(cities,dateLabel);\n'
    '    html+=svRenderFad(cities,dateLabel);\n'
    '    html+=svRenderFsd(cities,dateLabel);\n'
    '    html+=svRenderTat(cities,dateLabel);\n'
    '    html+=svRenderTrip(cities,dateLabel);'
)
if OLD_SV_ORDER in content:
    content = content.replace(OLD_SV_ORDER, NEW_SV_ORDER, 1)
    changes.append('5. Simplified view: Task first, Trip moved after TAT')
else:
    print('WARN 5: renderSimplifiedView order not found')

open(HTML, 'w', encoding='utf-8').write(content)
print('\nChanges applied:')
for c in changes:
    print(' -', c)
