"""Rule modules. Importing this package registers every rule."""

from iati_scout.quality.rules import (  # noqa: F401
    classification,
    dates,
    finance,
    hierarchy,
    organisations,
    results,
    text_location,
)
