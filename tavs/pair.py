"""The unit of testing: one pair of geometries and how it was produced."""

from dataclasses import dataclass, field
from typing import Literal, Optional

Coord = Literal["int", "float"]
Kind = Literal["predicate", "overlay"]


@dataclass
class Pair:
    a: str                      # WKT
    b: str                      # WKT
    coord: Coord                # integer grid or floating point; sets the rule tier
    kind: Kind                  # predicate pairs get R1-R4, overlay pairs also R5-R11
    arm: Optional[str] = None   # plain-int, plain-float, degen-int, degen-float, or None (seeds, XML)
    seed: Optional[int] = None
    index: Optional[int] = None
    moves: list[str] = field(default_factory=list)  # degenerate moves applied, in order
    source: Optional[str] = None  # seed id or XML file/case for E1
