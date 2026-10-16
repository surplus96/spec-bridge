import json

import pytest

from spec_bridge.registry.identity import MakerIndex, model_key
from tests.conftest import ROOT

MAKERS = json.loads((ROOT / "data/synth/registry/manufacturers.json").read_text())


@pytest.mark.parametrize("variant", ["{0} {1}", "{0}{1}", "{0}-{1}"])
def test_model_spacing_and_case_share_identity(variant: str) -> None:
    head, tail = "VX022", "009"
    assert model_key(variant.format(head, tail).lower()) == model_key(f"{head}-{tail}")


def test_same_series_is_not_same_identity() -> None:
    assert model_key("VX022-109") != model_key("VX022-009")


def test_alias_resolves_to_registered_maker() -> None:
    index = MakerIndex(MAKERS)
    maker = MAKERS[0]
    assert index.resolve(maker["aliases"][0].upper()) == maker["maker_id"]


def test_unknown_or_partial_maker_is_not_guessed() -> None:
    index = MakerIndex(MAKERS)
    assert index.resolve(MAKERS[0]["name"].split()[0]) is None


def test_name_shared_by_two_makers_rejected() -> None:
    clash = [dict(MAKERS[0]), dict(MAKERS[1], aliases=[MAKERS[0]["name"]])]
    with pytest.raises(ValueError, match="shared"):
        MakerIndex(clash)
