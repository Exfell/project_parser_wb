import aiohttp
import asyncio
import datetime
import json
import pandas as pd
import re
import math, time
from aiohttp import ClientSession
from fake_useragent import UserAgent

# pip install openpyxl
# pip install aiohttp
# pip install xlsxwriter
session = None

async def create_session():
    """Функция для создания сессии с нужными настройками"""
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit_per_host=60)) # Semaphore - ограниченное кол-во одновременных запросов с фронетнда, TCPConnector - запросов на WB API

async def scrap_page(session: ClientSession, keywords: str, page: int, low_price: int, top_price: int, discount: int = None, rating: float = 0) -> dict:
    """Асинхронная функция для запроса страницы."""
    ua = UserAgent()
    current = ua.random
    keywords = keywords.replace(' ', '%20')

    url = (
        f'https://search.wb.ru/exactmatch/ru/common/v4/search?'
        f'appType=1&curr=rub&dest=-1257786&locale=ru&query={keywords}'
        f'&resultset=catalog&page={page}&priceU={low_price * 100};{top_price * 100}'
        f'&sort=popular&spp=0&discount={discount}&rating={rating}'
    )

    headers = {
        'User-Agent': current,
        'Accept': 'application/json',
    }

    async with session.get(url, headers=headers,timeout=aiohttp.ClientTimeout(total=10)) as response:
        response_text = await response.text()  # Получаем текст ответа

        if response.status == 200:
            try:
                # Используем json.loads на строке текста
                json_data = json.loads(response_text)
                return json_data
            except json.JSONDecodeError:
                raise ValueError("Failed to parse JSON response")
        else:
            raise Exception(f"Request failed with status code {response.status}: {response_text}")


def get_total(json_file: dict):
    total_items = json_file["data"].get("total", 0)
    return total_items


def get_data_from_json(json_file: dict, min_rating: float = 0.0, low_price: int = 1, top_price: int = 1000000) -> list:
    data_list = []
    for data in json_file['data']['products']:
        salePriceU = int(data.get('salePriceU', 0) / 100) if data.get('salePriceU') else int(data.get("priceU", 0) / 100)
        reviewRating = data.get('reviewRating', 0)
        if reviewRating >= min_rating and low_price <= salePriceU <= top_price:
            data_list.append({
                'id': data.get('id'),
                'name': data.get('name'),
                'salePriceU': salePriceU,
                'cashback': data.get('feedbackPoints'),
                'sale': data.get('sale'),
                'brand': data.get('brand'),
                'rating': data.get('rating'),
                'supplier': data.get('supplier'),
                'supplierRating': data.get('supplierRating'),
                'feedbacks': data.get('feedbacks'),
                'reviewRating': reviewRating,
                'link': f'https://www.wildberries.ru/catalog/{data.get("id")}/detail.aspx?targetUrl=BP'
            })
    return data_list


def sanitize_filename(filename: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    sanitized = sanitized.strip()
    return sanitized


async def scrap_page_with_retries(session: ClientSession, page: int, low_price: int, top_price: int, discount: int, keywords: str, min_rating: float, max_retries: int = 10):
    retries = 0
    while retries < max_retries:
        try:
            data = await scrap_page(session, keywords, page, low_price, top_price, discount, min_rating)
            if get_total(data) > 1:
                return data
        except Exception as e:
            print(f"Ошибка на странице {page}: {e}. Попытка {retries + 1}/{max_retries}...")
        retries += 1
    print(f"Не удалось получить данные для страницы {page} после {max_retries} попыток.")
    return None


async def parser(keywords: str = None, low_price: int = 1, top_price: int = 1000000, discount: int = 0, min_rating: float = 0):
    await create_session()
    try:
        data_t = await scrap_page_with_retries(session, page=1, low_price=low_price, top_price=top_price, discount=discount, keywords=keywords, min_rating=min_rating)
        if not data_t:
            print("Ошибка! Не удалось получить данные для первой страницы.")
            return

        total = get_total(data_t)
        items_per_page = 100
        pages = math.ceil(total / items_per_page)
        if pages > 60:
            pages = 60

        data_list = []
        tasks = [scrap_page_with_retries(session, page, low_price, top_price, discount, keywords, min_rating) for page in range(1, pages + 1)]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        # ссли gather сломается, то программа не продолжит работу, т.к. он по умолчанию останавливает всю программу, если хотя бы одна корутина вызывает исключение
        for result in results:
            if isinstance(result, Exception):
                print(f"Ошибка при парсинге страницы: {result}")  # Логируем ошибку, но не падаем
                continue  # Пропускаем этот результат
            extracted_data = get_data_from_json(result, min_rating=min_rating, low_price=low_price, top_price=top_price)
            data_list.extend(extracted_data)

        category = data_t['metadata']['title']
        print(f'Сбор данных завершен. Собрано: {len(data_list)} товаров.')
        filename = sanitize_filename(f'{category}_from_{low_price}_to_{top_price}_rating_{min_rating}')
        save_excel(data_list, filename)
        return f'{filename}.xlsx'
    except Exception as e:
        print(e)



def save_excel(data: list, filename: str):
    df = pd.DataFrame(data)
    with pd.ExcelWriter(f'{filename}.xlsx', engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='data', index=False)
        worksheet = writer.sheets['data']
        worksheet.set_column(0, 1, width=10)
        worksheet.set_column(1, 2, width=34)
        worksheet.set_column(2, 3, width=9)
        worksheet.set_column(3, 4, width=8)
        worksheet.set_column(4, 5, width=4)
        worksheet.set_column(5, 6, width=20)
        worksheet.set_column(6, 7, width=6)
        worksheet.set_column(7, 8, width=23)
        worksheet.set_column(8, 9, width=13)
        worksheet.set_column(9, 10, width=11)
        worksheet.set_column(10, 11, width=12)
        worksheet.set_column(11, 12, width=67)


if __name__ == '__main__':
    while True:
        try:
            keywords = input('Введите ключевые слова для фильтрации (через пробел, или просто нажмите Enter):').strip()
            low_price = int(input('Введите минимальную сумму товара: '))
            top_price = int(input('Введите максимальную сумму товара: '))
            discount = int(input('Введите минимальную скидку (введите 0 если без скидки): '))
            min_rating = float(input('Введите минимальную оценку (введите 0 для любого рейтинга): '))
            start = time.time()
            asyncio.run(parser(low_price=low_price, top_price=top_price, discount=discount, min_rating=min_rating, keywords=keywords))
            end = time.time()
            print(end-start)
        except ValueError:
            print('Ошибка ввода! Проверьте, что все введенные данные являются числами.\nПерезапуск...')
