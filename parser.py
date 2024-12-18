import datetime
import requests
import json
import pandas as pd
from retry import retry
# pip install openpyxl
# pip install xlsxwriter



def get_catalogs_wb() -> dict:
    url = 'https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json'
    headers = {'Accept': '*/*', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    return requests.get(url, headers=headers).json()


def get_data_category(catalogs_wb: dict) -> list:
    """сбор данных категорий из каталога Wildberries"""
    catalog_data = []
    if isinstance(catalogs_wb, dict) and 'childs' not in catalogs_wb:
        catalog_data.append({
            'name': f"{catalogs_wb['name']}",
            'shard': catalogs_wb.get('shard', None),
            'url': catalogs_wb['url'],
            'query': catalogs_wb.get('query', None)
        })
    elif isinstance(catalogs_wb, dict):
        catalog_data.append({
            'name': f"{catalogs_wb['name']}",
            'shard': catalogs_wb.get('shard', None),
            'url': catalogs_wb['url'],
            'query': catalogs_wb.get('query', None)
        })
        catalog_data.extend(get_data_category(catalogs_wb['childs']))
    else:
        for child in catalogs_wb:
            catalog_data.extend(get_data_category(child))
    return catalog_data


def search_category_in_catalog(url: str, catalog_list: list) -> dict:
    """проверка пользовательской ссылки на наличии в каталоге"""
    for catalog in catalog_list:
        if catalog['url'] == url.split('https://www.wildberries.ru')[-1]:
            print(f'найдено совпадение: {catalog["name"]}')
            return catalog


def get_data_from_json(json_file: dict, min_rating: float = 0.0, low_price: int = 1, top_price: int = 1000000,
                       keywords: list = None) -> list:
    data_list = []
    for data in json_file['data']['products']:
        # Используем цену со скидкой, если она есть, иначе - обычную цену
        salePriceU = int(data.get('salePriceU', 0) / 100) if data.get('salePriceU') else int(
            data.get("priceU", 0) / 100)
        reviewRating = data.get('reviewRating', 0)

        # Проверка фильтров: по рейтингу и цене
        if reviewRating >= min_rating and low_price <= salePriceU <= top_price:
            # Проверка ключевых слов в названии товара
            if keywords and not any(keyword.lower() in data.get('name', '').lower() for keyword in keywords):
                continue  # Пропускаем товар, если ни одно ключевое слово не найдено

            # Если все проверки прошли, добавляем товар в список
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

@retry(Exception, tries=-1, delay=0)
def scrap_page(page: int, shard: str, query: str, low_price: int, top_price: int, discount: int = None, rating: int = 0) -> dict:
    """Сбор данных со страниц с фильтром по рейтингу"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"}
    url = f'https://catalog.wb.ru/catalog/{shard}/catalog?appType=1&curr=rub' \
          f'&dest=-1257786' \
          f'&locale=ru' \
          f'&page={page}' \
          f'&priceU={low_price * 100};{top_price * 100}' \
          f'&sort=popular&spp=0' \
          f'&{query}' \
          f'&discount={discount}' \
          f'&rating={rating}'  # Добавляем фильтр по рейтингу
    r = requests.get(url, headers=headers)
    print(f'Статус: {r.status_code} Страница {page} Идет сбор...')
    return r.json()



def parser(url: str, low_price: int = 1, top_price: int = 1000000, discount: int = 0, min_rating: float = 0, keywords: list = None):
    """Основная функция с фильтрацией по ключевым словам"""
    catalog_data = get_data_category(get_catalogs_wb())
    try:
        # Поиск введенной категории в общем каталоге
        category = search_category_in_catalog(url=url, catalog_list=catalog_data)
        data_list = []

        for page in range(1, 51):  # ВБ отдает максимум 50 страниц товара
            data = scrap_page(
                page=page,
                shard=category['shard'],
                query=category['query'],
                low_price=low_price,
                top_price=top_price,
                discount=discount
            )

            # Передаем минимальный рейтинг и ключевые слова для фильтрации товаров
            extracted_data = get_data_from_json(data, min_rating=min_rating, low_price=low_price, top_price=top_price, keywords=keywords)
            print(f'Добавлено позиций: {len(extracted_data)}')

            if extracted_data:
                data_list.extend(extracted_data)
            else:
                break

        print(f'Сбор данных завершен. Собрано: {len(data_list)} товаров.')
        save_excel(data_list, f'{category["name"]}_from_{low_price}_to_{top_price}_rating_{min_rating}_keywords')
        print(
            f'Ссылка для проверки: {url}?priceU={low_price * 100};{top_price * 100}&discount={discount}&minRating={min_rating}')

    except TypeError:
        print('Ошибка! Возможно, не верно указан раздел. Удалите все доп фильтры с ссылки.')
    except PermissionError:
        print('Ошибка! Закройте созданный ранее Excel файл и повторите попытку.')

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
    print(f'Все сохранено в {filename}.xlsx\n')

if __name__ == '__main__':
    while True:
        try:
            url = input('Введите ссылку на категорию без фильтров для сбора (или "q" для выхода):\n')
            if url == 'q':
                break
            keywords_input = input('Введите ключевые слова для фильтрации (через пробел, или просто нажмите Enter):')
            low_price = int(input('Введите минимальную сумму товара: '))
            top_price = int(input('Введите максимальную сумму товара: '))
            discount = int(input('Введите минимальную скидку (введите 0 если без скидки): '))
            min_rating = float(input('Введите минимальную оценку (введите 0 для любого рейтинга): '))
            keywords = [word.strip() for word in keywords_input.split()] if keywords_input else []
            parser(url=url, low_price=low_price, top_price=top_price, discount=discount, min_rating=min_rating, keywords=keywords)
        except ValueError:
            print('Ошибка ввода! Проверьте, что все введенные данные являются числами.\nПерезапуск...')
