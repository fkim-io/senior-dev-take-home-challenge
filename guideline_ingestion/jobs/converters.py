"""
Custom URL converters for jobs API.

Provides flexible UUID conversion that handles both uppercase and lowercase UUIDs.
"""

import uuid
from django.urls.converters import UUIDConverter


class CaseInsensitiveUUIDConverter(UUIDConverter):
    """
    UUID converter that accepts both uppercase and lowercase UUIDs.
    
    Django's default UUIDConverter only accepts lowercase UUIDs,
    but this converter normalizes to lowercase and accepts both cases.
    """
    
    regex = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    
    def to_python(self, value):
        """Convert URL string to UUID object, normalizing case."""
        # Normalize to lowercase before creating UUID
        normalized_value = value.lower()
        return uuid.UUID(normalized_value)
    
    def to_url(self, value):
        """Convert UUID object to URL string (always lowercase)."""
        return str(value).lower()