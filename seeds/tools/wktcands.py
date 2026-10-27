import json,sys,re,os
sys.stdout.reconfigure(encoding="utf-8")
RX=re.compile(r"""(['"])((?:MULTI)?(?:POLYGON|LINESTRING|POINT)\b[^'"]*|GEOMETRYCOLLECTION[^'"]*)\1""",re.I)
def cands(text):
    return [m.group(2) for m in RX.finditer(text or '')]
if __name__=='__main__':
    d=sys.argv[1]
    for f in sys.argv[2:]:
        i=json.load(open(os.path.join(d,f),encoding='utf-8'))
        for k,c in enumerate(cands(i['body'])):
            print(f,k,len(c),c[:70].replace('\n','\n'),'...',c[-30:].replace('\n','\n'))
