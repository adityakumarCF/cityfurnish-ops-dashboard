import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Task_Efficiency_Dashboard.html')
content = open(HTML, encoding='utf-8').read()
changes = []

# ── 1. FSD KPI: "Total Tasks" → "Total Assigned" ─────────────────────────────
OLD1 = "{l:'Total Tasks',v:totalAll,s:cities.length<ALL_CITIES.length?cities.join(', '):'All categories',c:'blue',d:''}"
NEW1 = "{l:'Total Assigned',v:totalAll,s:cities.length<ALL_CITIES.length?cities.join(', '):'All categories',c:'blue',d:''}"
if OLD1 in content:
    content = content.replace(OLD1, NEW1, 1)
    changes.append('1. FSD KPI: "Total Tasks" → "Total Assigned"')
else:
    print('WARN 1: FSD Total Tasks not found')

# ── 2. FAD KPI: subtitle "Unique Order IDs" → "All categories" ───────────────
OLD2 = "{l:'Total Assigned',v:totalAssigned,s:cities.length<ALL_CITIES.length?cities.join(', '):'Unique Order IDs',c:'blue',d:''}"
NEW2 = "{l:'Total Assigned',v:totalAssigned,s:cities.length<ALL_CITIES.length?cities.join(', '):'All categories',c:'blue',d:''}"
if OLD2 in content:
    content = content.replace(OLD2, NEW2, 1)
    changes.append('2. FAD KPI: subtitle "Unique Order IDs" → "All categories"')
else:
    print('WARN 2: FAD Total Assigned subtitle not found')

# ── 3. TAT KPI: "Total Cases" → "Total Assigned", subtitle → "All categories" ─
OLD3 = "{l:'Total Cases',v:totCases,s:'All Zoho ticket cases',c:'blue',d:''}"
NEW3 = "{l:'Total Assigned',v:totCases,s:cities.length<ALL_CITIES.length?cities.join(', '):'All categories',c:'blue',d:''}"
if OLD3 in content:
    content = content.replace(OLD3, NEW3, 1)
    changes.append('3. TAT KPI: "Total Cases" → "Total Assigned", subtitle consistent')
else:
    print('WARN 3: TAT Total Cases not found')

# ── 4. Zoho reasons table: inline style → sv-tdl class ───────────────────────
OLD4a = "h += '<tr><td style=\"text-align:left\">'+pair[0]+'</td><td>'+pair[1]+'</td><td class=\"'+cls+'\">'+pct+'%</td></tr>';"
NEW4a = "h += '<tr><td class=\"sv-tdl\">'+pair[0]+'</td><td>'+pair[1]+'</td><td class=\"'+cls+'\">'+pct+'%</td></tr>';"
if OLD4a in content:
    content = content.replace(OLD4a, NEW4a, 1)
    changes.append('4a. Zoho reasons: reason cell style → sv-tdl class')
else:
    print('WARN 4a: Zoho reasons reason cell not found')

OLD4b = "  h += '<tr class=\"sv-tot\"><td style=\"text-align:left\"><strong>Total Rescheduled</strong></td><td><strong>'+total+'</strong></td><td></td></tr>';"
NEW4b = "  h += '<tr class=\"sv-tot\"><td class=\"sv-tdl\"><strong>Total Rescheduled</strong></td><td><strong>'+total+'</strong></td><td></td></tr>';"
if OLD4b in content:
    content = content.replace(OLD4b, NEW4b, 1)
    changes.append('4b. Zoho reasons: Total row style → sv-tdl class')
else:
    print('WARN 4b: Zoho reasons total row not found')

# ── 5. svRenderTask: add per-category Done breakdown after "Total Done" row ───
OLD5 = (
    "  h+='<tr class=\"sv-tot\"><td></td><td class=\"sv-tdl\"><strong>Total Done</strong></td>';\n"
    "  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td><strong>'+(v.total_done||0)+'</strong></td>';});\n"
    "  h+='<td><strong>'+aggDone+'</strong></td></tr>';\n"
    "  h+='<tr><td></td><td class=\"sv-tdl\">Efficiency</td>';"
)
NEW5 = (
    "  h+='<tr class=\"sv-tot\"><td></td><td class=\"sv-tdl\"><strong>Total Done</strong></td>';\n"
    "  dataCities.forEach(function(c){var v=TASK.vehicle[c]||{};h+='<td><strong>'+(v.total_done||0)+'</strong></td>';});\n"
    "  h+='<td><strong>'+aggDone+'</strong></td></tr>';\n"
    "  // Per-category Done breakdown\n"
    "  cats.forEach(function(cat){\n"
    "    var catDoneTot=0;\n"
    "    h+='<tr><td></td><td class=\"sv-tdl\">&nbsp;&nbsp;&rsaquo; '+cat+'</td>';\n"
    "    dataCities.forEach(function(c){\n"
    "      var d=(TASK.task[cat]&&TASK.task[cat][c])||{done:0};\n"
    "      catDoneTot+=d.done;\n"
    "      h+='<td>'+d.done+'</td>';\n"
    "    });\n"
    "    h+='<td>'+catDoneTot+'</td></tr>';\n"
    "  });\n"
    "  h+='<tr><td></td><td class=\"sv-tdl\">Efficiency</td>';"
)
if OLD5 in content:
    content = content.replace(OLD5, NEW5, 1)
    changes.append('5. svRenderTask: per-category Done breakdown added below Total Done')
else:
    print('WARN 5: svRenderTask Total Done row not found')

open(HTML, 'w', encoding='utf-8').write(content)
print('\nChanges applied:')
for c in changes:
    print(' -', c)
