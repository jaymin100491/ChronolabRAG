"""Input parsers for plain JSON timelines and FHIR R4 Bundles."""

from chronolab_rag.parsers.fhir_bundle import parse_fhir_bundle
from chronolab_rag.parsers.simple_json import parse_simple_json

__all__ = ["parse_fhir_bundle", "parse_simple_json"]
