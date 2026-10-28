from lib import *
print(form_of("ST_Contains(b,ST_ForceCollection(a))"), form_of("ST_Contains(ST_ForceCollection(b),a)"), form_of("ST_Relate(a,b,'FF*FF****')"), form_of("ST_Relate(ST_ForceCollection(a),b)"))
print(call("relate","POLYGON((0 0,1 0,1 1,0 0))","POINT(0 0)"))
A="MULTIPOLYGON (((164484 439560, 164431 439492, 164415 439458, 164484 439560)))"
B="GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((164444 439544, 164448 439550, 164449 439556, 164444 439544)), POLYGON ((164449 439556, 164451 439558, 164452 439556, 164449 439556)))"
print(call("relate",A,B), call("relate",A,B.replace("POLYGON EMPTY, ","")))
