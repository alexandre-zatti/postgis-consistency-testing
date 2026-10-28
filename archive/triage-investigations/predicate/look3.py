import csv,sys,json,collections,os,re
d=sys.argv[1]
rows=list(csv.DictReader(open(d+'/findings.csv',encoding='utf-8')))
c=collections.Counter()
for r in rows:
    if r['rule']!='R3': continue
    a=r['shrunk_a']; b=r['shrunk_b']
    if not('EMPTY' in a or 'EMPTY' in b): continue
    j=json.load(open(d+'/reruns/'+r['key']+'.json',encoding='utf-8'))
    v=j['images']['current']['violations']
    raws=[(x['sub'],x['function'],x['orientation'],json.dumps(x['raw'])) for x in v if x['rule']=='R3']
    sig=re.sub(r'[-\d.e]+','#',a)+' || '+re.sub(r'[-\d.e]+','#',b)
    c[(r['sub'],r['function'],sig[:200])]+=1
for k,n in c.most_common(): print(n,k)
