"""The API reference of the documentation site is the package as it is."""

from pathlib import Path

import lighthouse
from scripts.reference import reference, text

WRITTEN = Path(__file__).parents[2] / "docs-site" / "app" / "reference.json"


def test_every_public_name_is_in_the_reference_once():
    names = [item["name"] for section in reference()["sections"] for item in section["names"]]
    assert sorted(names) == sorted(lighthouse.__all__)
    assert all(section["about"] for section in reference()["sections"])


def test_the_reference_of_the_site_is_up_to_date():
    assert WRITTEN.read_text() == text(), (
        "run: python scripts/reference.py ../docs-site/app/reference.json"
    )
