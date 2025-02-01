from quart import Quart, request, jsonify, send_file
from quart_cors import cors
import os
import asyncio
from parser import parser
import logging
import sys
# Отключаем информацию от asyncio
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(
    level=logging.INFO,  # Можно изменить на DEBUG для подробных логов
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/var/log/flask_backend.log"),  # Запись в файл
        logging.StreamHandler(sys.stdout)  # Дублирование в stdout
    ]
)

app = Quart(__name__)
cors(app)  # Для разрешения запросов с фронтенда

@app.route('/api/parse', methods=['POST'])
async def api_parse():
    try:
        data = await request.json
        keywords = data.get('keywords', '')
        low_price = int(data.get('low_price', 1) or 1)  # Если значение пустое, подставляем 1
        top_price = int(data.get('top_price', 1000000) or 1000000)  # Если значение пустое, подставляем 1000000
        discount = int(data.get('discount', 0) or 0)  # Если значение пустое, подставляем 0
        min_rating = float(data.get('min_rating', 0) or 0)  # Если значение пустое, подставляем 0
        # Вызов парсера
        filename = await parser(keywords, low_price, top_price, discount, min_rating) # Используйте await
        return jsonify({"message": "Парсинг завершен успешно!", "file": filename})
    except Exception as e:
        return jsonify({"message": str(e)}), 400


@app.route('/download/<filename>', methods=['GET'])
async def download(filename):
    file_path = os.path.join('.', filename)
    print('Зашёл', file_path)
    if not os.path.exists(file_path):
        return jsonify({"message": "Файл не найден"}), 404

    try:
        # Отправляем файл
        response = await send_file(file_path, as_attachment=True)
        print('Работает')

        return response

    except Exception as e:
        return jsonify({"message": f"Ошибка при отправке файла: {e}"}), 500

@app.route('/api/hello', methods=['GET'])
async def hello():
    return "Hello, World!"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, loop=asyncio.new_event_loop())
