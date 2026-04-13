import json
import asyncio
from pathlib import Path

from telethon import TelegramClient, events
from telethon.events import Album

from xai_sdk import Client
from xai_sdk.chat import user, system


# ────────────────────────────────────────────────
# ĐỌC CONFIG
# ────────────────────────────────────────────────
CONFIG_PATH = Path("config.json")

if not CONFIG_PATH.is_file():
    raise FileNotFoundError("Không tìm thấy file config.json. Hãy tạo file theo mẫu.")

with CONFIG_PATH.open(encoding="utf-8") as f:
    config = json.load(f)

# Telegram
tg_cfg = config["telegram"]
API_ID = tg_cfg["api_id"]
API_HASH = tg_cfg["api_hash"]
PHONE = tg_cfg["phone"]
SESSION_NAME = tg_cfg["session_name"]

# xAI / Grok
xai_cfg = config["xai"]
XAI_API_KEY = xai_cfg["api_key"]
XAI_MODEL = xai_cfg["model"]
XAI_REASONING_EFFORT = xai_cfg["reasoning_effort"]
XAI_TIMEOUT = xai_cfg["timeout"]

# Destination & Sources
SOURCE_CONFIG = config["source_channels"]
SOURCE_CHATS = list(SOURCE_CONFIG.keys())

# ────────────────────────────────────────────────
# Khởi tạo clients
# ────────────────────────────────────────────────
telegram_client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

xai_client = Client(
    api_key=XAI_API_KEY,
    timeout=XAI_TIMEOUT,
)


# ────────────────────────────────────────────────
# Dịch văn bản bằng Grok
# ────────────────────────────────────────────────
async def translate_to_vietnamese(text: str, prompt: str) -> str:
    if not text or not text.strip():
        return text

    print(f"→ Dịch: {text[:60]}{'...' if len(text) > 60 else ''}")

    try:
        chat = xai_client.chat.create(
            model=XAI_MODEL,
            reasoning_effort=XAI_REASONING_EFFORT,
            store_messages=False
        )

        chat.append(system(prompt))
        chat.append(user(text))

        response = chat.sample()
        translated = response.content.strip()

        print(f"   → Kết quả: {translated[:60]}{'...' if len(translated) > 60 else ''}\n")
        return translated or text

    except Exception as e:
        print(f"❌ Lỗi dịch Grok: {type(e).__name__} → {e}")
        return text


# ────────────────────────────────────────────────
# Helper: Forward (text hoặc media) với nội dung đã dịch
# ────────────────────────────────────────────────
async def forward_safe(destination, source_message, prompt, original_text="", template="{}"):
    text_to_translate = original_text or source_message.text or source_message.caption or ""
    translated = await translate_to_vietnamese(text_to_translate, prompt)
    try:
        formatted = template.format(translated)
    except Exception:
        formatted = translated

    # Check if media is a web page preview (MessageMediaWebPage)
    from telethon.tl.types import MessageMediaWebPage
    if source_message.media:
        if isinstance(source_message.media, MessageMediaWebPage):
            # Just send as text, not as file
            return await telegram_client.send_message(
                entity=destination,
                message=formatted,
                link_preview=True,
            )
        else:
            return await telegram_client.send_file(
                entity=destination,
                file=source_message.media,
                caption=formatted,
                link_preview=True,
            )
    else:
        return await telegram_client.send_message(
            entity=destination,
            message=formatted,
            link_preview=True,
        )


# ────────────────────────────────────────────────
# Album handler
# ────────────────────────────────────────────────
@telegram_client.on(events.Album(chats=SOURCE_CHATS))
async def album_handler(event: Album.Event):
    chat = await event.get_chat()
    chat_id = str(event.chat_id)
    username = getattr(chat, "username", None)

    cfg = SOURCE_CONFIG.get(chat_id) or \
          (SOURCE_CONFIG.get(f"@{username}") if username else None) or \
          (SOURCE_CONFIG.get(username) if username else None)

    if not cfg:
        return

    caption = event.text or ""
    if not caption.strip():
        return

    keywords = cfg["keywords"]
    min_matches = cfg.get("min_matches", 1)

    matched = ["ALL"] if not keywords else \
              [kw for kw in keywords if kw.lower() in caption.lower()]

    if keywords and len(matched) < min_matches:
        return

    media_files = [m.media for m in event.messages if m.media]
    if not media_files:
        return

    try:
        dest_channel = cfg.get("destination_channel")
        prompt = cfg.get("prompt", "Dịch sang tiếng Việt.")
        template = cfg.get("template", "{}")
        translated_caption = await translate_to_vietnamese(caption, prompt)
        try:
            formatted_caption = template.format(translated_caption)
        except Exception:
            formatted_caption = translated_caption
        sent = await telegram_client.send_file(
            entity=dest_channel,
            file=media_files,
            caption=formatted_caption,
            link_preview=True,
        )
        source_name = chat.title or username or chat_id
        print(f"→ ALBUM forwarded | {source_name} | "
              f"kw: {', '.join(matched)} | media: {len(media_files)} | dest id: {sent.id if not isinstance(sent, list) else sent[0].id}")
    except Exception as e:
        print(f"❌ Album error {chat_id}: {type(e).__name__} → {e}")


# ────────────────────────────────────────────────
# Single message handler
# ────────────────────────────────────────────────
@telegram_client.on(events.NewMessage(chats=SOURCE_CHATS))
async def single_handler(event):
    if event.grouped_id:
        return

    chat = await event.get_chat()
    chat_id = str(event.chat_id)
    username = getattr(chat, "username", None)

    cfg = SOURCE_CONFIG.get(chat_id) or \
          (SOURCE_CONFIG.get(f"@{username}") if username else None) or \
          (SOURCE_CONFIG.get(username) if username else None)

    if not cfg:
        return

    msg = event.message
    content = msg.text or (msg.caption if msg.media else "")
    if not content or not content.strip():
        return

    keywords = cfg["keywords"]
    min_matches = cfg.get("min_matches", 1)

    matched = ["ALL"] if not keywords else \
              [kw for kw in keywords if kw.lower() in content.lower()]

    if keywords and len(matched) < min_matches:
        return

    try:
        dest_channel = cfg.get("destination_channel")
        prompt = cfg.get("prompt", "Dịch sang tiếng Việt.")
        template = cfg.get("template", "{}")
        sent = await forward_safe(dest_channel, msg, prompt, content, template)
        source_name = chat.title or username or chat_id
        print(f"→ SINGLE forwarded | {source_name} | id {msg.id} | "
              f"kw: {', '.join(matched)} | {'media' if msg.media else 'text'} | dest id: {sent.id}")
    except Exception as e:
        print(f"❌ Single error #{msg.id} {chat_id}: {type(e).__name__} → {e}")


# ────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────
async def main():
    await telegram_client.start(phone=PHONE)
    print("Telegram login OK")

    me = await telegram_client.get_me()
    print(f"Account: {me.first_name} (@{me.username or 'no username'})")

    print("\nTheo dõi nguồn (dịch sang tiếng Việt):")
    for src, cfg in SOURCE_CONFIG.items():
        kw_text = "TẤT CẢ" if not cfg["keywords"] else ", ".join(cfg["keywords"])
        dest_channel = cfg.get("destination_channel", "(chưa cấu hình)")
        print(f"  • {src:22} | {kw_text} (min {cfg.get('min_matches', 1)}) → {dest_channel}")

    print("Đang lắng nghe...\n")

    await telegram_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())