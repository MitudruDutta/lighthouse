"""What a name, a key, and a property may hold."""

import pytest

from lighthouse.values import (
    MAX_ITEMS,
    MAX_NAME,
    MAX_REFERENCES,
    MAX_TEXT,
    MAX_VALUES,
    describe,
    indexed,
    is_key,
    is_name,
    is_storable,
    mapping,
    named,
    properties,
    references,
    whole_number,
    without_words,
)

NOT_NAMES = [
    "",
    " ",
    " a",
    "a ",
    "a\nb",
    "a\tb",
    "a\x00b",  # NUL: the database cannot parse it
    "a\x7fb",
    "a\u200bb",  # zero width space: invisible
    "a\u202eb",  # right-to-left override: shows the text in another order
    "\ufeffa",  # byte order mark
    "a\u2028b",  # line separator
    "a\ud800b",  # lone surrogate: cannot be encoded
    "a\ue000b",  # private use
    "x" * (MAX_NAME + 1),
]


@pytest.mark.parametrize("value", ["a", "a b", "é/ü:1", "berth 7-A", "名前", "x" * MAX_NAME])
def test_visible_text_of_a_bounded_length_is_a_name(value):
    assert is_name(value) is True and is_key(value) is True


@pytest.mark.parametrize("value", [*NOT_NAMES, None, 7, True, b"a", ["a"]])
def test_everything_else_is_not_a_name(value):
    assert is_name(value) is False


@pytest.mark.parametrize("value", [0, -1, 2**63 - 1, -(2**63)])
def test_64_bit_integers_are_keys(value):
    assert is_key(value) is True


@pytest.mark.parametrize(
    "value", [*NOT_NAMES, None, True, False, 1.0, 2**63, -(2**63) - 1, [1], ("a",)]
)
def test_everything_else_is_not_a_key(value):
    assert is_key(value) is False


@pytest.mark.parametrize(
    "value",
    [None, "", "a", " spaces and\nlines\tare fine in a value ", "x" * MAX_TEXT, 0, -3, 2.5, True]
    + [[], [1, "a", 2.5, False], list(range(MAX_ITEMS)), -(2**63)],
)
def test_what_can_be_stored(value):
    assert is_storable(value) is True


@pytest.mark.parametrize(
    "value",
    [{"a": 1}, [[1]], [None], [{"a": 1}], float("nan"), float("inf"), [float("nan")], 2**63]
    + [(1, 2), b"a", object(), "a\x00b", "a\ud800b", ["a\x00b"], "x" * (MAX_TEXT + 1)]
    + [list(range(MAX_ITEMS + 1)), ["x" * (MAX_TEXT + 1)]],
)
def test_what_cannot_be_stored(value):
    assert is_storable(value) is False


def test_mapping_takes_a_map_or_nothing():
    assert mapping(None, "values") == {} and mapping({"a": 1}, "values") == {"a": 1}
    for wrong in (0, "", [], "a", [("a", 1)]):
        with pytest.raises(TypeError, match="values must be a map"):
            mapping(wrong, "values")


def test_properties_drop_nulls_and_keep_the_rest():
    given = {"a": 1, "b": None, "c": "", "d": [1, 2], "e": False}
    assert properties(given, {"id"}, "values") == {"a": 1, "c": "", "d": [1, 2], "e": False}
    assert properties(None, set(), "values") == {}
    assert len(properties({f"p{i}": i for i in range(MAX_VALUES)}, set(), "values")) == MAX_VALUES


@pytest.mark.parametrize(
    "given",
    [{"a b": 1}, {"a`b": 1}, {"": 1}, {"1a": 1}, {7: 1}, {"id": 1}, {"a": {"b": 1}}, {"a": [[1]]}]
    + [{"x" * 101: 1}, {"a": "b\x00c"}, {f"p{i}": i for i in range(MAX_VALUES + 1)}],
)
def test_properties_reject_an_unsafe_name_a_taken_name_and_an_unstorable_value(given):
    with pytest.raises(ValueError, match="values"):
        properties(given, {"id"}, "values")


def test_named_takes_only_names():
    named(agent="a", kind="k")
    for wrong in (None, 7, ["a"], b"a", *NOT_NAMES):
        with pytest.raises(ValueError, match="agent must be text"):
            named(agent=wrong)


def test_references_are_checked_and_put_in_one_order():
    assert references(None, "to") == [] and references("a", "to") == ["a"]
    assert references(["b", 2, "a", 1, "b", 1], "to") == [1, 2, "a", "b"]
    assert len(references([f"k{i}" for i in range(MAX_REFERENCES)], "to")) == MAX_REFERENCES
    for wrong in (
        ["a", ""],
        [None],
        ["a\x00"],
        [1.5],
        [f"k{i}" for i in range(MAX_REFERENCES + 1)],
    ):
        with pytest.raises(ValueError, match="to"):
            references(wrong, "to")


def test_describe_is_short_and_safe_for_any_value():
    deep = inner = {}
    for _ in range(100_000):
        inner["a"] = {}
        inner = inner["a"]
    cyclic = {}
    cyclic["self"] = cyclic
    for hostile in (deep, cyclic, "x" * 10_000_000, list(range(1_000_000)), "a\x00b", "a\ud800b"):
        text = describe(hostile)
        assert len(text) < 1_000
        text.encode("utf-8")  # can be stored
        assert "\x00" not in text


@pytest.mark.parametrize("value", [0, -1, 11, 1.0, 2.5, "3", None, True, False, [3]])
def test_whole_number_takes_only_a_whole_number_within_its_limit(value):
    assert [whole_number(n, "limit", 10) for n in (1, 5, 10)] == [1, 5, 10]
    with pytest.raises(ValueError, match="limit must be a whole number from 1 to 10"):
        whole_number(value, "limit", 10)


def test_indexed_text_is_its_words_alone():
    assert indexed(["Pump-seal\nLine_two", None, 7, ["a b", 3], "  "]) == {
        "words": "Pump seal Line two a b"
    }
    assert indexed([None, 7, "", " -*- "]) == {}
    assert without_words({"words": "x", "text": "y"}) == {"text": "y"}
