import os
import json
import secrets
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

LINKS_FILE = 'links.json'

def load_links():
    try:
        with open(LINKS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_links(links):
    with open(LINKS_FILE, 'w') as f:
        json.dump(links, f)

@dp.message_handler(commands=['start'])
async def start_cmd(message: Message):
    await message.answer(
        "📍 Создай ссылку и узнай где человек\n\n"
        "Нажми кнопку 👇",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔗 Создать ссылку", callback_data="create")
        )
    )

@dp.callback_query_handler(lambda c: c.data == "create")
async def create_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    code = secrets.token_hex(6)
    
    links = load_links()
    links[code] = user_id
    save_links(links)
    
    # Ссылка на GitHub Pages
    link = f"https://{os.getenv('GITHUB_USERNAME')}.github.io/{os.getenv('REPO_NAME')}/?code={code}"
    
    await callback.message.answer(
        f"✅ Твоя ссылка готова!\n\n"
        f"🔗 {link}\n\n"
        f"📤 Отправь человеку и получи его карту!"
    )
    await callback.answer()

@dp.message_handler(commands=['stats'])
async def stats_cmd(message: Message):
    links = load_links()
    await message.answer(f"📊 Активных ссылок: {len(links)}")

if __name__ == '__main__':
    executor.start_polling(bot)