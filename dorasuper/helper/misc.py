from math import ceil

from pyrogram.types import InlineKeyboardButton

from dorasuper import MOD_LOAD, MOD_NOLOAD


# skipcq: PYL-W1641
class EqInlineKeyboardButton(InlineKeyboardButton):
    def __eq__(self, other):
        return self.text == other.text

    def __lt__(self, other):
        return self.text < other.text

    def __gt__(self, other):
        return self.text > other.text


def paginate_modules(page_n, module_dict, prefix, chat=None):
    # Dùng index thay vì tên module để callback_data luôn < 64 byte (giới hạn Telegram)
    ordered_keys = sorted(module_dict.keys(), key=lambda k: (module_dict[k].__MODULE__ or ""))
    modules = [
        EqInlineKeyboardButton(
            module_dict[k].__MODULE__,
            callback_data=f"{prefix}_module({chat},{i})" if chat is not None else f"{prefix}_module({i})",
        )
        for i, k in enumerate(ordered_keys)
    ]
    modules = sorted(modules)

    pairs = list(zip(modules[::3], modules[1::3], modules[2::3]))
    remainder = len(modules) % 3
    if remainder == 1:
        pairs.append((modules[-1],))
    elif remainder == 2:
        pairs.append((modules[-2], modules[-1]))

    COLUMN_SIZE = 4

    max_num_pages = ceil(len(pairs) / COLUMN_SIZE)
    modulo_page = page_n % max_num_pages

    # can only have a certain amount of buttons side by side
    if len(pairs) > COLUMN_SIZE:
        pairs = pairs[modulo_page * COLUMN_SIZE : COLUMN_SIZE * (modulo_page + 1)] + [
            (
                EqInlineKeyboardButton(
                    "❮", callback_data=f"{prefix}_prev({modulo_page})"
                ),
                EqInlineKeyboardButton(
                    "Trở lại", callback_data=f"{prefix}_home({modulo_page})"
                ),
                EqInlineKeyboardButton(
                    "❯", callback_data=f"{prefix}_next({modulo_page})"
                ),
            )
        ]
    else:
        pairs = pairs[modulo_page * COLUMN_SIZE : COLUMN_SIZE * (modulo_page + 1)] + [
            (
                EqInlineKeyboardButton(
                    "Trở lại", callback_data=f"{prefix}_home({modulo_page})"
                ),
            )
        ]

    return pairs


def is_module_loaded(name):
    return (not MOD_LOAD or name in MOD_LOAD) and name not in MOD_NOLOAD
