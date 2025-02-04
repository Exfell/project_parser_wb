import json
import pandas as pd
import re
import math
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from fake_useragent import UserAgent
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Настройки для повторных попыток
retry_strategy = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]
)


def create_session():
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=100, pool_maxsize=100)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def scrap_page(session: requests.Session, keywords: str, page: int, low_price: int, top_price: int,
               discount: int = None, rating: float = 0) -> dict:
    """Функция для запроса страницы."""
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
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ошибка при запросе страницы {page}: {e}")
        return None


def get_total(json_file: dict):
    total_items = json_file["data"].get("total", 0)
    return total_items


def get_data_from_json(json_file: dict, min_rating: float = 0.0, low_price: int = 1, top_price: int = 1000000) -> list:
    data_list = []
    for data in json_file['data']['products']:
        salePriceU = int(data.get('salePriceU', 0) / 100) if data.get('salePriceU') else int(
            data.get("priceU", 0) / 100)
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


def scrap_page_with_retries(session: requests.Session, page: int, low_price: int, top_price: int, discount: int,
                            keywords: str, min_rating: float, max_retries: int = 10):
    retries = 0
    while retries < max_retries:
        try:
            data = scrap_page(session, keywords, page, low_price, top_price, discount, min_rating)
            if data and get_total(data) > 1:
                return data
        except Exception as e:
            print(f"Ошибка на странице {page}: {e}. Попытка {retries + 1}/{max_retries}...")
            retries += 1
    print(f"Не удалось получить данные для страницы {page} после {max_retries} попыток.")
    return None

# старый parser
def process_keyword(args):
    keywords, low_price, top_price, discount, min_rating = args
    start_time = time.time()
    print(f"Начало обработки ключевого слова: {keywords}")

    with create_session() as session:
        # Получение данных первой страницы для определения общего количества
        data_t = scrap_page_with_retries(session, page=1, low_price=low_price, top_price=top_price, discount=discount,
                                         keywords=keywords, min_rating=min_rating)
        if not data_t:
            print("Ошибка! Не удалось получить данные для первой страницы.")
            return None

        total = get_total(data_t)
        items_per_page = 100
        pages = math.ceil(total / items_per_page)
        if pages > 60:
            pages = 60

        # Подготовка аргументов для потоков
        page_args = [(session, page, low_price, top_price, discount, keywords, min_rating)
                     for page in range(1, pages + 1)]

        # Параллельная обработка страниц с использованием потоков
        with ThreadPoolExecutor(max_workers=1000) as executor:
            results = list(executor.map(lambda args: scrap_page_with_retries(*args), page_args))

        # Сбор и обработка результатов
        data_list = []
        for result in results:
            if result:
                data_list.extend(get_data_from_json(result, min_rating, low_price, top_price))

        # Сохранение в Excel
        if data_list:
            category = data_t['metadata']['title']
            filename = sanitize_filename(f'{category}_from_{low_price}_to_{top_price}_rating_{min_rating}')
            save_excel(data_list, filename)
            print(f'Сбор {keywords} данных завершен. Собрано: {len(data_list)} товаров.')

        print(f"Завершено: {keywords} за {time.time() - start_time:.2f} сек.")
        return f'{filename}.xlsx'


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


def main():
    tasks = []
    while True:
        keywords = input('Введите ключевые слова для фильтрации (через пробел, или просто нажмите Enter):').strip()
        if not keywords:
            break
        low_price = int(input('Введите минимальную сумму товара: '))
        top_price = int(input('Введите максимальную сумму товара: '))
        discount = int(input('Введите минимальную скидку (введите 0 если без скидки): '))
        min_rating = float(input('Введите минимальную оценку (введите 0 для любого рейтинга): '))
        tasks.append((keywords, low_price, top_price, discount, min_rating))

    start = time.time()
    results = []
    # Параллельная обработка разных ключевых слов в процессах
    with ProcessPoolExecutor() as executor:
        future_to_task = {executor.submit(process_keyword, task): task for task in tasks}

        for future in as_completed(future_to_task):  # Получаем результаты по мере завершения
            result = future.result()
            results.append(result)

    print(f"Все задачи завершены за {time.time() - start:.2f} сек.")
    print("Результаты:", [r for r in results if r])


if __name__ == '__main__':
    main()
