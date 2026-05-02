import base64
import re
import os
from datetime import datetime
from urllib.parse import urlparse
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
    Пытается извлечь адрес (или IP) и порт из строки конфигурации.
    Поддерживает vmess://, vless://, trojan://, ss://, ssr://, hysteria2:// и т.д.
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

    for proto in ['vless://','trojan://','ss://','ssr://','hysteria2://','hysteria://','tuic://',
                  'socks5://','http://','https://']:
        if config_str.startswith(proto):
            try:
                main_part = config_str.split('#')[0]
                parsed = urlparse(main_part)
                host = parsed.hostname
                port = parsed.port
                if host and port:
                    return f"{host}:{port}"
                if proto == 'ss://':
                    match = re.search(r'@([^:]+):(\d+)', main_part)
                    if match:
                        return f"{match.group(1)}:{match.group(2)}"
            except:
                pass

    match = re.search(r'@([^:\[\]]+):(\d+)', config_str.split('#')[0])
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def fetch_subscription(url):
    """Скачивает подписку по URL, при необходимости декодирует base64,
    возвращает список строк-ключей."""
    resp = requests.get(url, timeout=30)
    content = resp.text.strip()
    try:
        missing = len(content) % 4
        if missing:
            content += '=' * (4 - missing)
        decoded = base64.b64decode(content).decode('utf-8')
        if any(proto in decoded for proto in ['vmess://','vless://','trojan://','ss://','ssr://']):
            content = decoded
    except:
        pass
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return lines


def process_source(source_file, output_file, header_template, ignore_words, datetime_str):
    """
    source_file – имя файла со списком URL (например, SURS.txt)
    output_file – имя выходного файла
    header_template – строка с плейсхолдерами {count} и {datetime}
    datetime_str – готовая строка даты/времени
    """
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    # Читаем URL
    with open(source_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    # Скачиваем все ключи
    all_keys = []
    for url in urls:
        try:
            keys = fetch_subscription(url)
            all_keys.extend(keys)
            print(f"[{source_file}] Загружено {len(keys)} ключей из {url}")
        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

    # Удаляем дубликаты по хост:порт
    seen_hostports = set()
    unique_keys = []
    for key in all_keys:
        hp = extract_host_port(key)
        if hp is None or hp not in seen_hostports:
            unique_keys.append(key)
            if hp:
                seen_hostports.add(hp)

    # Очищаем названия
    final_keys = []
    for key in unique_keys:
        if '#' in key:
            base_part, name = key.split('#', 1)
            cleaned_name = remove_ignored_words(name, ignore_words)
            new_key = f"{base_part}#{cleaned_name}" if cleaned_name else base_part
            final_keys.append(new_key)
        else:
            final_keys.append(key)

    # Записываем файл
    header = header_template.format(count=len(final_keys), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))

    print(f"✅ Создан файл {output_file} с {len(final_keys)} ключами.")


def main():
    ignore_words = load_ignore_words()
    now = datetime.now()
    datetime_str = now.strftime("%d-%m-%Y %H:%M")

    # Обработка основного источника
    process_source(
        source_file="SURS.txt",
        output_file="🥷КРОТовые ТОННЕЛИ🥷.txt",
        header_template=HEADER_SURS,
        ignore_words=ignore_words,
        datetime_str=datetime_str
    )

    # Обработка дополнительного источника (WHITE)
    process_source(
        source_file="SURS-WHITE.txt",
        output_file="📡КРОТовые ТОННЕЛИ📡.txt",
        header_template=HEADER_WHITE,
        ignore_words=ignore_words,
        datetime_str=datetime_str
    )


if __name__ == "__main__":
    main()
