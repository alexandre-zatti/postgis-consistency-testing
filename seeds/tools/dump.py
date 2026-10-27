import json,sys,os
sys.stdout.reconfigure(encoding="utf-8")
d=sys.argv[1]
for f in sorted(os.listdir(d)):
    if f.endswith('.json') and not f.endswith('_c.json'):
        i=json.load(open(os.path.join(d,f),encoding='utf-8'))
        if 'title' not in i: print('=====',f,i);continue
        print('=====',f,i['state'],i.get('state_reason'),'|',i['title'],'| milestone:',(i.get('milestone') or {}).get('title'),'| closed',i.get('closed_at'))
        print(i.get('body'))
        c=json.load(open(os.path.join(d,f[:-5]+'_c.json'),encoding='utf-8'))
        for x in c: print('--- comment',x['user']['login'],x['created_at']); print(x['body'])
