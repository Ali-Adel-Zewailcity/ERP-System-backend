"""
International Mobile Number Validation & Normalization Utility.

Implements a scalable dispatcher pattern allowing multi-country mobile syntax
validation and standardization based on country calling code prefixes.
"""

import re
from typing import Dict, Optional


class CountryMobileValidator:
    def __init__(self, name: str, country_code: str, pattern: str, example: str):
        self.name = name
        self.country_code = country_code
        self.pattern = re.compile(pattern)
        self.example = example

    def validate_and_normalize(self, phone: str) -> Optional[str]:
        """
        Validates the phone string against this country's rules.
        Returns the normalized string for DB storage if valid, else None.
        """
        match = self.pattern.match(phone)
        if match:
            return match.group(1)
        return None


class MobileNumberRegistry:
    def __init__(self):
        self._validators: Dict[str, CountryMobileValidator] = {}

    def register(self, name: str, country_code: str, pattern: str, example: str) -> None:
        """
        Register a country's mobile validation rule.

        `name`: Country name (e.g., 'Egypt')
        `country_code`: Calling code without '+' (e.g., '20')
        `pattern`: Regex pattern where group(1) captures the standardized DB storage format.
        `example`: Example valid syntax.
        """
        self._validators[country_code] = CountryMobileValidator(
            name=name, country_code=country_code, pattern=pattern, example=example
        )

    def parse_and_normalize(self, raw_phone: str) -> str:
        if not isinstance(raw_phone, str):
            raw_phone = str(raw_phone)

        if "+" in raw_phone:
            raise ValueError("The '+' character is not allowed in phone numbers.")

        # Remove spaces and dashes for user convenience
        clean_phone = re.sub(r"[\s\-]", "", raw_phone.strip())

        if not clean_phone.isdigit():
            raise ValueError("Phone number must contain only digits.")

        # 1. Inspect prefix for explicit international country codes
        for code, validator in self._validators.items():
            if clean_phone.startswith(code):
                normalized = validator.validate_and_normalize(clean_phone)
                if normalized:
                    return normalized

        # 2. Inspect against local/storage formats across registered countries
        for validator in self._validators.values():
            normalized = validator.validate_and_normalize(clean_phone)
            if normalized:
                return normalized

        supported = ", ".join(f"{v.name} (+{v.country_code})" for v in self._validators.values())
        raise ValueError(
            f"Invalid mobile number format. Currently supported countries: [{supported}]. "
            "Please check country calling code and mobile number structure."
        )


# Global registry instance
mobile_registry = MobileNumberRegistry()

# Register Egypt (Calling code: 20)
# Matches:
# 1- 201{0,1,2,5}xxxxxxxx (formal 12 digits)
# 2- 01{0,1,2,5}xxxxxxxx (common 11 digits)
# 3- 1{0,1,2,5}xxxxxxxx (storage 10 digits)
# Group 1 extracts 1{0,1,2,5}xxxxxxxx (10 digits) for database storage.
mobile_registry.register(
    name="Egypt",
    country_code="20",
    pattern=r"^(?:20|0)?(1[0125]\d{8})$",
    example="201012345678, 01012345678, or 1012345678",
)

# Example of how easily future countries can be plugged in:
# mobile_registry.register(
#     name="Saudi Arabia",
#     country_code="966",
#     pattern=r"^(?:966|0)?(5\d{8})$",
#     example="966501234567 or 0501234567"
# )
