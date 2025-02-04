from quart import Quart, request, jsonify, send_file
from quart_cors import cors
import os
import asyncio
from parser import process_keyword
import logging

# Отключаем информацию от asyncio
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
app = Quart(__name__)
cors(app)  # Для разрешения запросов с фронтенда

@app.route('/api/parse', methods=['POST'])
async def api_parse():
    try:
        data = await request.json
        params = (
            data.get('keywords', '') or '',
            int(data.get('low_price', 1) or 1),
            int(data.get('top_price', 1000000) or 1000000),
            int(data.get('discount', 0) or 0),
            float(data.get('min_rating', 0) or 0)
        )  # Если значение пустое, подставляем 0
        # Вызов парсера
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, process_keyword, params) # Используйте await
        if result:
            # print(result,'ХЕЙ, ЭТО ОН СДЕЛАН==================') # это всё в одно и то же время делается, т.е. result  нас выходит только тогда, когда все доделаются
            return jsonify({
                "status": "completed",
                "message": "Парсинг успешно завершен",
                "file": result
            })
        return jsonify({"status": "error", "message": "Не удалось получить данные"}), 500
    except Exception as e:
        return jsonify({"message": str(e)}), 400


@app.route('/download/<filename>', methods=['GET'])
async def download(filename):
    file_path = os.path.join('.', filename)
    if not os.path.exists(file_path):
        return jsonify({"message": "Файл не найден"}), 404
    try:
        # Отправляем файл
        response = await send_file(file_path, as_attachment=True)
        return response
    except Exception as e:
        return jsonify({"message": f"Ошибка при отправке файла: {e}"}), 500


@app.route('/api/hello', methods=['GET'])
async def hello():
    return "Hello, World!"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200, debug=False)
# проблема, если что, была в том, что порт был занят
