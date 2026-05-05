import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Task_Efficiency_Dashboard.html')
content = open(HTML, encoding='utf-8').read()
changes = []

# ═══════════════════════════════════════════════════════════════
# A. CENTER ALIGNMENT — first column in all main report tables
# ═══════════════════════════════════════════════════════════════

# A1. tatTable (TAT city/job-type rows)
OLD_A1 = 'h+=`<tr><td>${d.name}</td>`'
NEW_A1 = 'h+=`<tr><td style="text-align:center">${d.name}</td>`'
if OLD_A1 in content:
    content = content.replace(OLD_A1, NEW_A1, 1)
    changes.append('A1. TAT tatTable: center first column (city/job type name)')
else:
    print('WARN A1: tatTable first-col pattern not found')

# A2. renderTaskPage / renderFadPage / renderFsdPage — shared pattern <tr${rowCls}><td>${rlbl}</td>
OLD_A2 = '<tr${rowCls}><td>${rlbl}</td>'
NEW_A2 = '<tr${rowCls}><td style="text-align:center">${rlbl}</td>'
count_a2 = content.count(OLD_A2)
if count_a2:
    content = content.replace(OLD_A2, NEW_A2)   # replace ALL — affects Task, FAD, FSD pages
    changes.append(f'A2. Task/FAD/FSD: center first column ({count_a2} occurrences)')
else:
    print('WARN A2: rowCls+rlbl pattern not found')

# A3. renderFadPage vehicle section — vH+=`<tr><td>${l}</td>
OLD_A3 = 'vH+=`<tr><td>${l}</td>${vCols.map'
NEW_A3 = 'vH+=`<tr><td style="text-align:center">${l}</td>${vCols.map'
if OLD_A3 in content:
    content = content.replace(OLD_A3, NEW_A3, 1)
    changes.append('A3. FAD vehicle section: center first column (metric label)')
else:
    print('WARN A3: FAD vehicle row pattern not found')

# ═══════════════════════════════════════════════════════════════
# B. TAT FORMULA — Requested Date → First Schedule Date fallback
# ═══════════════════════════════════════════════════════════════

# B1. recomputeAggregates TAT section — add R_RDI index
OLD_B1 = (
    "var R_SI=RH.indexOf('Status'),R_ASI=RH.indexOf('Case Addigned Date');\n"
    "  var R_CI=RH.indexOf('City'),R_JTI=RH.indexOf('Job Type');\n"
    "  var R_SDI=RH.indexOf('Scheduled Date'),R_FSI=RH.indexOf('first Schedule Date');"
)
NEW_B1 = (
    "var R_SI=RH.indexOf('Status'),R_ASI=RH.indexOf('Case Addigned Date');\n"
    "  var R_CI=RH.indexOf('City'),R_JTI=RH.indexOf('Job Type');\n"
    "  var R_SDI=RH.indexOf('Scheduled Date'),R_FSI=RH.indexOf('first Schedule Date');\n"
    "  var R_RDI=RH.indexOf('Requested Date');  // Requested Date — fallback to First Schedule Date"
)
if OLD_B1 in content:
    content = content.replace(OLD_B1, NEW_B1, 1)
    changes.append('B1. TAT: added R_RDI (Requested Date) column index')
else:
    print('WARN B1: R_SI/R_ASI block not found')

# B2. recomputeAggregates rawFiltered loop — use Requested Date with First Schedule Date fallback
OLD_B2 = "var assignedDate=parseAssignedDate(r[R_ASI]||'');"
NEW_B2 = "var assignedDate=parseAssignedDate(r[R_RDI]||'')||parseAssignedDate(r[R_FSI]||''); // Req Date, else First Sched Date"
if OLD_B2 in content:
    content = content.replace(OLD_B2, NEW_B2, 1)
    changes.append('B2. TAT recomputeAggregates: assignedDate = Req Date || First Sched Date')
else:
    print('WARN B2: assignedDate parseAssignedDate pattern not found')

# B3. tatRows loop (KPI trend function) — same fallback
OLD_B3 = "var ad=pAD(r[R_ASI]||'');if(!ad||!sd)return;"
NEW_B3 = "var ad=pAD(r[R_RDI]||'')||pAD(r[R_FSI]||'');if(!ad||!sd)return; // Req Date, else First Sched Date"
if OLD_B3 in content:
    content = content.replace(OLD_B3, NEW_B3, 1)
    changes.append('B3. TAT tatRows loop: ad = Req Date || First Sched Date')
else:
    print('WARN B3: pAD(r[R_ASI]) pattern not found')

# B4. KPI subtitle — update label
OLD_B4 = "s:'Sched Date − Assigned Date'"
NEW_B4 = "s:'Sched Date − Req/First Sched Date'"
if OLD_B4 in content:
    content = content.replace(OLD_B4, NEW_B4, 1)
    changes.append('B4. TAT KPI subtitle: updated to Req/First Sched Date')
else:
    print('WARN B4: Avg TAT subtitle not found')

# B5. svRenderTat KPI label (simplified view)
OLD_B5 = "{l:'Total Scheduled',v:totCases,c:''}"
NEW_B5 = "{l:'Total Assigned',v:totCases,c:''}"
if OLD_B5 in content:
    content = content.replace(OLD_B5, NEW_B5, 1)
    changes.append('B5. svRenderTat: "Total Scheduled" → "Total Assigned"')
else:
    print('WARN B5: svRenderTat Total Scheduled not found')

open(HTML, 'w', encoding='utf-8').write(content)
print('\nChanges applied:')
for c in changes:
    print(' -', c)
