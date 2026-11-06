"""Small TL compatibility shim, not a replacement Telegram client.

Constructors/field order copied from https://core.telegram.org/schema/json
(accessed 2026-11-06). Old constructors remain registered for old-layer replies.
Only styled outgoing buttons use the new constructors; no global layer bump.
"""
from pyrogram import raw
from pyrogram.raw.all import objects
from pyrogram.raw.core import TLObject, Int, Long, String, Bytes, Bool, Vector

# (constructor id, ordered TL fields); flags.10 holds KeyboardButtonStyle.
SCHEMA = {'KeyboardButton': (2098662655,
                    [('flags', '#'),
                     ('style', 'flags.10?KeyboardButtonStyle'),
                     ('text', 'string')]),
 'KeyboardButtonUrl': (3624674796,
                       [('flags', '#'),
                        ('style', 'flags.10?KeyboardButtonStyle'),
                        ('text', 'string'),
                        ('url', 'string')]),
 'KeyboardButtonCallback': (3861629280,
                            [('flags', '#'),
                             ('requires_password', 'flags.0?true'),
                             ('style', 'flags.10?KeyboardButtonStyle'),
                             ('text', 'string'),
                             ('data', 'bytes')]),
 'KeyboardButtonRequestPhone': (1098841487,
                                [('flags', '#'),
                                 ('style', 'flags.10?KeyboardButtonStyle'),
                                 ('text', 'string')]),
 'KeyboardButtonRequestGeoLocation': (2856384845,
                                      [('flags', '#'),
                                       ('style', 'flags.10?KeyboardButtonStyle'),
                                       ('text', 'string')]),
 'KeyboardButtonSwitchInline': (2568198652,
                                [('flags', '#'),
                                 ('same_peer', 'flags.0?true'),
                                 ('style', 'flags.10?KeyboardButtonStyle'),
                                 ('text', 'string'),
                                 ('query', 'string'),
                                 ('peer_types', 'flags.1?Vector<InlineQueryPeerType>')]),
 'KeyboardButtonGame': (2311426297,
                        [('flags', '#'),
                         ('style', 'flags.10?KeyboardButtonStyle'),
                         ('text', 'string')]),
 'KeyboardButtonBuy': (1067792645,
                       [('flags', '#'),
                        ('style', 'flags.10?KeyboardButtonStyle'),
                        ('text', 'string')]),
 'KeyboardButtonUrlAuth': (4111468281,
                           [('flags', '#'),
                            ('style', 'flags.10?KeyboardButtonStyle'),
                            ('text', 'string'),
                            ('fwd_text', 'flags.0?string'),
                            ('url', 'string'),
                            ('button_id', 'int')]),
 'InputKeyboardButtonUrlAuth': (1744911986,
                                [('flags', '#'),
                                 ('request_write_access', 'flags.0?true'),
                                 ('style', 'flags.10?KeyboardButtonStyle'),
                                 ('text', 'string'),
                                 ('fwd_text', 'flags.1?string'),
                                 ('url', 'string'),
                                 ('bot', 'InputUser')]),
 'KeyboardButtonRequestPoll': (2047989634,
                               [('flags', '#'),
                                ('style', 'flags.10?KeyboardButtonStyle'),
                                ('quiz', 'flags.0?Bool'),
                                ('text', 'string')]),
 'InputKeyboardButtonUserProfile': (2103314375,
                                    [('flags', '#'),
                                     ('style', 'flags.10?KeyboardButtonStyle'),
                                     ('text', 'string'),
                                     ('user_id', 'InputUser')]),
 'KeyboardButtonUserProfile': (3237829897,
                               [('flags', '#'),
                                ('style', 'flags.10?KeyboardButtonStyle'),
                                ('text', 'string'),
                                ('user_id', 'long')]),
 'KeyboardButtonWebView': (3896947104,
                           [('flags', '#'),
                            ('style', 'flags.10?KeyboardButtonStyle'),
                            ('text', 'string'),
                            ('url', 'string')]),
 'KeyboardButtonSimpleWebView': (3780920176,
                                 [('flags', '#'),
                                  ('style', 'flags.10?KeyboardButtonStyle'),
                                  ('text', 'string'),
                                  ('url', 'string')]),
 'KeyboardButtonRequestPeer': (1527715317,
                               [('flags', '#'),
                                ('style', 'flags.10?KeyboardButtonStyle'),
                                ('text', 'string'),
                                ('button_id', 'int'),
                                ('peer_type', 'RequestPeerType'),
                                ('max_quantity', 'int')]),
 'InputKeyboardButtonRequestPeer': (45580630,
                                    [('flags', '#'),
                                     ('name_requested', 'flags.0?true'),
                                     ('username_requested', 'flags.1?true'),
                                     ('photo_requested', 'flags.2?true'),
                                     ('style', 'flags.10?KeyboardButtonStyle'),
                                     ('text', 'string'),
                                     ('button_id', 'int'),
                                     ('peer_type', 'RequestPeerType'),
                                     ('max_quantity', 'int')]),
 'KeyboardButtonCopy': (3167006480,
                        [('flags', '#'),
                         ('style', 'flags.10?KeyboardButtonStyle'),
                         ('text', 'string'),
                         ('copy_text', 'string')]),
 'KeyboardButtonStyle': (1339896880,
                         [('flags', '#'),
                          ('bg_primary', 'flags.0?true'),
                          ('bg_danger', 'flags.1?true'),
                          ('bg_success', 'flags.2?true'),
                          ('icon', 'flags.3?long')])}

