import datetime
import requests
import json
import pandas as pd
from retry import retry
import re
import math
import time  # Импорт модуля для добавления задержки
from fake_useragent import UserAgent

# pip install openpyxl
# pip install xlsxwriter

# чтобы получить json, надо сделать то же, что делал и Тимур в get_catalog
"""Сбор данных со страниц с фильтром по рейтингу, собираем всю возможную информацию по нужному url"""
# полностью работает

@retry(Exception, tries=-1, delay=0)
def scrap_page(keywords: str, page: int, low_price: int, top_price: int, discount: int = None,
               rating: float = 0) -> dict:
    ua = UserAgent()
    current = ua.random
    headers = {"User-Agent": current}
    keywords = keywords.replace(' ', '%20')  # Кодируем пробелы в ключевых словах
    url = (
        f'https://search.wb.ru/exactmatch/ru/common/v4/search?'
        f'appType=1'
        f'&curr=rub'
        f'&dest=-1257786'
        f'&locale=ru'
        f'&query={keywords}' \
        f'&resultset=catalog' \
        f'&page={page}' \
        f'&priceU={low_price * 100};{top_price * 100}' \
        f'&sort=popular&spp=0' \
        f'&discount={discount}' \
        f'&rating={rating}'
    )
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        try:
            return response.json()  # Возвращаем JSON-ответ
        except ValueError:
            raise ValueError("Failed to parse JSON response")
    else:
        raise Exception(f"Request failed with status code {response.status_code}: {response.text}")


def get_total(json_file: dict):
    total_items = json_file["data"].get("total", 0)
    return total_items


def first_check(json_file):
    data_list = []
    '''Выбираем нужные нам параметры'''
    for data in json_file['data']['products']:
        # Используем цену со скидкой, если она есть, иначе - обычную цену
        salePriceU = int(data.get('salePriceU', 0) / 100) if data.get('salePriceU') else int(
            data.get("priceU", 0) / 100)
        reviewRating = data.get('reviewRating', 0)
        data_list.append('res')
    return data_list


# здесь уже выбираем только нужную информацию. Если name in категории кароче сделаешь
unique_characteristics = {}
def get_data_from_json(json_file: dict, min_rating: float = 0.0, low_price: int = 1, top_price: int = 1000000,) -> list:
    data_list = []
    '''Выбираем нужные нам параметры'''
    for data in json_file['data']['products']:
        # Используем цену со скидкой, если она есть, иначе - обычную цену
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
    # Заменяем все недопустимые символы на "_"
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Убираем начальные и конечные пробелы
    sanitized = sanitized.strip()
    return sanitized


def scrap_page_with_retries(page: int, low_price: int, top_price: int, discount: int, keywords: str, min_rating: float,
                            expected_count: int, max_retries: int = 5):
    retries = 0
    while retries < max_retries:
        data = scrap_page(
            page=page,
            low_price=low_price,
            top_price=top_price,
            discount=discount,
            keywords=keywords,
            rating=min_rating,
        )
        print()
        # Проверяем, сколько товаров вернулось
        extracted_data = first_check(data)
        if len(extracted_data) >= expected_count:
            return data
        retries += 1
        print(f"Некорректное количество товаров на странице {page}. Повтор попытки {retries}/{max_retries}...")
    print(
        f"Не удалось получить корректные данные для страницы {page} после {max_retries} попыток. Скорее всего, это очень узкий поиск.")
    return None


def get_settings(id: str):
    ua = UserAgent()
    current = ua.random
    headers = {"User-Agent": current}
    for i in range(30):  # Перебор basket
        basket_id = f"{i:02d}"  # Форматирование, чтобы всегда было два символа
        try:
            moz = len(id) - 3
            url = f'https://basket-{basket_id}.wbbasket.ru/vol{id[:(moz - 2)]}/part{id[:moz]}/{id}/info/ru/card.json'
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()  # Возвращаем JSON-данные, если запрос успешен
        except requests.exceptions.RequestException:
            continue
    raise Exception(f"Не удалось получить JSON для id: {id}")


def parser(keywords: str = None, low_price: int = 1, top_price: int = 1000000, discount: int = 0,
           min_rating: float = 0):
    """Основная функция с фильтрацией по ключевым словам"""
    try:
        # Поиск введенной категории в общем каталоге
        data_list = []
        data_t = scrap_page_with_retries(page=1, low_price=low_price, top_price=top_price, discount=discount,
                                         min_rating=min_rating, expected_count=2, keywords=keywords)
        total = get_total(data_t)
        items_per_page = 100
        # Количество страниц
        pages = math.ceil(total / items_per_page)
        if pages > 60:  # ВБ отдает максимум 50 страниц товара
            pages = 60

        for page in range(1, pages + 1):
            print('Страница ',page)
            expected_count = min(items_per_page, total - 100 * (page - 1))
            data = scrap_page_with_retries(
                page=page,
                low_price=low_price,
                top_price=top_price,
                discount=discount,
                keywords=keywords,
                min_rating=min_rating,
                expected_count=expected_count
            )
            # на выходе получаются все товары на странице
            # Передаем минимальный рейтинг и ключевые слова для фильтрации товаров
            extracted_data = get_data_from_json(data, min_rating=min_rating, low_price=low_price, top_price=top_price)
            print(f'Страница {page}. Добавлено позиций: {len(extracted_data)}')
            if extracted_data:
                data_list.extend(extracted_data)
            # Добавляем задержку перед следующим запросом
            # time.sleep(3)  # Эта задержка нужна, чтобы у нас был не всякий мусор, но API wb успевал подгружать нужные файлы. Кароче, это ещё может быть из-за всяких там пиковых нагрузок на сервер wb и т.п.
        category = data_t['metadata']['title']
        print(f'Сбор данных завершен. Собрано: {len(data_list)} товаров.')
        filename = sanitize_filename(f'{category}_from_{low_price}_to_{top_price}_rating_{min_rating}')
        save_excel(data_list, filename)
        return f'{filename}.xlsx'
    except TypeError:
        print('Ошибка! Возможно, не верно указан раздел. Удалите все доп фильтры с ссылки.')
    except PermissionError:
        print('Ошибка! Закройте созданный ранее Excel файл и повторите попытку.')

# это мы переделаем, чтобы он динамично считал
def save_excel(data: list, filename: str):
    """сохранение результата в excel файл"""
    df = pd.DataFrame(data)
    # Добавляем engine='xlsxwriter' для поддержки записи
    with pd.ExcelWriter(f'{filename}.xlsx', engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='data', index=False)
        # указываем размеры каждого столбца в итоговом файле
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


# здесь фактически я ничего не меняю, кроме того, что убираем запрос по url
if __name__ == '__main__':
    while True:
        try:
            keywords = input('Введите ключевые слова для фильтрации (через пробел, или просто нажмите Enter):').strip()
            low_price = int(input('Введите минимальную сумму товара: '))
            top_price = int(input('Введите максимальную сумму товара: '))
            discount = int(input('Введите минимальную скидку (введите 0 если без скидки): '))
            min_rating = float(input('Введите минимальную оценку (введите 0 для любого рейтинга): '))
            parser(low_price=low_price, top_price=top_price, discount=discount, min_rating=min_rating,
                   keywords=keywords)
        except ValueError:
            print('Ошибка ввода! Проверьте, что все введенные данные являются числами.\nПерезапуск...')

# Итак, что мы будем делать. Можно ведь просто по этой штуке проходить, просто сделать url это...
# Итак, у нас, я так понял, фактически уже есть категория, и нам надо только по page ходить и смотреть. Посмотрим.
