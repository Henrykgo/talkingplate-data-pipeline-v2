"""The data contract. Every row shape the pipeline reads or writes is here.

Two tables reach the iOS app through Supabase: restaurants and dishes. The
columns they carry are fixed by the app; this file keeps them and adds the
pipeline's own bookkeeping. Anything derived (ready, prices) is computed at
the sync boundary, never stored, so it cannot drift from its inputs.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- App vocabularies (the iOS filters) ------------------------------------

class DietaryOption(StrEnum):
    VEGETARIAN = "Vegetarian"
    VEGAN = "Vegan"
    GLUTEN_FREE = "Gluten-free"


class MealType(StrEnum):
    BREAKFAST = "Breakfast"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    BRUNCH = "Brunch"


class EstablishmentType(StrEnum):
    CASUAL_DINING = "Casual Dining"
    FINE_DINING = "Fine Dining"
    CAFE = "Cafe"
    FAST_CASUAL = "Fast Casual"
    STREET_FOOD = "Street Food"


class Dresscode(StrEnum):
    CASUAL = "Casual"
    SMART_CASUAL = "Smart Casual"
    FORMAL = "Formal"


class Award(StrEnum):
    MICHELIN_STAR = "Michelin Star"
    MICHELIN_BIB_GOURMAND = "Michelin Bib Gourmand"
    MICHELIN_RECOMMENDED = "Michelin Recommended"
    GAULT_MILLAU = "Gault & Millau"


class Wheelchair(StrEnum):
    YES = "yes"
    LIMITED = "limited"
    NO = "no"


# --- Pipeline vocabularies (never shown to users) ---------------------------

class MenuStatus(StrEnum):
    PENDING = "pending"            # not done yet; transient errors keep it here
    SCRAPED = "scraped"            # extracted and passed the gates
    NEEDS_REVIEW = "needs_review"  # extracted, but a check wants a human; blocks publish
    NO_WEBSITE = "no_website"
    FAILED = "failed"              # a fact about the restaurant; see menu_failure


class MenuFailure(StrEnum):
    """Why menu_status is FAILED. Only things true about the restaurant or
    its site belong here. Quota limits and timeouts are facts about today's
    run: they go to the run ledger, bump menu_attempts, and the row stays
    PENDING. Low coverage is not a failure either: it routes to NEEDS_REVIEW
    with the number in menu_failure_detail."""
    NO_MENU_FOUND = "no_menu_found"
    PDF_UNREADABLE = "pdf_unreadable"
    REJECTED_BY_GATES = "rejected_by_gates"   # too few dishes or too few priced
    SITE_UNREACHABLE = "site_unreachable"     # settings.max_fetch_attempts on distinct days


class Provenance(StrEnum):
    OSM = "osm"
    SCRAPED = "scraped"
    LLM = "llm"
    DERIVED = "derived"
    MANUAL = "manual"


class SourceType(StrEnum):
    HTML = "html"
    PDF = "pdf"
    IMAGE = "image"
    STRUCTURED = "structured"


class SourceKind(StrEnum):
    FOOD = "food"
    DRINKS = "drinks"
    WINE = "wine"
    LUNCH = "lunch"
    OTHER = "other"


# --- Nested value objects (JSON columns in Supabase) -------------------------
# Absent is None everywhere except SocialMedia and OperatingHours, which keep
# "": the app decodes those JSON columns as plain strings, not optionals.

class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lng: float


class Reservations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool | None = None
    website: str | None = None


class OperatingHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monday: str = ""
    tuesday: str = ""
    wednesday: str = ""
    thursday: str = ""
    friday: str = ""
    saturday: str = ""
    sunday: str = ""


class SocialMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facebook: str = ""
    instagram: str = ""
    youtube: str = ""
    tiktok: str = ""


class ExternalIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    osm_type: str          # "node" | "way" | "relation"; an id is unique only within its type
    osm_id: int
    osm_snapshot: str      # Overpass timestamp_osm_base of the snapshot this row came from


class MenuSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    kind: SourceKind
    source_type: SourceType


# --- Identity ---------------------------------------------------------------
# Restaurant ids are derived from the OSM element on FIRST mint, so a rebuild
# from scratch reproduces them. They are not re-derived afterwards: when a
# mapper redraws a node as a building way, the element id changes, and ingest
# must find the existing row (same normalised name within ~50 m) and update
# external_ids while keeping id. Otherwise the app's ratings, visits and
# lists orphan.
#
# Dish ids are derived on first mint and CARRIED OVER on refresh: a new
# extraction matches dishes to the previous one through the fuzzy matcher and
# keeps the old id where a match exists. The ordinal distinguishes two dishes
# with the same name on one menu; if the first is removed, the second's
# derived id shifts, which the carry-over step also absorbs.

def restaurant_uuid(osm_type: str, osm_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"talkingplate/restaurant/{osm_type}/{osm_id}"))


def normalized_dish_name(name: str) -> str:
    """Casefold, strip diacritics, collapse whitespace. Shared with matching."""
    folded = unicodedata.normalize("NFKD", name.casefold())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def dish_uuid(restaurant_id: str, name: str, ordinal: int = 0) -> str:
    key = f"talkingplate/dish/{restaurant_id}/{normalized_dish_name(name)}/{ordinal}"
    return str(uuid5(NAMESPACE_URL, key))


# Fields that must be non-empty before a row is published. Checked by
# Restaurant.is_ready(); the sync writes the app's ready column from it.
REQUIRED_WHEN_READY = ["name", "address", "city", "location", "website",
                       "google_maps_url", "cuisines", "about"]


# --- The restaurant row -----------------------------------------------------

class Restaurant(BaseModel):
    # extra="forbid": a typo in a scraper is an error, not a silent new field.
    # validate_assignment: r.menu_status = "bogus" fails at the assignment.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str                        # filled from external_ids when absent, see _default_id
    external_ids: ExternalIds

    name: str
    phone: str | None = None
    cleaned_phone: str | None = None
    address: str
    district: str | None = None
    city: str = "Warsaw"
    location: Location

    website: str | None = None
    google_maps_url: str | None = None
    menu_sources: list[MenuSource] = Field(default_factory=list)

    about: str | None = None
    cuisines: list[str] = Field(default_factory=list)
    operating_hours: OperatingHours = Field(default_factory=OperatingHours)
    social_media: SocialMedia = Field(default_factory=SocialMedia)

    price_level: Annotated[int, Field(ge=1, le=4)] | None = None
    dietary_options: list[DietaryOption] = Field(default_factory=list)
    meal_type: list[MealType] = Field(default_factory=list)
    establishment_type: list[EstablishmentType] = Field(default_factory=list)
    outdoor_seating: bool | None = None
    wheelchair: Wheelchair | None = None
    reservations: Reservations = Field(default_factory=Reservations)
    awards: list[Award] = Field(default_factory=list)
    dresscode: Dresscode | None = None

    menu_status: MenuStatus = MenuStatus.PENDING
    menu_failure: MenuFailure | None = None
    menu_failure_detail: str | None = None
    menu_attempts: int = 0                   # transient errors increment this
    menu_last_attempt_at: str | None = None  # ISO UTC; attempts count per distinct day

    provenance: dict[str, Provenance] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _default_id(cls, data):
        # Runs on the raw input, before the required-field check, so a row
        # built from external_ids alone gets its id and one with neither
        # fails with the normal "field required" error.
        if not isinstance(data, dict) or data.get("id"):
            return data
        ext = data.get("external_ids")
        if isinstance(ext, ExternalIds):
            ext = ext.model_dump()
        if isinstance(ext, dict) and ext.get("osm_type") and ext.get("osm_id") is not None:
            data["id"] = restaurant_uuid(ext["osm_type"], ext["osm_id"])
        return data

    @field_validator("dresscode", "wheelchair", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if v == "" else v

    @field_validator("cleaned_phone")
    @classmethod
    def _nine_digits(cls, v):
        if v in (None, ""):
            return None
        if len(v) >= 9 and v.isdigit():
            return v
        raise ValueError(f"cleaned_phone must be digits, got {v!r}")

    @field_validator("cuisines")
    @classmethod
    def _known_cuisines(cls, v):
        # tp/cuisines.py is the only vocabulary: KNOWN is built from the OSM
        # tag table plus a few hand styles, so it cannot drift from the table.
        from .cuisines import unknown
        bad = unknown(v)
        if bad:
            raise ValueError(f"unknown cuisine(s): {bad}; add them to tp/cuisines.py")
        return v

    def is_ready(self) -> bool:
        """Publishable: menu scraped and every required field filled.
        Derived, never stored, so it cannot disagree with its inputs.
        A human hold is menu_status = NEEDS_REVIEW, which this refuses."""
        if self.menu_status is not MenuStatus.SCRAPED:
            return False
        return all(getattr(self, f) for f in REQUIRED_WHEN_READY)


# --- Menu rows --------------------------------------------------------------

# Ceiling 10000, not 2000: the old pipeline nulled a real 2900 zł Dom
# Pérignon and then dropped the dish. Champagne and rare spirits run to
# thousands; misreads (portion weights, phone fragments) land far below.
Price = Annotated[float, Field(ge=1, lt=10000)]


class PriceVariant(BaseModel):
    # Strict: a variant with an implausible price fails at construction, and
    # the extractor's parser drops that variant, not the dish.
    model_config = ConfigDict(extra="forbid")
    label: str
    price: Price


class Dish(BaseModel):
    # No validate_assignment here: _price_is_cheapest_variant assigns price.
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    price: float | None = None     # the cheapest variant when variants exist
    variants: list[PriceVariant] = Field(default_factory=list)
    currency: str = "PLN"
    description: str | None = None
    section: str | None = None
    dietary_tags: list[str] = Field(default_factory=list)
    language: str | None = None
    # None = grounding did not run (no source text, e.g. a photo menu).
    # False = it ran and the price or name was not found in the source.
    grounded: bool | None = None

    @field_validator("price")
    @classmethod
    def _plausible(cls, v):
        # Lenient on purpose: a bad top-level price becomes "unpriced", not a
        # rejected dish. Variants are strict because there is no fallback.
        return v if v is None or 1 <= v < 10000 else None

    @model_validator(mode="after")
    def _price_is_cheapest_variant(self):
        if self.variants:
            self.price = min(v.price for v in self.variants)
        return self

    def prices(self) -> list[float]:
        """Every price point, for the app's prices column. Derived."""
        if self.variants:
            return [v.price for v in self.variants]
        return [self.price] if self.price is not None else []


class MenuDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restaurant_id: str
    sources: list[MenuSource]
    fetched_at: str
    extracted_at: str
    model: str
    config_fingerprint: str
    coverage: float | None = None
    dishes: list[Dish]