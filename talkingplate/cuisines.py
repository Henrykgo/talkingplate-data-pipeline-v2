"""Cuisine vocabulary. Raw OSM tag in, canonical ordered list out."""

CUISINES: dict[str, list[str]] = {
    "polish": ["Polish", "European"],
    "italian": ["Italian", "European"],
    "pizza": ["Pizza", "Italian", "European"],
    "french": ["French", "European"],
    "georgian": ["Georgian", "European"],
    "greek": ["Greek", "Mediterranean", "European"],
    "japanese": ["Japanese", "Asian"],
    "sushi": ["Sushi", "Japanese", "Asian"],
    "thai": ["Thai", "Asian"],
    "vietnamese": ["Vietnamese", "Asian"],
    "chinese": ["Chinese", "Asian"],
    "indian": ["Indian", "Asian"],
    "turkish": ["Turkish", "Middle Eastern"],
    "kebab": ["Kebab", "Middle Eastern"],
    "mexican": ["Mexican", "Latin American"],
    "american": ["American"],
    "burger": ["Burgers"],
    "steak_house": ["Steak"],
    "seafood": ["Seafood"],
    "vegan": ["Vegan"],
    "vegetarian": ["Vegetarian"],
}

IGNORED_TAGS = frozenset({"regional", "international", "traditional", "local"})

KNOWN: frozenset[str] = frozenset(
    name for names in CUISINES.values() for name in names
)

def from_osm(raw: str | None) -> list[str]:
    """"pizza;italian" -> ["Pizza", "Italian", "European"]; None -> []."""
    cuisines = []
    if not raw:
        return cuisines

    for tag in raw.split(";"):
        key = tag.strip().lower().replace(" ", "_")
        if key in IGNORED_TAGS:
            continue
        for name in CUISINES.get(key, []):
            if name not in cuisines:
                cuisines.append(name)
    return cuisines

def unknown(names: list[str]) -> list[str]:
    """Return the names that are not in KNOWN; empty list means all valid."""
    unknown_cuisines = []
    for i in names:
        if i not in KNOWN:
            unknown_cuisines.append(i)
    return unknown_cuisines

    