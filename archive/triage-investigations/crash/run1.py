import json, re
from concurrent.futures import ThreadPoolExecutor
from lib import *
D=json.load(open("crash_f.json"))
def noempty(w):
    w2=re.sub(r",\s*(POLYGON |LINESTRING |POINT )?EMPTY","",w)
    w2=re.sub(r"(POLYGON |LINESTRING |POINT )?EMPTY,\s*","",w2)
    return w2
def job(o):
    fn=FN[o['fn']]; res=[]
    for pr in o['cur']:
        i=form_of(pr); pat=pattern_of(pr)
        a,b=o['a'],o['b']
        r=dict(probe=pr,i=i,base=run_form(o,fn,i,a,b,pat))
        na,nb=noempty(a),noempty(b)
        assert 'EMPTY' not in na+nb, (na,nb)
        r['noempty']=run_form(o,fn,i,na,nb,pat)
        if fn in ('covers','relate_pattern','covered_by'):
            r['relate']=run_form(o,'relate',i,a,b)
        res.append(r)
    return o['key'],res
with ThreadPoolExecutor(8) as ex:
    out=dict(ex.map(job,D))
json.dump(out,open("run1.json","w"),indent=1)
