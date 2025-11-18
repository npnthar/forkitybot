import asyncio
import random
import logging
import os
import json
import dateparser
from datetime import datetime
import tempfile
from threading import Thread

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType, FSInputFile
from aiogram.client.default import DefaultBotProperties

from groq import Groq
from flask import Flask

# Stability AI
from stability_sdk import client
from stability_sdk.interfaces.gooseai.generation import generation_pb2

# --- Логирование ---
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
TOKEN = os.getenv("TG_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STABILITY_KEY = os.getenv("STABILITY_API_KEY")
MY_HUGS_CHANNEL = os.getenv("MY_HUGS_CHANNEL") or "@forkity"

if not STABILITY_KEY:
    raise ValueError("Не задан STABILITY_API_KEY. Проверь переменные окружения.")

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# --- База фото ---
hugs_file_ids = []

def save_photos_db():
    # сохраняем список фото в json (можно подключить db или файл)
    with open("hugs_file_ids.json", "w", encoding="utf-8") as f:
        json.dump(hugs_file_ids, f, ensure_ascii=False)


async def load_initial_photos():
    global hugs_file_ids
    try:
        with open('hugs_file_ids.json', 'r', encoding='utf-8') as f:
            hugs_file_ids = json.load(f)
            logger.info(f"Загружено {len(hugs_file_ids)} фотографий в базу")
    except FileNotFoundError:
        logger.warning("Файл с начальными фотографиями не найден")
    except Exception as e:
        logger.error(f"Ошибка загрузки начальных фотографий: {e}")


# --- Клавиатура ---
def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🫂 Обнять", callback_data="hug"),
            InlineKeyboardButton(text="💞 Комплимент", callback_data="cute")
        ],
        [
            InlineKeyboardButton(text="✨ Факт", callback_data="fact"),
            InlineKeyboardButton(text="🤖 Подскажи", callback_data="ask")
        ],
        [
            InlineKeyboardButton(text="⏰ Напомни", callback_data="remind"),
            InlineKeyboardButton(text="🎮 Brawl Stars", callback_data="brawl")
        ],
        [
            InlineKeyboardButton(text="🖼️ Нарисуй", callback_data="draw")
        ]
    ])

# --- Тексты hug / cute / morning / night ---
hug_texts = [
    "Крепко обнимаю — ты не одна.",
    "Тебе можно немного передохнуть, я рядом, пусть и через телефон.",
    "Всегда думаю о тебе.", "Я всегда рядом с тобой.",
    "Очень хочу тебя обнять.", "Всегда буду тебя поддерживать.",
    "Обнимаю крепко-крепко.", "Ты справляешься лучше, чем думаешь.",
    "Обнимаю, чтобы стало теплее на душе.",
    "Виртуальные обнимаю самую милую девочку.", "Ты не одна, я с тобой.",
    "Обнимаю так, будто рядом.", "Пусть у тебя всё всегда будет хорошо.",
    "Обнимаю с заботой и нежностью.", "Считай, что я рядом и обнимаю.",
    "Обнимаю и поддерживаю.", "Обнимаю, чтобы стало легче.",
    "Обниму крепко, даже на расстоянии.", "Обнимаю мысленно, но с теплом.",
    "Обнимаю, чтобы день стал легче.", "Обнимаю с искренней заботой.",
    "Обнимаю крепко, чтобы стало легче.", "Мысленно обнимаю тебя 💖."
]

cute_texts = [
    "Ты очень милая, красивая и добрая — ты самая крутая девочка на свете.",
    "У тебя такая добрая душа и красивая улыбка.",
    "Ты невероятно талантливая и умная.",
    "Твоя доброта делает этот мир лучше.",
    "Ты справляешься с трудностями — это вызывает восхищение.",
    "У тебя потрясающее чувство юмора.",
    "Ты такая сильная и одновременно нежная.",
    "Твоя искренность — это настоящее сокровище.",
    "Ты умеешь дарить радость окружающим.",
    "У тебя удивительная способность видеть красоту в простых вещах.",
    "Ты очень заботливая и внимательная.",
    "Твоя улыбка может скрасить любой день.", "Ты вдохновляешь быть лучше.",
    "У тебя золотое сердце.", "Ты такая целеустремленная и упорная.",
    "Твоя честность и открытость подкупают.",
    "Ты умеешь находить выход из сложных ситуаций.",
    "У тебя прекрасный вкус во всем.",
    "Ты настоящая, без масок и притворства.",
    "Твоя энергия заряжает позитивом.",
    "Ты умеешь быть собой — это очень ценно.",
    "У тебя удивительная внутренняя красота.",
    "Ты делаешь мир вокруг себя добрее.", "Ты очень чуткая и понимающая.",
    "Ты умеешь радоваться мелочам.",
    "Ты просто замечательная такая, какая есть."
]

