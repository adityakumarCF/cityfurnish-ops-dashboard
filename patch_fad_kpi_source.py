import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Task_Efficiency_Dashboard.html')
content = open(HTML, encoding='utf-8').read()

# Change renderFadPage to source totalAssigned and totalDone from TASK.task
# (same numbers as Task report) instead of FAD.fad, so both reports agree.
OLD = (
    '  // FAD numbers below are ORDER-LEVEL: assigned/done/fad are unique-order counts (not row counts)\n'
    '  let totalDone=0,totalFad=0,totalAssigned=0;\n'
    "  FAD.categories.forEach(cat=>{cities.forEach(c=>{if(FAD.fad[cat][c]){totalDone+=FAD.fad[cat][c].done;totalFad+=FAD.fad[cat][c].fad;totalAssigned+=FAD.fad[cat][c].assigned;}});});"
)

NEW = (
    '  // totalAssigned and totalDone match the Task report (use TASK.task source);\n'
    '  // totalFad is FAD-specific (globally-unique Done orders)\n'
    '  let totalDone=0,totalFad=0,totalAssigned=0;\n'
    '  FAD.categories.forEach(cat=>{\n'
    '    cities.forEach(c=>{\n'
    '      if(TASK.task[cat]&&TASK.task[cat][c]){\n'
    '        totalAssigned+=TASK.task[cat][c].total||0;\n'
    '        totalDone+=TASK.task[cat][c].done||0;\n'
    '      }\n'
    '      if(FAD.fad[cat][c]) totalFad+=FAD.fad[cat][c].fad;\n'
    '    });\n'
    '  });'
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print('OK: renderFadPage — totalAssigned/totalDone now from TASK.task')
else:
    print('WARN: target block not found')

open(HTML, 'w', encoding='utf-8').write(content)
