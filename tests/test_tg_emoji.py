"""Offline: DORASUPER_OFFLINE=1 ./venv/bin/python -m unittest discover -s tests -v"""
import ast
import asyncio
import html
import os
from pathlib import Path
import re
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DORASUPER_OFFLINE'] = '1'
import dorasuper
from dorasuper import emoji
from dorasuper.tg_emoji import (
    EMOJI_TAG, to_html, to_unicode, split_button, premium_enabled, install,
    _plain_request, invoke_with_fallback, plain_markup,
)
from dorasuper.tg_keyboard import SCHEMA, STYLED_TYPES
from pyrogram import raw, types
from pyrogram.enums import MessageEntityType
from pyrogram.errors import BadRequest
from pyrogram.parser.html import HTML
from pyrogram.raw.core import TLObject

OLD = '<emoji id="123">👍</emoji>'
NEW = '<tg-emoji emoji-id="123">👍</tg-emoji>'
ROOT = Path(__file__).resolve().parents[1]


def selected_source(path, names, namespace):
    """Load pure plugin helpers without running plugin handlers/DB imports."""
    tree = ast.parse((ROOT / path).read_text())
    selected = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in names or isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    exec(compile(ast.Module(body=selected, type_ignores=[]), path, 'exec'), namespace)
    return namespace


class EmojiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, USE_PREMIUM_EMOJI='true')
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_conversion(self):
        for tag in (OLD, NEW, "<tg-emoji emoji-id='123'>👍</tg-emoji>"):
            self.assertEqual(to_html(tag), NEW)
            self.assertEqual(to_unicode(tag), '👍')
        self.assertEqual(to_unicode('<b>'+NEW+'</b>'), '<b>👍</b>')

    def test_button_split(self):
        self.assertEqual(split_button(OLD+' A &amp; B '+NEW), ('A & B', '123'))
        self.assertEqual(split_button('Plain label'), ('Plain label', None))
        self.assertTrue(split_button(NEW)[0])

    async def test_entities_utf16_and_unparse(self):
        for tag in (OLD, NEW):
            parsed = await HTML(None).parse('😀 <b>'+tag+'</b>')
            self.assertEqual(parsed['message'], '😀 👍')
            custom = next(e for e in parsed['entities'] if isinstance(e, raw.types.MessageEntityCustomEmoji))
            self.assertEqual((custom.offset, custom.length, custom.document_id), (3, 2, 123))
        entity = types.MessageEntity(type=MessageEntityType.CUSTOM_EMOJI, offset=0,
                                     length=2, custom_emoji_id=123)
        self.assertEqual(HTML.unparse('👍', [entity]), NEW)

    async def test_button_types(self):
        cases = [dict(callback_data=b'\xff'), dict(url='https://example.com'),
                 dict(switch_inline_query='q'), dict(switch_inline_query_current_chat='q'),
                 dict(web_app=types.WebAppInfo(url='https://example.com')),
                 dict(callback_game=types.CallbackGame()), dict(user_id=42),
                 dict(login_url=types.LoginUrl(url='https://example.com'))]
        async def resolve(_):
            return raw.types.InputUserSelf()
        client = SimpleNamespace(resolve_peer=resolve)
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                button = types.InlineKeyboardButton(NEW+' Button', **kwargs)
                self.assertEqual(button.text, 'Button')
                self.assertEqual(button.icon_custom_emoji_id, '123')
                wire = await button.write(client)
                self.assertEqual(wire.style.icon, 123)
                decoded = TLObject.read(BytesIO(wire.write()))
                self.assertEqual(decoded.style.icon, 123)
                self.assertEqual(decoded.text, 'Button')
                plain = _plain_request(wire)
                self.assertIsNone(getattr(plain, 'style', None))
                self.assertEqual(plain.text, 'Button')
                if 'callback_data' in kwargs:
                    self.assertEqual(plain.data, b'\xff')
                if 'url' in kwargs:
                    self.assertEqual(plain.url, kwargs['url'])

    async def test_wire_constructor_and_flags(self):
        button = types.InlineKeyboardButton(NEW+' B', callback_data='q')
        wire = (await button.write(None)).write()
        # Official TL: keyboardButtonCallback#e62bc960, style at flags.10;
        # keyboardButtonStyle#4fdd3430, icon at flags.3, then int64 document id.
        self.assertEqual(wire[:24], bytes.fromhex(
            '60c92be6 00040000 3034dd4f 08000000 7b00000000000000'))

    async def test_disabled_request_boundary(self):
        button = types.InlineKeyboardButton(NEW+' B', callback_data='q')
        query = raw.functions.messages.SendMessage(
            peer=raw.types.InputPeerSelf(), message='👍', random_id=7,
            entities=[raw.types.MessageEntityCustomEmoji(offset=0, length=2, document_id=123)],
            reply_markup=raw.types.ReplyInlineMarkup(rows=[raw.types.KeyboardButtonRow(
                buttons=[await button.write(None)])]))
        calls = []
        async def invoke(client, request):
            calls.append(request)
            return 'ok'
        with patch.dict(os.environ, USE_PREMIUM_EMOJI='false'):
            self.assertEqual(await invoke_with_fallback(invoke, None, query), 'ok')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].entities, [])
        self.assertIsNone(getattr(calls[0].reply_markup.rows[0].buttons[0], 'style', None))

    def test_button_format_preserves_tags(self):
        ns = selected_source('dorasuper/helper/emoji_fmt.py',
            {'EMOJI_FMT', 'EMOJI_FMT_BTN'}, dict(vars(emoji)))
        self.assertEqual(ns['EMOJI_FMT_BTN'], ns['EMOJI_FMT'])
        label = '{E_MENU} Menu'.format(**ns['EMOJI_FMT_BTN'])
        button = types.InlineKeyboardButton(label, callback_data='menu')
        self.assertEqual(button.text, 'Menu')
        self.assertEqual(button.icon_custom_emoji_id, EMOJI_TAG.search(emoji.E_MENU)['id'])

    async def test_explicit_icon_and_read(self):
        b = types.InlineKeyboardButton('Button', callback_data='q', icon_custom_emoji_id='456')
        wire = await b.write(None)
        read = types.InlineKeyboardButton.read(TLObject.read(BytesIO(wire.write())))
        self.assertEqual(read.icon_custom_emoji_id, '456')
        self.assertEqual(read.callback_data, 'q')

    async def test_disabled(self):
        with patch.dict(os.environ, USE_PREMIUM_EMOJI='false'):
            self.assertEqual(split_button(NEW+' Button'), ('👍 Button', None))
            parsed = await HTML(None).parse(NEW)
            self.assertIsNone(parsed['entities'])
            self.assertEqual(parsed['message'], '👍')
            b = types.InlineKeyboardButton(NEW+' Button', callback_data='q', icon_custom_emoji_id='456')
            self.assertIsNone(b.icon_custom_emoji_id)
            self.assertIsNone(getattr(await b.write(None), 'style', None))

    async def test_rejected_icons_retry_once(self):
        b = types.InlineKeyboardButton(NEW+' Button', callback_data='q')
        wire = await b.write(None)
        query = raw.functions.messages.SendMessage(
            peer=raw.types.InputPeerSelf(), message='👍', random_id=99,
            entities=[raw.types.MessageEntityCustomEmoji(offset=0, length=2, document_id=123),
                      raw.types.MessageEntityBold(offset=0, length=2)],
            reply_markup=raw.types.ReplyInlineMarkup(rows=[raw.types.KeyboardButtonRow(buttons=[wire])]))
        calls = []
        async def invoke(client, request):
            calls.append(request)
            if len(calls) == 1:
                raise BadRequest('BUTTON_ICON_INVALID')
            return 'sent'
        self.assertEqual(await invoke_with_fallback(invoke, None, query), 'sent')
        self.assertEqual(len(calls), 2)
        plain = calls[1]
        self.assertEqual(plain.random_id, 99)
        self.assertEqual(plain.message, '👍')
        self.assertEqual(len(plain.entities), 1)
        self.assertIsInstance(plain.entities[0], raw.types.MessageEntityBold)
        self.assertIsNone(getattr(plain.reply_markup.rows[0].buttons[0], 'style', None))
        self.assertEqual(query.reply_markup.rows[0].buttons[0].style.icon, 123)

    async def test_no_retry_unrelated_errors(self):
        calls = []
        async def invoke(*args):
            calls.append(1)
            raise TimeoutError('no duplicate sends')
        with self.assertRaises(TimeoutError):
            await invoke_with_fallback(invoke, None, raw.types.InputPeerSelf())
        self.assertEqual(len(calls), 1)

    def test_markup_copy(self):
        b = types.InlineKeyboardButton(NEW+' B', callback_data='payload')
        m = types.InlineKeyboardMarkup([[b]])
        plain = plain_markup(m)
        self.assertIsNone(plain.inline_keyboard[0][0].icon_custom_emoji_id)
        self.assertEqual(b.icon_custom_emoji_id, '123')
        self.assertEqual(b.text, 'B')  # icon applied → no unicode prefix
        self.assertEqual(plain.inline_keyboard[0][0].text, '👍 B')  # fallback unicode
        self.assertEqual(plain.inline_keyboard[0][0].callback_data, 'payload')

    def test_idempotent(self):
        before = types.InlineKeyboardButton.__init__
        install()
        self.assertIs(before, types.InlineKeyboardButton.__init__)

    def test_all_constants_canonical(self):
        for name, value in vars(emoji).items():
            if name.startswith('E_'):
                for item in value if isinstance(value, (list, tuple)) else [value]:
                    if isinstance(item, str):
                        self.assertNotIn('<emoji', item)
                        self.assertEqual(to_html(item), item)

    def test_checkin_helpers(self):
        ns = selected_source('dorasuper/plugins/checkin.py',
            {'_html_to_entities', '_utf16_len', '_html_drop_custom_emoji'},
            dict(re=re, html=html, EMOJI_TAG=EMOJI_TAG, to_unicode=to_unicode,
                 premium_enabled=premium_enabled, MessageEntity=types.MessageEntity,
                 enums=SimpleNamespace(MessageEntityType=MessageEntityType)))
        for tag in (OLD, NEW):
            text, entities = ns['_html_to_entities']('😀 '+tag)
            self.assertEqual(text, '😀 👍')
            self.assertEqual((entities[0].offset, entities[0].length), (3, 2))
            self.assertEqual(ns['_html_drop_custom_emoji'](tag), '👍')

    def test_ai_helpers(self):
        ns = selected_source('dorasuper/plugins/ai.py',
            {'_RE_EMOJI_TAG', '_normalize_emoji_tag', '_flatten_nested_emoji',
             '_replace_unicode_emoji_with_custom', '_strip_unknown_custom_emoji'},
            dict(re=re, _ALLOWED_EMOJI_IDS={'123'}, _UNICODE_EMOJI_TO_CUSTOM={'👍':NEW}))
        for tag in (OLD, NEW):
            self.assertEqual(ns['_strip_unknown_custom_emoji'](tag), tag)
            self.assertEqual(ns['_strip_unknown_custom_emoji'](tag.replace('123', '999')), '👍')
            self.assertEqual(ns['_replace_unicode_emoji_with_custom'](tag+' 👍'), tag+' '+NEW)
            nested = '<tg-emoji emoji-id="999">'+tag+'</tg-emoji>'
            self.assertEqual(ns['_flatten_nested_emoji'](nested), tag)


if __name__ == '__main__':
    unittest.main()
