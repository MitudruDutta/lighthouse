"""One ranking from several, by the places only."""

import pytest

from lighthouse import fuse


def ranking(*keys) -> list[dict]:
    return [{"key": key, "score": 100 - n} for n, key in enumerate(keys)]


def test_what_several_rankings_agree_on_comes_first():
    fused = fuse(
        {"graph": ranking("a", "b", "c"), "words": ranking("c", "a"), "meaning": ranking("a", "d")}
    )
    assert [item["key"] for item in fused] == ["a", "c", "b", "d"]
    assert fused[0] == {
        "key": "a",
        "score": pytest.approx(1 / 61 + 1 / 62 + 1 / 61),
        "places": {"graph": 1, "words": 2, "meaning": 1},
    }
    assert fused[1]["places"] == {"graph": 3, "words": 1}
    assert fused[3] == {"key": "d", "score": pytest.approx(1 / 62), "places": {"meaning": 2}}


def test_scores_of_the_rankings_are_not_used():
    high = [{"key": "a", "score": 9_999.0}, {"key": "b", "score": 0.001}]
    low = [{"key": "b", "score": 0.2}, {"key": "a", "score": 0.1}]
    fused = fuse({"one": high, "two": low})
    assert fused[0]["score"] == pytest.approx(fused[1]["score"])  # each is first once, second once
    assert [item["key"] for item in fused] == ["a", "b"]  # a tie goes by key


def test_ties_go_by_key_with_numbers_before_text():
    fused = fuse(
        {"one": ranking("b"), "two": ranking(7), "three": ranking("a"), "four": ranking(3)}
    )
    assert [item["key"] for item in fused] == [3, 7, "a", "b"]


def test_key_that_a_ranking_lists_twice_counts_once_at_its_best_place():
    fused = fuse({"one": ranking("a", "b", "a", "c")})
    assert [(item["key"], item["places"]["one"]) for item in fused] == [
        ("a", 1),
        ("b", 2),
        ("c", 3),
    ]


def test_best_come_first_up_to_the_limit():
    rankings = {"one": ranking(*"abcdef"), "two": ranking(*"fedcba")}
    assert len(fuse(rankings)) == 6 and len(fuse(rankings, limit=2)) == 2
    assert (
        fuse({}) == []
        and fuse({"one": []}) == []
        and fuse({"one": [], "two": ranking("a")})[0]["key"] == "a"
    )


def test_other_fields_of_the_items_are_ignored():
    items = [{"key": "a", "shared": 2, "through": [("AT", "x")]}, {"key": "b", "values": {"n": 1}}]
    assert [item["key"] for item in fuse({"graph": items})] == ["a", "b"]


@pytest.mark.parametrize(
    "rankings",
    [
        None,
        [],
        "graph",
        {"": []},
        {7: []},
        {"a\x00b": []},
        {"one": [{"score": 1}]},
        {"one": [{"key": None}]},
    ]
    + [{"one": [{"key": {"a": 1}}]}, {"one": ["a"]}, {"one": [{"key": 1.5}]}],
)
def test_rankings_of_a_wrong_form_are_refused(rankings):
    with pytest.raises(ValueError):
        fuse(rankings)


@pytest.mark.parametrize("ranking_", [None, "abc", {"key": "a"}, 7])
def test_ranking_that_is_not_a_list_is_refused(ranking_):
    with pytest.raises(TypeError, match="must be a list"):
        fuse({"one": ranking_})


@pytest.mark.parametrize("limit", [0, -1, 1001, 1.5, "10", None, True])
def test_limit_of_a_wrong_form_is_refused(limit):
    with pytest.raises(ValueError, match="limit"):
        fuse({"one": ranking("a")}, limit=limit)
