import asyncio
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from config import TELEGRAM_TOKEN

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Определение состояний FSM
class SearchStates(StatesGroup):
    waiting_for_search_type = State()
    waiting_for_input = State()
    waiting_for_company_choice = State()

# Маппинг типов поиска на параметры URL
SEARCH_TYPES = {
    "Поиск по ИНН": "inn",
    "Поиск по ОГРН": "ogrn",
    "Поиск по ОКПО": "okpo",
    "Поиск по телефону": "phone",
    "Поиск по наименованию": "name",
    "Поиск по руководителю": "boss",
    "Поиск по адресу": "address",
    "Поиск банка по БИК": "bic",
    "Расширенный поиск": "all"
}

# Кнопки управления
CONTROL_BUTTONS = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Назад"), KeyboardButton(text="На главную")]
    ],
    resize_keyboard=True
)

# Функция для парсинга результатов поиска
async def search_companies(search_type: str, query: str) -> list:
    async with aiohttp.ClientSession() as session:
        url = f"https://www.list-org.com/search?type={SEARCH_TYPES[search_type]}&val={query}"
        async with session.get(url) as response:
            if response.status != 200:
                return []
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            companies = []
            org_list = soup.select(".org_list p")
            for org in org_list:
                link = org.find("a")
                if not link:
                    continue
                company_id = link.get("href").split("/")[-1]
                short_name = link.text.strip()
                full_name = org.find("span").text.strip() if org.find("span") else short_name
                companies.append({
                    "id": company_id,
                    "short_name": short_name,
                    "full_name": full_name
                })
            return companies

# Функция для получения подробной информации о компании
async def get_company_details(company_id: str) -> dict:
    async with aiohttp.ClientSession() as session:
        url = f"https://www.list-org.com/company/{company_id}"
        async with session.get(url) as response:
            if response.status != 200:
                return {"basic": "Не удалось загрузить информацию о компании.", "activities": "", "founders": "", "financials": ""}

            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            # Основная информация
            basic_details = []
            table = soup.select_one(".card.w-100.p-1.p-lg-3 table.table-sm")
            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) == 2:
                        key = cols[0].text.strip()
                        value = cols[1].text.strip()
                        basic_details.append(f"{key} {value}")

            contact_section = soup.select_one(".card.w-100.p-1.p-lg-3 .col-md-9")
            if contact_section:
                basic_details.append("\nКонтактная информация:")
                for p in contact_section.find_all("p"):
                    basic_details.append(p.text.strip())

            requisites_section = soup.select_one(".card.w-100.p-1.p-lg-3 h6:contains('Реквизиты компании')")
            if requisites_section:
                requisites = requisites_section.find_next("div")
                basic_details.append("\nРеквизиты компании:")
                for p in requisites.find_all("p"):
                    basic_details.append(p.text.strip())

            basic_info = "\n".join(basic_details) if basic_details else "Информация о компании не найдена."

            # Виды деятельности
            activities_section = soup.select_one(".card.w-100.p-1.p-lg-3 h6:contains('Виды деятельности')")
            activities = []
            if activities_section:
                activities_div = activities_section.find_next("div")
                main_activity = activities_div.find("p", string=lambda t: "Основной" in t if t else False)
                if main_activity:
                    activities.append(f"Основной вид деятельности:\n{main_activity.text.strip()}")
                additional_activities = activities_div.select(".fix_height table.tt tr")
                if additional_activities:
                    activities.append("\nДополнительные виды деятельности:")
                    for tr in additional_activities:
                        tds = tr.find_all("td")
                        if len(tds) == 2:
                            activities.append(f"{tds[0].text.strip()} - {tds[1].text.strip()}")
            activities_info = "\n".join(activities) if activities else "Информация не найдена."

            # Учредители
            founders_section = soup.select_one("#founders")
            founders = []
            if founders_section:
                founders_table = founders_section.find("table")
                if founders_table:
                    for tr in founders_table.find_all("tr")[1:]:  # Пропускаем заголовок
                        tds = tr.find_all("td")
                        if len(tds) >= 4:
                            name = tds[0].text.strip()
                            inn = tds[1].text.strip()
                            share = tds[2].text.strip()
                            amount = tds[3].text.strip()
                            founders.append(f"Наименование: {name}\nИНН: {inn}\nДоля: {share}\nСумма: {amount}")
            founders_info = "\n\n".join(founders) if founders else "Информация не найдена."

            # Финансовые отчеты
            financials_section = soup.select_one("h6:contains('Результаты работы')")
            financials = []
            if financials_section:
                financials_table = financials_section.find_next("table")
                if financials_table:
                    for tr in financials_table.find_all("tr")[1:]:  # Пропускаем заголовок
                        tds = tr.find_all("td")
                        if len(tds) >= 3:
                            code = tds[0].text.strip()
                            name = tds[1].text.strip()
                            value = tds[2].text.strip()
                            unit = tds[3].text.strip() if len(tds) > 3 else "тыс. руб."
                            financials.append(f"{code} | {name} | {value} {unit}")
            financials_info = "\n".join(financials) if financials else "Информация не найдена."

            return {
                "basic": basic_info,
                "activities": activities_info,
                "founders": founders_info,
                "financials": financials_info
            }

# Стартовая команда
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Начать поиск")]],
        resize_keyboard=True
    )
    await message.answer("Привет! Нажми кнопку, чтобы начать поиск.", reply_markup=keyboard)
    await state.set_state(SearchStates.waiting_for_search_type)

