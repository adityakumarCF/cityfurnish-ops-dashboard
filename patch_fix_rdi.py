import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Task_Efficiency_Dashboard.html')
content = open(HTML, encoding='utf-8').read()

# R_RDI was added to the wrong function (the tatRows/trend function).
# It needs to be in recomputeAggregates where rawFiltered.forEach uses it.
# The recomputeAggregates R_* block ends with R_FSI; add R_RDI right after.
OLD = (
    "var R_SDI=RH.indexOf('Scheduled Date'),R_FSI=RH.indexOf('first Schedule Date');\n"
    "  var DONE_ST={'Pickup Done':1,'Completed':1,'Delivered':1};"
)
NEW = (
    "var R_SDI=RH.indexOf('Scheduled Date'),R_FSI=RH.indexOf('first Schedule Date');\n"
    "  var R_RDI=RH.indexOf('Requested Date');\n"
    "  var DONE_ST={'Pickup Done':1,'Completed':1,'Delivered':1};"
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print('OK: R_RDI added to recomputeAggregates RAW_EXCEL index block')
else:
    print('WARN: target block not found')

open(HTML, 'w', encoding='utf-8').write(content)