_PRIMITIVES = {"int": Int, "long": Long, "string": String, "bytes": Bytes, "Bool": Bool}
STYLED_TYPES = {}


def _read_value(stream, kind):
    if kind.startswith("Vector<"):
        stream.read(4)  # vector constructor
        return Vector.read(stream)
    primitive = _PRIMITIVES.get(kind)
    return primitive.read(stream) if primitive else TLObject.read(stream)


def _write_value(value, kind):
    if kind.startswith("Vector<"):
        return Vector(value)
    primitive = _PRIMITIVES.get(kind)
    return primitive(value) if primitive else value.write()


def install_raw_types():
    if STYLED_TYPES:
        return
    for name, (constructor, fields) in SCHEMA.items():
        old = getattr(raw.types, name, TLObject)
        slots = [key for key, kind in fields if kind != "#"]

        def init(self, **kwargs):
            for key in self.__slots__:
                setattr(self, key, kwargs.pop(key, None))
            if kwargs:
                raise TypeError(f"Unexpected TL fields: {tuple(kwargs)}")

        def write(self, *args):
            flags = 0
            for key, kind in self._fields:
                if "?" in kind:
                    bit = int(kind.split("?")[0].split(".")[1])
                    value = getattr(self, key)
                    if value is not None and (not kind.endswith("?true") or value):
                        flags |= 1 << bit
            data = self.ID.to_bytes(4, "little") + Int(flags)
            for key, kind in self._fields:
                if kind == "#":
                    continue
                if "?" in kind:
                    flag, kind = kind.split("?")
                    if not flags & (1 << int(flag.split(".")[1])):
                        continue
                if kind != "true":
                    data += _write_value(getattr(self, key), kind)
            return data

        @classmethod
        def read(cls, stream, *args):
            flags = Int.read(stream)
            values = {}
            for key, kind in cls._fields:
                if kind == "#":
                    continue
                if "?" in kind:
                    flag, kind = kind.split("?")
                    present = bool(flags & (1 << int(flag.split(".")[1])))
                    if kind == "true":
                        values[key] = present
                        continue
                    if not present:
                        values[key] = None
                        continue
                values[key] = _read_value(stream, kind)
            return cls(**values)

        cls = type(name, (old,), {
            "ID": constructor, "QUALNAME": f"types.{name}",
            "__slots__": slots, "_fields": fields,
            "__init__": init, "read": read, "write": write,
            "_legacy_type": old,
        })
        STYLED_TYPES[name] = cls
        # Do not overwrite an already-native constructor on newer libraries.
        objects.setdefault(constructor, cls)
    if not hasattr(raw.types, "KeyboardButtonStyle"):
        raw.types.KeyboardButtonStyle = STYLED_TYPES["KeyboardButtonStyle"]


def with_icon(button, icon):
    """Retain the exact action/payload, adding only the official style field."""
    if hasattr(button, "style"):
        button.style = raw.types.KeyboardButtonStyle(icon=int(icon))
        return button
    cls = STYLED_TYPES.get(type(button).__name__)
    if cls is None:
        raise TypeError(f"Unsupported keyboard button: {type(button).__name__}")
    values = {key: getattr(button, key, None) for key in cls.__slots__}
    values["style"] = raw.types.KeyboardButtonStyle(icon=int(icon))
    return cls(**values)


def without_style(button):
    old = getattr(type(button), "_legacy_type", None)
    if old is not None and old is not TLObject:
        return old(**{key: getattr(button, key, None) for key in old.__slots__})
    from copy import copy
    button = copy(button)
    button.style = None
    return button