# Обработка кнопки "На главную"
@dp.message(lambda message: message.text == "На главную")
async def go_to_main(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Начать поиск")]],
        resize_keyboard=True
    )
    await message.answer("Вы вернулись на главный экран.", reply_markup=keyboard)
    await state.set_state(SearchStates.waiting_for_search_type)

# Обработка кнопки "Начать поиск"
@dp.message(lambda message: message.text == "Начать поиск")
async def process_search_start(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    search_options = [
        "Поиск по ИНН", "Поиск по ОГРН", "Поиск по ОКПО", "Поиск по телефону",
        "Поиск по наименованию", "Поиск по руководителю", "Поиск по адресу",
        "Поиск банка по БИК", "Расширенный поиск"
    ]
    for option in search_options:
        builder.add(KeyboardButton(text=option))
    builder.add(KeyboardButton(text="Назад"))
    builder.add(KeyboardButton(text="На главную"))
    builder.adjust(3)
    await message.answer("Выберите тип поиска:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(SearchStates.waiting_for_search_type)

# Обработка выбора типа поиска
@dp.message(lambda message: message.text in SEARCH_TYPES.keys())
async def process_search_type(message: types.Message, state: FSMContext):
    search_type = message.text
    search_prompts = {
        "Поиск по ИНН": "Введите ИНН:",
        "Поиск по ОГРН": "Введите ОГРН:",
        "Поиск по ОКПО": "Введите ОКПО:",
        "Поиск по телефону": "Введите номер телефона:",
        "Поиск по наименованию": "Введите наименование:",
        "Поиск по руководителю": "Введите имя руководителя:",
        "Поиск по адресу": "Введите адрес:",
        "Поиск банка по БИК": "Введите БИК банка:",
        "Расширенный поиск": "Введите данные для поиска:"
    }
    await state.update_data(search_type=search_type)
    await message.answer(search_prompts[search_type], reply_markup=CONTROL_BUTTONS)
    await state.set_state(SearchStates.waiting_for_input)

# Обработка кнопки "Назад"
@dp.message(lambda message: message.text == "Назад")
async def handle_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == SearchStates.waiting_for_input:
        await process_search_start(message, state)
    elif current_state == SearchStates.waiting_for_company_choice:
        data = await state.get_data()
        search_type = data.get("search_type")
        search_prompts = {
            "Поиск по ИНН": "Введите ИНН:",
            "Поиск по ОГРН": "Введите ОГРН:",
            "Поиск по ОКПО": "Введите ОКПО:",
            "Поиск по телефону": "Введите номер телефона:",
            "Поиск по наименованию": "Введите наименование:",
            "Поиск по руководителю": "Введите имя руководителя:",
            "Поиск по адресу": "Введите адрес:",
            "Поиск банка по БИК": "Введите БИК банка:",
            "Расширенный поиск": "Введите данные для поиска:"
        }
        await message.answer(search_prompts[search_type], reply_markup=CONTROL_BUTTONS)
        await state.set_state(SearchStates.waiting_for_input)
    else:
        await go_to_main(message, state)

# Обработка ввода данных пользователем
@dp.message(SearchStates.waiting_for_input)
async def process_input(message: types.Message, state: FSMContext):
    if message.text in ["Назад", "На главную"]:
        return

    user_input = message.text
    data = await state.get_data()
    search_type = data.get("search_type")

    companies = await search_companies(search_type, user_input)
    if not companies:
        await message.answer("Компании не найдены. Попробуйте изменить запрос.", reply_markup=CONTROL_BUTTONS)
        await state.set_state(SearchStates.waiting_for_input)
        return

    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{company['short_name']}\n{company['full_name']}", callback_data=f"company_{company['id']}")]
        for company in companies[:10]
    ])
    await message.answer("Выберите предприятие:", reply_markup=inline_keyboard)
    await state.set_state(SearchStates.waiting_for_company_choice)

# Обработка выбора компании
@dp.callback_query(lambda c: c.data.startswith("company_"))
async def process_company_choice(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != SearchStates.waiting_for_company_choice:
        await callback.message.answer("Пожалуйста, сначала выполните поиск и выберите предприятие.", reply_markup=CONTROL_BUTTONS)
        await callback.answer()
        return

    company_id = callback.data.split("_")[1]
    details = await get_company_details(company_id)

    # Формируем основное сообщение с кнопками
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Виды деятельности", callback_data=f"activities_{company_id}")],
        [InlineKeyboardButton(text="Учредители", callback_data=f"founders_{company_id}")],
        [InlineKeyboardButton(text="Финансовые отчеты", callback_data=f"financials_{company_id}")]
    ])
    await callback.message.answer(details["basic"], reply_markup=inline_keyboard)
    await state.update_data(company_details=details)  # Сохраняем детали в состоянии
    await callback.answer()

# Обработка кнопок дополнительных данных
@dp.callback_query(lambda c: c.data.startswith(("activities_", "founders_", "financials_")))
async def process_additional_info(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    company_details = data.get("company_details", {})

    callback_type, company_id = callback.data.split("_", 1)
    if callback_type == "activities":
        info = company_details.get("activities", "Информация не найдена.")
        await callback.message.answer(f"Виды деятельности:\n{info}", reply_markup=CONTROL_BUTTONS)
    elif callback_type == "founders":
        info = company_details.get("founders", "Информация не найдена.")
        await callback.message.answer(f"Учредители:\n{info}", reply_markup=CONTROL_BUTTONS)
    elif callback_type == "financials":
        info = company_details.get("financials", "Информация не найдена.")
        await callback.message.answer(f"Финансовые отчеты:\n{info}", reply_markup=CONTROL_BUTTONS)
    await callback.answer()

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())