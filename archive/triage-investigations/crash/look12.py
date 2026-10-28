import json
D=json.load(open("crash_f.json"))
for o in D:
    if not o['shp']:
        print(o['key'],o['fn'],o['cur'],o['shpfns'])
        print('  A',o['a'][:300]); print('  B',o['b'][:300])
