from lib import *
A="GEOMETRYCOLLECTION (POLYGON EMPTY, POLYGON ((0 0, 1 0, 0 1, 0 0)), POLYGON ((0 0, -1 0, 0 -1, 0 0)))"
for y in ["POLYGON ((9 9, 10 9, 9 10, 9 9))","LINESTRING (9 9, 10 10)","POINT (9 9)","POLYGON ((-5 -5, 5 -5, 5 5, -5 5, -5 -5))","LINESTRING (-1 1, 1 -1)"]:
    print(y, "relate:",call('relate',A,y),"| FF*FF****:",call('relate_pattern',A,y,pattern='FF*FF****'),"| intersects:",call('intersects',A,y),"| touches:",call('touches',A,y))
