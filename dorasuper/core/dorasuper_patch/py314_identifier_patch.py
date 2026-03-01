"""
Python 3.14 compatibility: Pyrogram's Identifier uses __annotations__, which
is not set on dataclass instances under PEP 649. We patch Identifier to use
dataclasses.fields() so callback_query handlers work on 3.14.
"""
import dataclasses
import sys

if sys.version_info >= (3, 14):
    from pyrogram.types.pyromod.identifier import Identifier

    def _identifier_fields(self):
        return [f.name for f in dataclasses.fields(self)]

    def _matches(self, update) -> bool:
        for field in _identifier_fields(self):
            pattern_value = getattr(self, field)
            update_value = getattr(update, field)
            if pattern_value is not None:
                if isinstance(update_value, list):
                    if isinstance(pattern_value, list):
                        if not set(update_value).intersection(set(pattern_value)):
                            return False
                    elif pattern_value not in update_value:
                        return False
                elif isinstance(pattern_value, list):
                    if update_value not in pattern_value:
                        return False
                elif update_value != pattern_value:
                    return False
        return True

    def _count_populated(self):
        return sum(1 for f in _identifier_fields(self) if getattr(self, f) is not None)

    Identifier.matches = _matches
    Identifier.count_populated = _count_populated