MORNING = [
    "Доброе утро! Надеюсь, день будет хорошим и спокойным.",
    "Просыпайся — пусть сегодня будет немного светлее.",
    "Небольшая поддержка перед днём: у тебя всё получится, ты умничка.",
    "С добрым утром! Пусть день будет полон приятных моментов.",
    "Доброе утро! Верю в тебя и твои силы."
]

NIGHT = [
    "Спокойной ночи — отдохни и выспись.",
    "Пусть тебе приснится что-то приятное.",
    "Закрывай глазки — ты хорошо сегодня потрудилась.",
    "Сладких снов! Завтра будет новый замечательный день.",
    "Спокойной ночи! Ты заслужила хороший отдых."
]

# --- FSM для напоминаний / Ask / Draw ---
class Remind(StatesGroup):
    waiting_text = State()
    waiting_time = State()


class Ask(StatesGroup):
    waiting = State()


class Draw(StatesGroup):
    waiting_prompt = State()


# --- Функция отправки hug с фото ---
async def send_hug_with_photo(chat_id: int, text: str):
    if not hugs_file_ids:
        await bot.send_message(
            chat_id,
            text + "\n\n(пока нет картинок — отправь новую картинку)",
            reply_markup=kb())
        return

    file_id = random.choice(hugs_file_ids)
    try:
        await bot.send_photo(chat_id, file_id, caption=text, reply_markup=kb())
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        try:
            hugs_file_ids.remove(file_id)
            save_photos_db()
        except Exception:
            pass
        await bot.send_message(chat_id, text, reply_markup=kb())


# --- Обработка фото/видео из канала ---
@dp.channel_post()
async def on_channel_post(message: types.Message):
    global hugs_file_ids
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.animation:
            file_id = message.animation.file_id
        elif message.video and getattr(message.video, 'duration', 0) < 30:
            file_id = message.video.file_id
        else:
            return

        if file_id not in hugs_file_ids:
            hugs_file_ids.append(file_id)
            save_photos_db()
    except Exception as e:
        logger.error(f"Ошибка в on_channel_post: {e}")


# --- Сохранение фото в ЛС ---
@dp.message(F.content_type == ContentType.PHOTO)
async def save_photo_dm(message: types.Message):
    global hugs_file_ids
    file_id = message.photo[-1].file_id
    if file_id not in hugs_file_ids:
        hugs_file_ids.append(file_id)
        save_photos_db()
        await message.answer("Фото сохранено в коллекцию ❤️")
    else:
        await message.answer("Эта фотография уже в коллекции 😊")


# --- Команды ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я буду поддерживать, помогать и радовать картинками.\n\nНажми кнопки ниже — и я отвечу.",
        reply_markup=kb())


@dp.message(Command("pics"))
async def cmd_pics(message: types.Message):
    await message.answer(f"В базе фото: {len(hugs_file_ids)}")


# --- Кнопки hug / cute ---
@dp.callback_query(F.data == "hug")
async def cb_hug(call: types.CallbackQuery):
    await call.answer()
    await send_hug_with_photo(call.message.chat.id, random.choice(hug_texts))


@dp.callback_query(F.data == "cute")
async def cb_cute(call: types.CallbackQuery):
    await call.answer()
    await send_hug_with_photo(call.message.chat.id, random.choice(cute_texts))


# --- Groq fact ---
@dp.callback_query(F.data == "fact")
async def cb_fact(call: types.CallbackQuery):
    await call.answer()
    try:
        client_groq = Groq(api_key=GROQ_API_KEY)
        resp = client_groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.8,
            max_tokens=120,
            messages=[{
                "role": "system",
                "content": "Генерируй короткий, интересный факт без романтических обращений."
            }, {
                "role": "user",
                "content": "Дай один случайный факт."
            }])
        fact_text = resp.choices[0].message.content.strip()
        await call.message.answer("✨ " + fact_text, reply_markup=kb())
    except Exception as e:
        logger.error(f"Groq fact error: {e}")
        await call.message.answer("Не получилось получить факт, попробуй чуть позже.", reply_markup=kb())


# --- Groq chat (Ask) ---
@dp.callback_query(F.data == "ask")
async def ask_start(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Задай любой вопрос — я отвечу.")
    await state.set_state(Ask.waiting)


@dp.message(Ask.waiting)
async def ask_answer(message: types.Message, state: FSMContext):
    await message.answer("Думаю... ✨")
    try:
        client_groq = Groq(api_key=GROQ_API_KEY)
        resp = client_groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=600,
            messages=[{
                "role": "system",
                "content": ("Ты — внимательный и мягкий собеседник. "
                            "Не используй обращения вроде 'любимая', 'солнышко'. "
                            "Отвечай спокойно и поддерживающе.")
            }, {
                "role": "user",
                "content": message.text
            }])
        answer_text = resp.choices[0].message.content.strip()
        await message.answer(answer_text, reply_markup=kb())
    except Exception as e:
        logger.error(f"Groq chat error: {e}")
        await message.answer("Что-то пошло не так — попробуй ещё раз позже.")
    await state.clear()


