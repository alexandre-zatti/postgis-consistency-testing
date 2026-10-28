# 1. Background

This page explains the few ideas needed to follow the rest. Skip what you already know.

## The software under test

- **PostGIS** adds geometry types and spatial functions to PostgreSQL. You call it from SQL,
  e.g. `SELECT ST_Contains(a, b) FROM parcels`.
- **GEOS** is the C++ library that does most of the computing behind those functions. PostGIS
  mostly checks its arguments, sometimes takes a shortcut, and then calls GEOS.
- **JTS** is the Java library GEOS was translated from. New algorithms are usually written in JTS
  first and then translated to C++. A translation mistake is a bug that exists only in GEOS.
- **Shapely** is a Python library that calls GEOS directly. If a problem also shows up in
  Shapely, the problem is in GEOS, not in PostGIS. That is how we told them apart.

## Shapes

| Type | Example (WKT, the text format used everywhere here) |
|---|---|
| point | `POINT (0 0)` |
| line | `LINESTRING (0 0, 2 2, 4 0)` |
| polygon, optionally with holes | `POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0), (1 1, 2 1, 2 2, 1 1))` |
| multi-shapes | `MULTIPOLYGON (...)`, `MULTILINESTRING (...)`, `MULTIPOINT (...)` |
| collection, mixed types | `GEOMETRYCOLLECTION (POINT (0 0), POLYGON (...))` |
| empty shapes | `POLYGON EMPTY`, `POINT EMPTY`. These are valid shapes with no points |

A shape has an **interior**, a **boundary** and an **exterior**. For a polygon, the boundary is
its outline. For a line, the boundary is its two end points.

## Two kinds of operations

**Predicates** answer yes or no: Contains, Within, Covers, CoveredBy, Intersects, Disjoint,
Touches, Equals. The differences matter at the boundary. A point exactly on a square's
outline is *covered* by the square, but not *contained* in it, because Contains requires the two
interiors to meet.

**Overlays** build a new shape from two shapes: Intersection (the overlap), Union, Difference,
SymDifference. Their results must be computed with rounding, so they can differ slightly from the
exact answer (see below).

## The relationship matrix (DE-9IM)

All predicates derive from one 3×3 table. A row is the interior, boundary or exterior of A, and
a column is the same for B. Each cell holds the dimension of where those two parts meet:
`F` (they do not meet), `0` (at points), `1` (along lines) or `2` (over an area).
`ST_Relate(a, b)` returns the nine cells as one string, row by row.

Example: a triangle A and the point B = `POINT (0 0)` at one of its corners.

|  | B interior | B boundary | B exterior |
|---|---|---|---|
| **A interior** | F | F | 2 |
| **A boundary** | 0 | F | 1 |
| **A exterior** | F | F | 2 |

As a string this is `FF20F1FF2`. Contains needs interior–interior to be non-empty (pattern
`T*****FF*`, `T` = any dimension, `*` = anything), so it is false. Covers accepts boundary–interior
as well, so it is true. Every named predicate is a pattern on this matrix, which gives us our
first consistency check (see [02-method.md](02-method.md)).

## Different routes to the same answer

PostGIS can answer one question through different code paths:

- **Direct call:** both shapes are given to GEOS once.
- **Prepared (cached) shape:** when the same shape appears in many rows of a query, PostGIS
  builds an indexed "prepared" version once and reuses it. Prepared predicates run different
  GEOS code.
- **Index scan:** a spatial index (GiST) first filters candidates by bounding box, then calls
  the predicate.
- **Wrapping:** the same shape can be passed as itself or inside a collection
  (`ST_ForceCollection`), which changes how GEOS sees it.

All routes must give the same answer. Disagreements between routes are a main source of
findings.

## Rounding

Coordinates are stored as 64-bit floating-point numbers (doubles). Most decimal values cannot be
represented exactly, and an intersection point of two segments usually lies between representable
numbers.

- **Predicates** in GEOS use robust techniques, and with **whole-number coordinates** below
  about one million (2^20) the key calculations are exact. Any disagreement between yes/no
  answers on such inputs is therefore a real bug. On decimal inputs we treat a disagreement as
  a candidate to examine.
- **Overlays** must round the new points they create. GEOS's overlay engine (OverlayNG) snaps
  points to nearby values and, if that fails, retries with coarser snapping. So an overlay can
  turn a sliver thinner than one rounding step into a line, without this being a bug.
  GEOS's maintainers say so explicitly.
- A **fixed-precision grid** (`ST_Intersection(a, b, gridSize)`) rounds everything to a chosen
  grid. We use it as a second opinion for overlays, and it can be wrong too (one of our results).

**RelateNG** is GEOS's new predicate engine, translated from JTS in 2024 (GEOS 3.13). The old
version tested here (GEOS 3.9.0) predates it, which helps date the problems.

## Testing ideas used

- **The oracle problem:** to test software you need to know the right answer, and for geometry we
  usually do not.
- **Metamorphic testing:** instead of the right answer, use relations that must hold between
  answers. For example, "A within B" must equal "B contains A".
- **Differential testing:** run the same input through different implementations or versions and
  compare the outputs.
- **Property-based testing:** write the relations as executable properties, check them on many
  randomly generated inputs, shrink each failure to a minimal input, and make every run replayable
  from its seed. This is the QuickCheck/Hypothesis tradition, implemented here by hand because the
  inputs come from our own generator.
- **Fuzzing:** generate large numbers of inputs automatically to find failures. Our generator is a
  fuzzer, and the consistency checks are its oracle. Crashes are caught as well.
- **Shrinking and triage:** a raw failing input is large and noisy. Shrinking removes parts while
  the failure persists. Triage merges duplicates, reruns each finding on other versions and
  classifies its cause.

## Prior work

- **Spatter** (Deng, Mang, Zhang and Rigger, SIGMOD 2024) tested spatial databases, PostGIS
  included, by comparing predicate answers on shapes moved by affine transformations. It
  tested predicates only. Shapes built by overlays were used to make inputs, but never checked.
- **Spader** (Li et al., 2025) applied equivalent transformations to PostGIS, MySQL and MariaDB.
  Only its abstract has been read so far.
- **SQLancer** and related tools (TLP, NoREC, PQS) find logic bugs in relational databases.
  Spatter showed that they miss spatial bugs.

This project adds three things:
- consistency checks on overlay results, not only on yes/no predicates;
- checks that compare code paths (direct, prepared, index, wrapped);
- a controlled, statistically tested comparison of ordinary and awkward shape generation.
