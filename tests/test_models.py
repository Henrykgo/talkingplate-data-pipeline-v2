import pytest
from pydantic import ValidationError

from talkingplate.models import (Dish, ExternalIds, Location, MenuStatus,
                       PriceVariant, Restaurant, restaurant_uuid)


def make_restaurant(**overrides) -> Restaurant:
    """A valid restaurant with the fewest fields; tests override what they test."""
    base = dict(
        external_ids=ExternalIds(osm_type="node", osm_id=1, osm_snapshot="t0"),
        name="Testowa", address="ul. Testowa 1",
        location=Location(lat=52.2, lng=21.0),
    )
    return Restaurant(**(base | overrides))


def test_id_is_minted_from_external_ids():
    assert make_restaurant().id == restaurant_uuid("node", 1)


def test_unknown_cuisine_rejected():
    with pytest.raises(ValidationError):
        make_restaurant(cuisines=["Itallian"])


def test_is_ready_needs_scraped_menu_and_required_fields():
    r = make_restaurant(
        website="https://testowa.pl",
        google_maps_url="https://maps.google.com/?q=testowa",
        cuisines=["Polish"],
        about="A small Polish place.",
    )
    assert r.is_ready() is False
    r.menu_status = MenuStatus.SCRAPED
    assert r.is_ready() is True
    r.website = ""
    assert r.is_ready() is False


   