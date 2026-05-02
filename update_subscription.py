import base64
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, unquote, quote
import requests

# ===== НАСТРОЙКИ ПУТЕЙ =====
SOURCES_DIR = "sources"
OUTPUT_DIR = "subscriptions"

SURS_FILE = os.path.join(SOURCES_DIR, "SURS.txt")
SURS_WHITE_FILE = os.path.join(SOURCES_DIR, "SURS-WHITE.txt")
TG_SURS_FILE = os.path.join(SOURCES_DIR, "TG-SURS.txt")
TOR_SURS_FILE = os.path.join(SOURCES_DIR, "TOR-SURS.txt")
IGNOR_FILE = os.path.join(SOURCES_DIR, "IGNOR-name.txt")

OUTPUT_SURS = os.path.join(OUTPUT_DIR, "🥷КРОТовые ТОННЕЛИ🥷.txt")
OUTPUT_WHITE = os.path.join(OUTPUT_DIR, "📡КРОТовые ТОННЕЛИ📡.txt")
OUTPUT_TG = os.path.join(OUTPUT_DIR, "TGproxy.txt")
OUTPUT_TOR = os.path.join(OUTPUT_DIR, "TOR.txt")

# ===== ШАБЛОНЫ ЗАГОЛОВКОВ =====
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

HEADER_TG = """// --- TG PROXY STATISTICS ---
// Updated      : {datetime}
// Working (verified): {count}
"""

HEADER_TOR = """=== TOR BRIDGES REPORT ({date}) ===
Total: {total} | obfs4: {obfs4} | webtunnel: {webtunnel} | vanilla: {vanilla}
========================================
"""

# Допустимые протоколы для VPN-ключей
VALID_PROTOCOLS = re.compile(
    r'^(vmess|vless|trojan|ss|ssr|hysteria2|hysteria|tuic|socks5|http|https)://'
)


def load_ignore_words():
    """Читает список игнорируемых слов из файла IGNOR-name.txt"""
    if not os.path.exists(IGNOR_FILE):
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def remove_ignored_words(name, ignore_words):
    """Удаляет все вхождения игнорируемых слов из строки (с учётом регистра)."""
    for word in ignore_words:
        # re.escape(word) чтобы спецсимволы не ломали регулярку
        name = re.sub(re.escape(word), '', name)
    return name.strip()


def extract_host_port(config_str):
    """Извлекает host:port из конфигурационной строки (для дедупликации)."""
    if config_str.startswith('vmess://'):
        try:
            b64_part = config_str[8:]
            if '#' in b64_part:
                b64_part = b64_part.split('#')[0]
            missing_padding = len(b64_part) % 4
            if missing_padding:
                b64_part += '=' * (4 - missing_padding)
            decoded = base64.b64decode(b64_part).decode('utf-8')
            vmess = json.loads(decoded)
            host = vmess.get('add')
            port = vmess.get('port')
            if host and port:
                return f"{host}:{port}"
        except Exception:
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
                if proto == 'ss://':
                    match = re.search(r'@([^:]+):(\d+)', main_part)
                    if match:
                        return f"{match.group(1)}:{match.group(2)}"
            except Exception:
                pass

    match = re.search(r'@([^:\[\]]+):(\d+)', config_str.split('#')[0])
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def convert_github_url(url):
    """Преобразует github.com/.../blob/... в raw.githubusercontent.com/..."""
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)', url)
    if match:
        user, repo, branch, path = match.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    return url


def fetch_subscription(url):
    """Загружает подписку, декодирует base64 если нужно, возвращает список строк."""
    raw_url = convert_github_url(url)
    resp = requests.get(raw_url, timeout=30)
    content = resp.text.strip()
    try:
        missing = len(content) % 4
        if missing:
            content += '=' * (4 - missing)
        decoded = base64.b64decode(content).decode('utf-8')
        content = decoded
    except Exception:
        pass
    return [line.strip() for line in content.splitlines() if line.strip()]


def clean_name_in_key(key, ignore_words):
    """
    Универсальная очистка имени ключа:
    - Если есть фрагмент '#', имя декодируется (unquote) и чистится.
    - Для vmess:// без '#' обрабатывается поле 'ps' в JSON.
    - Для остальных протоколов без '#' возвращается без изменений.
    """
    # Случай 1: есть '#'
    if '#' in key:
        base_part, name = key.split('#', 1)
        decoded_name = unquote(name)          # декодируем %XX
        new_name = remove_ignored_words(decoded_name, ignore_words)
        if new_name:
            encoded_name = quote(new_name, safe='')
            return f"{base_part}#{encoded_name}"
        else:
            return base_part

    # Случай 2: vmess:// без '#', работаем с полем 'ps'
    if key.startswith('vmess://'):
        try:
            b64_part = key[8:]
            if '?' in b64_part:
                b64_part = b64_part.split('?')[0]
            missing_padding = len(b64_part) % 4
            if missing_padding:
                b64_part += '=' * (4 - missing_padding)
            decoded = base64.b64decode(b64_part).decode('utf-8')
            vmess = json.loads(decoded)
            ps = vmess.get('ps', '')
            if ps:
                # декодируем ps (вдруг там тоже %XX) и чистим
                new_ps = remove_ignored_words(unquote(ps), ignore_words)
                if new_ps != ps:
                    vmess['ps'] = new_ps
                    new_json = json.dumps(vmess, separators=(',', ':'), ensure_ascii=False)
                    new_b64 = base64.b64encode(new_json.encode()).decode().rstrip('=')
                    return f"vmess://{new_b64}"
            return key
        except Exception:
            return key

    # Случай 3: все остальные ключи без имени
    return key


