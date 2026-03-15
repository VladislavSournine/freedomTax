# Калькулятор податків Freedom24

Локальний інструмент для розрахунку ПДФО та ВЗ з виписки Freedom24 брокера.
Допомагає заповнити рядок 10.10 та Додаток Ф1 декларації (cabinet.tax.gov.ua).

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Відкрий http://localhost:8080 у браузері.

За замовчуванням порт **8080**. Щоб змінити:

```bash
PORT=5000 python app.py
```

> На macOS порт 5000 може бути зайнятий AirPlay Receiver (System Settings → General → AirDrop & Handoff → AirPlay Receiver → вимкнути).

## Як отримати файл з Freedom24

1. Відкрий freedom24.com → Мій рахунок → Звіти → Загальний звіт
2. Формат: **JSON**
3. Період: **від дати відкриття рахунку** до 31 грудня звітного року
   > Повна історія потрібна для правильного FIFO-розрахунку

## Дисклеймер

Інструмент надається виключно для довідки. Перевірте розрахунки самостійно
або з податковим консультантом. Автор не несе відповідальності за помилки.

## Тести

```bash
pytest
```
