import base64
import re
import os
from datetime import datetime
from zoneinfo import ZoneInfo          # для часового пояса
from urllib.parse import urlparse, unquote, quote
import requests

# ---- Шаблоны заголовков ----
HEADER_SURS = """#profile-title:🥷КРОТовые ТОННЕЛИ🥷
#subscription-userinfo:upload=0; download=0; total=0; expire=0
#profile-update-interval:1
#announce:ТОННЕЛЕЙ: {count} | 📅 {datetime}
"""

HEADER_WHITE = """#profile-title:📡КРОТовые ТОННЕЛИ📡
#subscription-userinfo:upload=0; download=0; total=0; expire=0
#profile-update-interval:1
#announce:ТОННЕЛЕЙ: {count} | 📅 {datetime}
"""

IGNOR_FILE = "IGNOR-name.txt"

# Допустимые протоколы
VALID_PROTOCOLS = re.compile(
    r'^(vmess|vless|trojan|ss|ssr|hysteria2|hysteria|tuic|socks5|http|https)://'
)


def load_ignore_words():
    """Читает файл со словами для вырезания, возвращает список."""
    if not os.path.exists(IGNOR_FILE):
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def remove_ignored_words(name, ignore_words):
    """Удаляет все вхождения запрещённых слов из строки name (без учёта регистра)."""
    for word in ignore_words:
        name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)
    return name.strip()


def extract_host_port(config_str):
    """
    Извлекает адрес и порт из строки ключа.
    Поддерживает vmess:// (json в base64), vless://, trojan://, ss://, ssr://,
    hysteria2:// и другие протоколы.
    Возвращает строку "host:port" или None.
    """
    if config_str.startswith('vmess://'):
        try:
            b64_part = config_str[8:]
            if '#' in b64_part:
                b64_part = b64_part.split('#')[0]
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

    for proto in ['vless://', 'trojan://', 'ss://', 'ssr://',
                  'hysteria2://', 'hysteria://', 'tuic://',
                  'socks5://', 'http://', 'https://']:
        if config_str.startswith(proto):
            try:
                main_part = config_str.split('#')[0]
                parsed = urlparse(main_part)
                host = parsed.hostname
                port = parsed.port
                if host and port:
                    return f"{host}:{port}"
                # Особый случай ss://
                if proto == 'ss://':
                    match = re.search(r'@([^:]+):(\d+)', main_part)
                    if match:
                        return f"{match.group(1)}:{match.group(2)}"
            except:
                pass

    # Резервный поиск через @
    match = re.search(r'@([^:\[\]]+):(\d+)', config_str.split('#')[0])
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def fetch_subscription(url):
    """
    Скачивает подписку по URL.
    Пытается декодировать из base64, если содержимое закодировано.
    Возвращает список строк (ключи + возможные комментарии).
    """
    resp = requests.get(url, timeout=30)
    content = resp.text.strip()
    # Попытка base64-декодирования
    try:
        missing = len(content) % 4
        if missing:
            content += '=' * (4 - missing)
        decoded = base64.b64decode(content).decode('utf-8')
        # Проверяем, что в результате есть ключи
        if any(proto in decoded for proto in ['vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://']):
            content = decoded
    except:
        pass
    return [line.strip() for line in content.splitlines() if line.strip()]


def process_source(source_file, output_file, header_template, ignore_words, datetime_str):
    """
    Обрабатывает файл со списком URL подписок:
    - скачивает все ключи,
    - удаляет дубли по host:port,
    - вырезает запрещённые слова из названий (с учётом URL-кодирования),
    - оставляет только валидные ключи (начинающиеся с протокола),
    - записывает результат в output_file с заданным заголовком.
    """
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    # Читаем список URL
    with open(source_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    all_keys = []
    for url in urls:
        try:
            keys = fetch_subscription(url)
            all_keys.extend(keys)
            print(f"[{source_file}] Загружено {len(keys)} ключей из {url}")
        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

    # Удаление дубликатов по хост:порт
    seen_hostports = set()
    unique_keys = []
    for key in all_keys:
        hp = extract_host_port(key)
        if hp is None or hp not in seen_hostports:
            unique_keys.append(key)
            if hp:
                seen_hostports.add(hp)

    # Очистка названий от запрещённых слов с учётом URL-кодирования
    cleaned_keys = []
    for key in unique_keys:
        if '#' in key:
            base_part, name = key.split('#', 1)
            # Декодируем URL-кодировку, чтобы получить читаемое имя
            decoded_name = unquote(name)
            # Удаляем запрещённые слова
            new_name = remove_ignored_words(decoded_name, ignore_words)
            if new_name:
                # Кодируем обратно, чтобы ключ остался валидным
                encoded_name = quote(new_name, safe='')
                cleaned_keys.append(f"{base_part}#{encoded_name}")
            else:
                # Если имя полностью удалилось, оставляем ключ без названия
                cleaned_keys.append(base_part)
        else:
            cleaned_keys.append(key)

    # Фильтр: оставляем только строки, начинающиеся с протокола
    final_keys = [k for k in cleaned_keys if VALID_PROTOCOLS.match(k)]

    # Запись в файл
    header = header_template.format(count=len(final_keys), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))

    print(f"✅ Создан файл {output_file} с {len(final_keys)} ключами.")


def main():
    ignore_words = load_ignore_words()
    # Время по Екатеринбургу (UTC+5)
    now = datetime.now(ZoneInfo("Asia/Yekaterinburg"))
    datetime_str = now.strftime("%d-%m-%Y %H:%M")

    # Основной источник → 🥷КРОТовые ТОННЕЛИ🥷.txt
    process_source(
        source_file="SURS.txt",
        output_file="🥷КРОТовые ТОННЕЛИ🥷.txt",
        header_template=HEADER_SURS,
        ignore_words=ignore_words,
        datetime_str=datetime_str
    )

    # Дополнительный источник → 📡КРОТовые ТОННЕЛИ📡.txt
    process_source(
        source_file="SURS-WHITE.txt",
        output_file="📡КРОТовые ТОННЕЛИ📡.txt",
        header_template=HEADER_WHITE,
        ignore_words=ignore_words,
        datetime_str=datetime_str
    )


if __name__ == "__main__":
    main()