# --- Brawl Stars с уведомлением ---
@dp.callback_query(F.data == "brawl")
async def cb_brawl(call: types.CallbackQuery):
    await call.answer()
    try:
        await bot.send_message(473191209, "Катя зовёт играть!!! ❤️❤️❤️")
        await call.message.answer("Хочешь играть? Уже отправил уведомление Паше!!!", reply_markup=kb())
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления Brawl: {e}")
        await call.message.answer("Не удалось отправить уведомление 😔", reply_markup=kb())


# --- Напоминания ---
@dp.callback_query(F.data == "remind")
async def remind_start(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Что мне напомнить?")
    await state.set_state(Remind.waiting_text)


@dp.message(Remind.waiting_text)
async def remind_text(message: types.Message, state: FSMContext):
    await state.update_data(remind_text=message.text)
    await message.answer("Когда прислать напоминание? Например: 'через 10 минут', 'завтра в 18:00', 'в понедельник в 12:30'")
    await state.set_state(Remind.waiting_time)


@dp.message(Remind.waiting_time)
async def remind_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data.get("remind_text")
    remind_dt = dateparser.parse(message.text, settings={'PREFER_DATES_FROM': 'future'})
    if not remind_dt:
        await message.answer("Не смог понять время. Попробуй снова.")
        return
    now = datetime.now()
    delay_seconds = (remind_dt - now).total_seconds()
    if delay_seconds <= 0:
        await message.answer("Время уже прошло. Попробуй снова.")
        return
    await message.answer(f"Хорошо! Я напомню в {remind_dt.strftime('%H:%M %d.%m.%Y')} ✅")
    await state.clear()

    async def send_reminder():
        await asyncio.sleep(delay_seconds)
        try:
            await message.answer(f"Напоминание: {text}")
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания: {e}")

    asyncio.create_task(send_reminder())


# --- Генерация картинок Stability AI ---
async def translate_prompt(text: str) -> str:
    try:
        client_groq = Groq(api_key=GROQ_API_KEY)
        resp = client_groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.25,
            max_tokens=200,
            messages=[{
                "role": "system",
                "content": ("Ты — помощник по подготовке промтов для генерации изображений. "
                            "Переведи текст на английский и сделай лаконичный prompt для SD, "
                            "добавь стиль, освещение, детализацию, если нужно.")
            }, {
                "role": "user",
                "content": text
            }])
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка перевода промта: {e}")
        return text


@dp.callback_query(F.data == "draw")
async def cb_draw_start(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Опиши, что я должен нарисовать (промт):")
    await state.set_state(Draw.waiting_prompt)


@dp.message(Draw.waiting_prompt)
async def draw_image(message: types.Message, state: FSMContext):
    prompt = message.text
    await message.answer("Перевожу промт и генерирую картинку... ⏳")
    await state.clear()
    try:
        prompt_en = await translate_prompt(prompt)
        logger.info(f"Prompt RU: {prompt} -> Prompt EN: {prompt_en}")
        stability_client = client.StabilityInference(
            key=STABILITY_KEY, engine="stable-diffusion-xl-1024-v1-0")
        response = stability_client.generate(
            prompt=prompt_en,
            steps=30,
            cfg_scale=7.0,
            width=512,
            height=512,
            samples=1,
        )
        for resp in response:
            for artifact in resp.artifacts:
                if artifact.type == generation_pb2.ARTIFACT_IMAGE:
                    img_bytes = artifact.binary
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp_file:
                        tmp_file.write(img_bytes)
                        tmp_file.flush()
                        photo_file = FSInputFile(tmp_file.name)
                        caption = f"Вот что получилось по твоему описанию:\n\n«{prompt}»\n\nИспользованный (англ.) промт: «{prompt_en}»"
                        await bot.send_photo(chat_id=message.chat.id, photo=photo_file, caption=caption, reply_markup=kb())
                        return
        await message.answer("Не удалось сгенерировать изображение.", reply_markup=kb())
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
        await message.answer("Что-то пошло не так при генерации. Попробуй другой промт.", reply_markup=kb())


# --- Flask для keep-alive (Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот Катя работает 24/7!"

@app.route('/health')
def health():
    return {"status": "ok", "photos_count": len(hugs_file_ids)}

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()


# --- Запуск бота ---
async def main():
    keep_alive()
    await load_initial_photos()
    scheduler.start()
    logger.info(f"Бот запускается. В базе фото: {len(hugs_file_ids)}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
