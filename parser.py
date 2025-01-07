import datetime
import requests
import json
import pandas as pd
from retry import retry
# pip install openpyxl
# pip install xlsxwriter


"""Сбор данных со страниц с фильтром по рейтингу, собираем всю возможную информацию по нужному url"""

@retry(Exception, tries=-1, delay=0)
def scrap_page(keywords: str,page: int, low_price: int, top_price: int, discount: int = None, rating: float = 0) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"}
    keywords = keywords.replace(' ', '%20')  # Кодируем пробелы в ключевых словах

    url = (
        f'https://search.wb.ru/exactmatch/ru/common/v4/search?'
        f'appType=1'
        f'&curr=rub'
        f'&dest=-1257786'
        f'&locale=ru'
        f'&query={keywords}' \
        f'&resultset=catalog'\
        f'&page={page}' \
        f'&priceU={low_price * 100};{top_price * 100}' \
        f'&sort=popular&spp=0' \
        f'&{keywords}' \
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


# здесь уже выбираем только нужную информацию. Если name in категории кароче сделаешь
def get_data_from_json(json_file: dict, min_rating: float = 0.0, low_price: int = 1, top_price: int = 1000000,
                       keywords: list = None) -> list:
    data_list = []
    # да нам, собственно-то, и категория не нужна.
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


def parser(keywords: str = None, low_price: int = 1, top_price: int = 1000000, discount: int = 0, min_rating: float = 0):
    """Основная функция с фильтрацией по ключевым словам"""
    try:
        # Поиск введенной категории в общем каталоге
        data_list = []

        for page in range(1, 51):  # ВБ отдает максимум 50 страниц товара
            data = scrap_page(
                page=page,
                low_price=low_price,
                top_price=top_price,
                discount=discount,
                keywords=keywords,
                rating=min_rating,
            )
            # на выходе получаются все товары на странице
            # Передаем минимальный рейтинг и ключевые слова для фильтрации товаров
            extracted_data = get_data_from_json(data, min_rating=min_rating, low_price=low_price, top_price=top_price, keywords=keywords)
            print(f'Страница {page}. Добавлено позиций: {len(extracted_data)}')

            if extracted_data:
                data_list.extend(extracted_data)
            else:
                break
        category = data['metadata']['normquery']
        print(f'Сбор данных завершен. Собрано: {len(data_list)} товаров.')
        save_excel(data_list, f'{category}_from_{low_price}_to_{top_price}_rating_{min_rating}_keywords')

    except TypeError:
        print('Ошибка! Возможно, не верно указан раздел. Удалите все доп фильтры с ссылки.')
    except PermissionError:
        print('Ошибка! Закройте созданный ранее Excel файл и повторите попытку.')


#это менять я не буду
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


# здесь фактически я ничего не меняю, кроме того, что убираем запрос по url
if __name__ == '__main__':
    while True:
        try:
            keywords = input('Введите ключевые слова для фильтрации (через пробел, или просто нажмите Enter):').strip()
            low_price = int(input('Введите минимальную сумму товара: '))
            top_price = int(input('Введите максимальную сумму товара: '))
            discount = int(input('Введите минимальную скидку (введите 0 если без скидки): '))
            min_rating = float(input('Введите минимальную оценку (введите 0 для любого рейтинга): '))
            parser(low_price=low_price, top_price=top_price, discount=discount, min_rating=min_rating, keywords=keywords)
        except ValueError:
            print('Ошибка ввода! Проверьте, что все введенные данные являются числами.\nПерезапуск...')

# Итак, что мы будем делать. Можно ведь просто по этой штуке проходить, просто сделать url это...
# Итак, у нас, я так понял, фактически уже есть категория, и нам надо только по page ходить и смотреть. Посмотрим.
