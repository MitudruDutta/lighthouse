"""Kinds of entity. The application declares each kind once; every query is built from it."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType

# Labels, edge types, and properties the library owns. An application cannot use them.
ENGINE_LABELS = {"State", "WriteFailure", "Task", "Agent", "Episode", "Entry", "Handoff"}
ENGINE_LABELS |= {"Lesson", "Playbook", "Step", "Trigger", "Entity", "Stamp"}
ENGINE_LABELS |= {"Session", "Message", "Reference"}
ENGINE_TYPES = {"HAS_STATE", "NEXT"}
ENGINE_PROPERTIES = {"fp", "valid_from", "valid_to", "recorded_at", "by", "seen_last", "entry"}
ENGINE_PROPERTIES |= {"words"}  # the searchable text: values.WORDS

# Names are put into query text and into parameter maps, so they are checked, not escaped.
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,99}")

SELF = "self"  # as a relation target: the kind that is being declared
# Every entity has this label besides the label of its kind. FalkorDB's PageRank takes one
# label, so this is what lets it run over the entities of all kinds and over nothing else.
ENTITY = "Entity"
# One node with this label holds a random id that ensure_schema() gives a graph. A graph that
# is deleted and made again under its name has another id: it is another graph.
STAMP = "Stamp"
VECTOR = "Vector"  # the vectors of kind Thing are nodes with the label ThingVector
# An entity of kind Thing whose text has no vector of the current model has the label
# ThingToEmbed as well, so embed() finds it without reading the others.
TO_EMBED = "ToEmbed"
MAX_DIMENSIONS = 4096


@dataclass(frozen=True, eq=False)
class Kind:
    """A kind of entity, declared once by the application.

    label      node label
    key        property that identifies one entity
    times      values that are stored as native time values
    relations  {TYPE: Kind}: edges from this kind to another, each with a validity window.
               Use SELF for a relation to the same kind: `{"KNOWS": SELF}`
    text       values that can be searched by their words
    dimensions size of the vectors that stand for that text; 0 for no search by meaning

    A Kind cannot change after it is made: its names were checked once and go into queries.
    """

    label: str
    key: str = "key"
    times: tuple[str, ...] = ()
    relations: dict = field(default_factory=dict)
    text: tuple[str, ...] = ()
    dimensions: int = 0

    def __post_init__(self):
        if not isinstance(self.relations, dict) or isinstance(self.times, str):
            raise TypeError(f"Kind {self.label!r}: times is a tuple and relations is a map")
        if isinstance(self.text, str):
            raise TypeError(f"Kind {self.label!r}: text is a tuple of property names")
        relations = {
            name: self if isinstance(target, str) and target == SELF else target
            for name, target in self.relations.items()
        }
        object.__setattr__(self, "times", tuple(self.times))
        object.__setattr__(self, "text", tuple(self.text))
        object.__setattr__(self, "relations", MappingProxyType(relations))
        for name in (self.label, self.key, *self.times, *self.relations, *self.text):
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError(f"invalid name in Kind {self.label!r}: {name!r}")
        if self.label in ENGINE_LABELS or set(self.relations) & ENGINE_TYPES:
            raise ValueError(f"Kind {self.label!r} uses a label or edge type of the engine")
        if {self.key, *self.times, *self.text} & ENGINE_PROPERTIES or self.key in self.times:
            raise ValueError(f"Kind {self.label!r} uses a property name of the engine")
        if set(self.text) & set(self.times):
            raise ValueError(f"Kind {self.label!r}: a time cannot be searched as text")
        if any(not isinstance(target, Kind) for target in self.relations.values()):
            raise TypeError(f"relations of Kind {self.label!r} must map a type to a Kind")
        if type(self.dimensions) is not int or not 0 <= self.dimensions <= MAX_DIMENSIONS:
            raise ValueError(f"Kind {self.label!r}: dimensions is 0 to {MAX_DIMENSIONS}")
        if self.dimensions and not self.text:
            raise ValueError(f"Kind {self.label!r} has dimensions but no text to stand for")
        for suffix in (VECTOR, TO_EMBED):
            if self.label.endswith(suffix):
                raise ValueError(
                    f"Kind {self.label!r}: a label that ends in {suffix!r} is the engine's"
                )


def all_kinds(kinds) -> dict[str, Kind]:
    """The given kinds and every kind they point at, by label."""
    found, todo = {}, list(kinds)
    while todo:
        kind = todo.pop()
        known = found.get(kind.label)
        if known is None:
            found[kind.label] = kind
            todo += kind.relations.values()  # a kind may point at itself: visit it once
        elif known.key != kind.key:
            raise ValueError(f"label {kind.label!r} is declared with two different keys")
    return found
