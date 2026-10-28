import json, collections, math, re
from lib import *
D=json.load(open("crash_f.json"))
c=collections.Counter(); mag=collections.Counter(); plain=collections.Counter()
for o in D:
    holder=[]
    for n,w in (('a',o['a']),('b',o['b'])):
        if 'EMPTY' in w: holder.append(w.split(' ')[0])
    c[tuple(holder)]+=1
    m=o['mag']; mag['<1' if m<1 else '1e4-1e6' if m<1e7 else '>=1e15' if m>=1e15 else 'other']+=1
    plain[(tuple(holder), any(form_of(p) in (0,3) for p in o['cur']))]+=1
print("EMPTY-holding input type:",c); print("magnitude:",mag); print("(holder, plain form crashes):",plain)
s=min(D,key=lambda o:len(o['a'])+len(o['b'])); print(s['key'],s['fn'],s['cur']); print(s['a']); print(s['b'])
i=form_of(s['cur'][0]); print("replay:",run_form(s,FN[s['fn']],i,s['a'],s['b'],pattern_of(s['cur'][0])))
