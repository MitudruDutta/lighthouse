"""One ranking from several: what the graph, the words, and the meaning each put first.

Each way of recall gives its own order and its own kind of score. The scores cannot be
added, so only the places are used: an entity gets 1 / (60 + its place) from each ranking
it is in. This is reciprocal rank fusion. An entity that several rankings agree on comes
first, and the answer says which ranking put it where.
"""

from lighthouse.values import describe, is_key, is_name

WEIGHT_OF_PLACE = 60  # the usual constant: it keeps one first place from deciding everything


def fuse(rankings: dict[str, list[dict]], limit: int = 10) -> list[dict]:
    """Merge rankings of the same kind of entity, best first:
    [{"key", "score", "places"}]. `rankings` maps a name to the result of similar(),
    search(), or nearest(). "places" maps each ranking's name to the place it gave the
    entity, from 1."""
    if not isinstance(rankings, dict) or not all(is_name(name) for name in rankings):
        raise ValueError("rankings must map a name to a ranking")
    if type(limit) is not int or not 1 <= limit <= 1_000:
        raise ValueError("limit must be a whole number from 1 to 1000")
    places: dict = {}
    for name, ranking in rankings.items():
        if not isinstance(ranking, (list, tuple)):
            raise TypeError(f"ranking {name!r} must be a list")
        seen = set()
        for item in ranking:
            key = item.get("key") if isinstance(item, dict) else None
            if not is_key(key):
                raise ValueError(f"ranking {name!r}: an item without a valid key: {describe(item)}")
            if key not in seen:  # a key counts once, at its best place
                seen.add(key)
                places.setdefault(key, {})[name] = len(seen)
    fused = [
        {
            "key": key,
            "score": sum(1 / (WEIGHT_OF_PLACE + place) for place in found.values()),
            "places": found,
        }
        for key, found in places.items()
    ]
    fused.sort(key=lambda item: (-item["score"], isinstance(item["key"], str), item["key"]))
    return fused[:limit]