def classify_bridge(line: str):
    """
    Возвращает тип моста: 'obfs4', 'webtunnel', 'vanilla' или None.
    Определяет по характерным признакам в строке.
    """
    stripped = line.strip()
    if not stripped:
        return None

    lower = stripped.lower()

    if 'webtunnel' in lower:
        return 'webtunnel'

    if 'cert=' in lower:
        return 'obfs4'

    parts = stripped.split()
    if len(parts) >= 1:
        if ':' in parts[0]:
            if len(parts) >= 2 and len(parts[1]) >= 20:
                return 'vanilla'
            elif len(parts) == 1:
                return 'vanilla'

    return None


def process_source(source_file, output_file, header_template, ignore_words, datetime_str):
    """Обрабатывает файл с URL-ами подписок (SURS.txt и SURS-WHITE.txt)."""
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

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

    # Удаление дубликатов по host:port
    seen_hostports = set()
    unique_keys = []
    for key in all_keys:
        hp = extract_host_port(key)
        if hp is None or hp not in seen_hostports:
            unique_keys.append(key)
            if hp:
                seen_hostports.add(hp)

    # Очистка имён (с декодированием и фильтрацией игнор-слов)
    cleaned_keys = [clean_name_in_key(k, ignore_words) for k in unique_keys]

    # Оставляем только корректные протоколы
    final_keys = [k for k in cleaned_keys if VALID_PROTOCOLS.match(k)]

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = header_template.format(count=len(final_keys), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))

    print(f"✅ Создан файл {output_file} с {len(final_keys)} ключами.")


def process_tg_source(source_file, output_file, datetime_str):
    """
    Сбор Telegram-прокси (tg://proxy и https://t.me/proxy).
    Все https:// ссылки преобразуются в tg://proxy?...
    """
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    with open(source_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    all_proxies = []
    for url in urls:
        try:
            lines = fetch_subscription(url)
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('https://t.me/proxy?'):
                    converted = re.sub(r'^https://t\.me/proxy\?', 'tg://proxy?', stripped)
                    all_proxies.append(converted)
                elif stripped.startswith('tg://proxy'):
                    all_proxies.append(stripped)
            print(f"[{source_file}] Загружено {len(all_proxies)} прокси из {url}")
        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

    # Удаление дубликатов по server:port
    seen_hostports = set()
    unique_proxies = []
    for proxy in all_proxies:
        match_server = re.search(r'\bserver=([^&]+)', proxy)
        match_port = re.search(r'\bport=(\d+)', proxy)
        if match_server and match_port:
            hp = f"{match_server.group(1)}:{match_port.group(1)}"
            if hp not in seen_hostports:
                seen_hostports.add(hp)
                unique_proxies.append(proxy)
        else:
            unique_proxies.append(proxy)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = HEADER_TG.format(count=len(unique_proxies), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(unique_proxies))

    print(f"✅ Создан файл {output_file} с {len(unique_proxies)} прокси.")


def process_tor_source(source_file, output_file, date_str):
    """
    Универсальный сборщик Tor-мостов без привязки к заголовкам.
    Тип моста определяется по содержимому строки (classify_bridge).
    """
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    with open(source_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    bridges_by_type = {
        'obfs4': set(),
        'vanilla': set(),
        'webtunnel': set()
    }

    for url in urls:
        try:
            lines = fetch_subscription(url)
            print(f"[{source_file}] Загружено {len(lines)} строк из {url}")

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                    continue

                bridge_type = classify_bridge(stripped)
                if bridge_type:
                    bridges_by_type[bridge_type].add(stripped)
                else:
                    if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', stripped):
                        bridges_by_type['vanilla'].add(stripped)
        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

    types = ['obfs4', 'webtunnel', 'vanilla']
    counts = {t: len(bridges_by_type[t]) for t in types}
    total = sum(counts.values())

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = HEADER_TOR.format(
        date=date_str,
        total=total,
        obfs4=counts['obfs4'],
        webtunnel=counts['webtunnel'],
        vanilla=counts['vanilla']
    )

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        for t in types:
            if bridges_by_type[t]:
                f.write(f"\n#{t}\n")
                for bridge in sorted(bridges_by_type[t]):
                    if t == 'vanilla':
                        f.write(f"{bridge}\n")
                    else:
                        f.write(f"{t} {bridge}\n")

    print(f"✅ Создан файл {output_file} с {total} мостами.")


def main():
    ignore_words = load_ignore_words()

    now_ekb = datetime.now(ZoneInfo("Asia/Yekaterinburg"))
    datetime_str_main = now_ekb.strftime("%d-%m-%Y %H:%M")
    datetime_str_tg = now_ekb.strftime("%Y-%m-%d %H:%M:%S")
    date_str_tor = now_ekb.strftime("%Y-%m-%d")

    process_source(SURS_FILE, OUTPUT_SURS, HEADER_SURS, ignore_words, datetime_str_main)
    process_source(SURS_WHITE_FILE, OUTPUT_WHITE, HEADER_WHITE, ignore_words, datetime_str_main)
    process_tg_source(TG_SURS_FILE, OUTPUT_TG, datetime_str_tg)
    process_tor_source(TOR_SURS_FILE, OUTPUT_TOR, date_str_tor)


if __name__ == "__main__":
    main()
