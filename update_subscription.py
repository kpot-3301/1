import base64
import re
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import requests

# ---- Настройки ----
OUTPUT_FILE = "🥷КРОТовые ТОННЕЛИ🥷.txt"
SURS_FILE = "SURS.txt"
IGNOR_FILE = "IGNOR-name.txt"

# Шаблон заголовка
HEADER = """#profile-title:🥷КРОТовые ТОННЕЛИ🥷
#subscription-userinfo:upload=0; download=0; total=0; expire=0
#profile-update-interval:1
#announce:ТОННЕЛЕЙ: {count} | 📅 {datetime}
"""

def load_ignore_words():
    """Читает файл со словами для вырезания, возвращает список."""
    if not os.path.exists(IGNOR_FILE):
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def remove_ignored_words(name, ignore_words):
    """Удаляет все вхождения запрещённых слов из строки name (без учёта регистра)."""
    for word in ignore_words:
        # Регистронезависимая замена
        name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)
    # Убираем лишние пробелы, которые могли остаться после удаления
    return name.strip()

def extract_host_port(config_str):
    """
    Пытается извлечь адрес (или IP) и порт из строки конфигурации.
    Поддерживает форматы: vmess://, vless://, trojan://, ss://, ssr://, hysteria2:// и т.д.
    Возвращает строку "host:port" или None.
    """
    # Если это vmess, сначала декодируем base64
    if config_str.startswith('vmess://'):
        try:
            b64_part = config_str[8:]
            # Иногда в конце может быть #name, убираем
            if '#' in b64_part:
                b64_part = b64_part.split('#')[0]
            # Добавляем padding
            missing_padding = len(b64_part) % 4
            if missing_padding:
                b64_part += '=' * (4 - missing_padding)
            decoded = base64.b64decode(b64_part).decode('utf-8')
            import json
            vmess = json.loads(decoded)
            host = vmess.get('add')
            port = vmess.get('port')
            if host and port:
                return f"{host}:{port}"
        except:
            pass
        return None

    # Для остальных протоколов парсим как URL
    # Убираем возможный префикс протокола
    for proto in ['vless://','trojan://','ss://','ssr://','hysteria2://','hysteria://','tuic://',
                  'socks5://','http://','https://']:
        if config_str.startswith(proto):
            try:
                # Отделяем основную часть до #
                main_part = config_str.split('#')[0]
                parsed = urlparse(main_part)
                host = parsed.hostname
                port = parsed.port
                if host and port:
                    return f"{host}:{port}"
                # Для ss:// особый случай: иногда парсится как scheme://base64
                # Попробуем альтернативный метод
                if proto == 'ss://':
                    # Формат ss://base64(method:password)@host:port?params#name
                    # urlparse не всегда корректно разбирает из-за base64
                    # Используем регулярку
                    match = re.search(r'@([^:]+):(\d+)', main_part)
                    if match:
                        return f"{match.group(1)}:{match.group(2)}"
            except:
                pass
    # Общий fallback: ищем @хост:порт
    match = re.search(r'@([^:\[\]]+):(\d+)', config_str.split('#')[0])
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None

def fetch_subscription(url):
    """Скачивает подписку по URL, при необходимости декодирует base64,
    возвращает список строк-ключей."""
    resp = requests.get(url, timeout=30)
    content = resp.text.strip()
    # Пробуем раскодировать как base64
    try:
        # добавляем padding если нужно
        missing = len(content) % 4
        if missing:
            content += '=' * (4 - missing)
        decoded = base64.b64decode(content).decode('utf-8')
        # Если в декодированной строке нет смысла, возможно это и так plain text
        # Проверяем, что результат содержит типичные протоколы
        if any(proto in decoded for proto in ['vmess://','vless://','trojan://','ss://','ssr://']):
            content = decoded
    except:
        pass
    # Разбиваем на строки, убираем пустые
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return lines

def main():
    # 1. Загружаем источники
    with open(SURS_FILE, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    # 2. Скачиваем все ключи
    all_keys = []
    for url in urls:
        try:
            keys = fetch_subscription(url)
            all_keys.extend(keys)
            print(f"Загружено {len(keys)} ключей из {url}")
        except Exception as e:
            print(f"Ошибка загрузки {url}: {e}")

    # 3. Удаляем дубликаты по адресу:порт
    seen_hostports = set()
    unique_keys = []
    for key in all_keys:
        hp = extract_host_port(key)
        if hp is None:
            # Не можем определить – оставляем как есть (или пропускаем? лучше оставить)
            unique_keys.append(key)
            continue
        if hp not in seen_hostports:
            seen_hostports.add(hp)
            unique_keys.append(key)

    # 4. Обрабатываем названия – вырезаем запрещённые слова
    ignore_words = load_ignore_words()
    final_keys = []
    for key in unique_keys:
        if '#' in key:
            base_part, name = key.split('#', 1)
            original_name = name
            cleaned_name = remove_ignored_words(name, ignore_words)
            if cleaned_name:
                new_key = f"{base_part}#{cleaned_name}"
            else:
                # Если после удаления имени не осталось, можно оставить без имени
                new_key = base_part
            final_keys.append(new_key)
        else:
            final_keys.append(key)

    # 5. Формируем итоговый файл
    now = datetime.now()
    datetime_str = now.strftime("%d-%m-%Y %H:%M")
    count = len(final_keys)

    header = HEADER.format(count=count, datetime=datetime_str)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))

    print(f"Готово! Сгенерирован файл {OUTPUT_FILE} с {count} ключами.")

if __name__ == "__main__":
    main()