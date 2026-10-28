import subprocess, json, sys, re
PY=sys.executable
def call(fn,x,y,wrap=0,pattern=None,prepared=False):
    spec=json.dumps(dict(fn=fn,x=x,y=y,wrap=wrap,pattern=pattern,prepared=prepared))
    r=subprocess.run([PY,"-s","C:/Users/Ale/AppData/Local/Temp/crash-families/child.py",spec],capture_output=True,text=True)
    if r.returncode!=0:
        if 'Error' in r.stderr or 'Exception' in r.stderr: return 'EXC:'+r.stderr.strip().splitlines()[-1][:120]
        return 'CRASH:%x'%(r.returncode & 0xffffffff)
    return json.loads(r.stdout)
FN={"ST_Contains":"contains","ST_Within":"within","ST_Covers":"covers","ST_CoveredBy":"covered_by",
    "ST_Intersects":"intersects","ST_Disjoint":"disjoint","ST_Touches":"touches",
    "ST_Relate(matrix)":"relate","ST_Relate(pattern)":"relate_pattern"}
# probe index -> (orientation, wrap)
FORMS=[("ab",0),("ab",1),("ab",2),("ba",0),("ba",1),("ba",2)]
def form_of(probe):
    # map SQL probe text to index
    m=re.match(r"ST_\w+\((.*)\)$",probe); inner=m.group(1)
    args=[s.strip() for s in re.split(r",(?![^(]*\))",inner)][:2]
    first=args[0]; o="ab" if first.endswith("a") or first.endswith("a)") else "ba"
    if o=="ab" and first.startswith("ST_Force"): w=1
    elif o=="ab" and args[1].startswith("ST_Force"): w=2
    elif o=="ba" and first.startswith("ST_Force"): w=1
    elif o=="ba" and args[1].startswith("ST_Force"): w=2
    else: w=0
    return FORMS.index((o,w))
def pattern_of(probe):
    m=re.search(r"'([^']+)'",probe); return m.group(1) if m else None
def run_form(o,fn,i,a,b,pattern=None):
    ori,w=FORMS[i]
    x,y=(a,b) if ori=="ab" else (b,a)
    return call(fn,x,y,w,pattern)
