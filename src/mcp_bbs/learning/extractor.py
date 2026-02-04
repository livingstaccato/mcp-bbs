"""Key-value extraction from screen text using regex patterns."""

from __future__ import annotations

import re
from typing import Any


class KVExtractor:
    """Extract structured key-value data from screen text."""

    @staticmethod
    def extract(screen: str, kv_config: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract key-value data from screen using configured patterns.

        Args:
            screen: Screen text to extract from
            kv_config: Extraction configuration from prompt pattern
                Can be a single field config or list of field configs

        Returns:
            Dictionary of extracted values, None if config invalid or extraction failed
        """
        if not kv_config:
            return None

        # Handle single field config (convert to list)
        if isinstance(kv_config, dict) and "field" in kv_config:
            configs = [kv_config]
        elif isinstance(kv_config, list):
            configs = kv_config
        else:
            return None

        extracted: dict[str, Any] = {}

        for config in configs:
            field_name = config.get("field")
            field_type = config.get("type", "string")
            pattern = config.get("regex")

            if not field_name or not pattern:
                continue

            # Try to extract using regex
            match = re.search(pattern, screen, re.MULTILINE | re.IGNORECASE)
            if not match:
                continue

            # Get captured group (first group or whole match)
            try:
                value_str = match.group(1) if match.lastindex else match.group(0)
            except IndexError:
                value_str = match.group(0)

            # Convert to target type
            try:
                converted_value = KVExtractor._convert_type(value_str, field_type)
                extracted[field_name] = converted_value
            except (ValueError, TypeError):
                # Conversion failed, skip this field
                continue

        return extracted if extracted else None

    @staticmethod
    def _convert_type(value_str: str, target_type: str) -> Any:
        """Convert string value to target type.

        Args:
            value_str: String value to convert
            target_type: Target type name ("string", "int", "float", "bool")

        Returns:
            Converted value

        Raises:
            ValueError: If conversion fails
        """
        value_str = value_str.strip()

        if target_type == "string":
            return value_str

        if target_type == "int":
            return int(value_str)

        if target_type == "float":
            return float(value_str)

        if target_type == "bool":
            # Boolean conversion
            lower_val = value_str.lower()
            if lower_val in ("true", "yes", "y", "1", "on"):
                return True
            if lower_val in ("false", "no", "n", "0", "off"):
                return False
            raise ValueError(f"Cannot convert '{value_str}' to bool")

        # Unknown type, return as string
        return value_str


def extract_kv(screen: str, kv_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convenience function for extracting K/V data.

    Args:
        screen: Screen text
        kv_config: Extraction configuration

    Returns:
        Extracted data or None
    """
    return KVExtractor.extract(screen, kv_config)
