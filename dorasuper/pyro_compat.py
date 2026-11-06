"""Fill missing pyrogram.errors names used by this bot but absent from the installed pyrofork."""
from pyrogram.errors import BadRequest, Forbidden, RPCError


_MISSING = {
    "ChatSendPlainForbidden": Forbidden,
    "ChatSendPhotosForbidden": Forbidden,
    "TopicClosed": BadRequest,
    "ListenerTimeout": RPCError,
}


def install():
    import pyrogram.errors as errors

    for name, base in _MISSING.items():
        if not hasattr(errors, name):
            setattr(errors, name, type(name, (base,), {"ID": name, "NAME": name}))
