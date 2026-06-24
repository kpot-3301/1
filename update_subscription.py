import sys
import base64
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, unquote

import requests

# Перенаправляем stdout в stderr, чтобы логи были видны в GitHub Actions
sys.stdout = sys.stderr

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

# ===== НАСТРОЙКИ ПУТЕЙ =====
SOURCES_DIR = "sources"
OUTPUT_DIR = "subscriptions"

SURS_FILE = os.path.join(SOURCES_DIR, "SURS.txt")
SURS_WHITE_FILE = os.path.join(SOURCES_DIR, "SURS-WHITE.txt")
TG_SURS_FILE = os.path.join(SOURCES_DIR, "TG-SURS.txt")
TOR_SURS_FILE = os.path.join(SOURCES_DIR, "TOR-SURS.txt")
CRIPT_FILE = os.path.join(SOURCES_DIR, "Cript")
IGNOR_FILE = "IGNOR-name.txt"

OUTPUT_SURS = os.path.join(OUTPUT_DIR, "🥷КРОТовые ТОННЕЛИ🥷.txt")
OUTPUT_WHITE = os.path.join(OUTPUT_DIR, "📡КРОТовые ТОННЕЛИ📡.txt")
OUTPUT_TG = os.path.join(OUTPUT_DIR, "TGproxy.txt")
OUTPUT_TOR = os.path.join(OUTPUT_DIR, "TOR.txt")

BANNED_HOSTS = ['111.111.111.111', '0.0.0.0', 'sub.limevpn.lol']

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

VALID_PROTOCOLS = re.compile(
    r'^(vmess|vless|trojan|ss|ssr|hysteria2|hysteria|tuic|socks5|http|https)://'
)

# ===== РАСШИФРОВКА ЧЕРЕЗ API happy-decoder.cc =====
def decrypt_via_api(link):
    """Расшифровывает happ:// ссылку через API."""
    try:
        clean_link = link.strip()
        print(f"   🔑 Отправка в API: {clean_link[:80]}...")
        response = requests.post(
            'https://happy-decoder.cc/api/decrypt',
            json={'url': clean_link},
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            data = response.json()
            if 'decryptedUrl' in data and data['decryptedUrl']:
                return data['decryptedUrl']
            else:
                print(f"   ⚠️ API ошибка: {data.get('error', 'неизвестная')}")
                return None
        else:
            print(f"   ❌ API вернул код {response.status_code}")
            return None
    except Exception as e:
        print(f"   ❌ Ошибка API: {e}")
        return None

# ===== ЗАГРУЗКА И РАСШИФРОВКА ССЫЛОК ИЗ Cript =====
def load_and_decrypt_happ_links():
    """Читает файл Cript, расшифровывает каждую ссылку через API,
    затем загружает полученные URL как подписки и возвращает список ключей."""
    print(f"📂 Обработка {CRIPT_FILE}...")
    if not os.path.exists(CRIPT_FILE):
        print(f"   ⚠️ Файл не найден, пропускаю.")
        return []

    try:
        with open(CRIPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        # Удаляем все пробелы и переносы, но разделяем по строкам, чтобы получить отдельные ссылки
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        # Если все в одной строке без переносов, разбиваем по 'happ://'
        if len(lines) == 1 and 'happ://' in lines[0]:
            lines = re.findall(r'happ://crypt5/[A-Za-z0-9+/=]+', lines[0])
        else:
            lines = [ln for ln in lines if ln.startswith('happ://')]

        if not lines:
            print(f"   ⚠️ В файле не найдено ссылок happ://")
            return []

        print(f"   🔗 Найдено {len(lines)} ссылок.")
        all_keys = []
        for idx, link in enumerate(lines):
            print(f"   🔑 Расшифровка ссылки #{idx+1}...")
            decrypted_url = decrypt_via_api(link)
            if not decrypted_url:
                print(f"   ❌ Не удалось расшифровать ссылку.")
                continue
            print(f"   ✅ Расшифрованный URL: {decrypted_url[:100]}...")

            print(f"   📥 Загрузка расшифрованной подписки...")
            keys = fetch_subscription(decrypted_url)
            if keys:
                print(f"   📦 Получено {len(keys)} ключей из расшифрованной подписки.")
                all_keys.extend(keys)
            else:
                print(f"   ⚠️ Не удалось получить ключи из расшифрованной подписки.")

        # Удаляем дубликаты по host:port для всех полученных ключей
        seen = set()
        unique_keys = []
        for key in all_keys:
            hp = extract_host_port(key)
            if hp and hp not in seen:
                seen.add(hp)
                unique_keys.append(key)
            elif not hp:
                if key not in unique_keys:
                    unique_keys.append(key)
        print(f"   🧹 Всего уникальных ключей после расшифровки: {len(unique_keys)}")
        return unique_keys
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return []

# ===== РАБОТА С ИГНОРИРУЕМЫМИ СЛОВАМИ (регистронезависимо) =====
def load_ignore_words():
    if not os.path.exists(IGNOR_FILE):
        print(f"⚠️  Файл {IGNOR_FILE} не найден, фильтрация отключена.")
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8-sig') as f:
        words = [line.strip() for line in f if line.strip()]
    print(f"📝 Загружено {len(words)} игнорируемых слов")
    return words

def remove_ignored_words(name, ignore_words):
    """Удаляет все игнорируемые слова из имени (регистронезависимо)."""
    for word in ignore_words:
        name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)
    return name.strip()

# ---------- ОСТАЛЬНЫЕ ФУНКЦИИ ----------
def extract_host_port(config_str):
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

def extract_host_from_key(key):
    hp = extract_host_port(key)
    if hp:
        return hp.rsplit(':', 1)[0]
    return None

def convert_github_url(url):
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)', url)
    if match:
        user, repo, branch, path = match.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    return url

def convert_dropbox_url(url):
    if 'dropbox.com' in url and 'raw=1' not in url:
        url = re.sub(r'[?&]dl=[01]', '', url)
        if '?' in url:
            url += '&raw=1'
        else:
            url += '?raw=1'
    return url

def _create_session():
    if CLOUDSCRAPER_AVAILABLE:
        return cloudscraper.create_scraper()
    else:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        return session

def fetch_subscription(url):
    raw_url = convert_github_url(url)
    print(f"   📥 Загрузка: {raw_url}")
    session = _create_session()
    try:
        resp = session.get(raw_url, timeout=45)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Ошибка запроса: {e}")
        return []

    content = resp.text.strip()
    # Если содержимое выглядит как base64, декодируем
    if re.match(r'^[A-Za-z0-9+/=]+$', content):
        try:
            missing_padding = len(content) % 4
            if missing_padding:
                content += '=' * (4 - missing_padding)
            decoded = base64.b64decode(content).decode('utf-8')
            content = decoded
        except Exception:
            pass

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    valid_lines = [line for line in lines if VALID_PROTOCOLS.match(line)]
    if not valid_lines:
        found = re.findall(r'(vmess|vless|trojan|ss|ssr|hysteria2?|tuic|socks5)://[^\s\"\'<>]+', content)
        if found:
            lines = found
            print(f"   🔎 Найдено {len(found)} ссылок в HTML")
        else:
            print(f"   ⚠️ Ключи не найдены. Показываю первые 200 символов:\n{content[:200]}")
            return []
    else:
        lines = valid_lines

    print(f"   ✅ Получено {len(lines)} ключей")
    return lines

def fetch_tor_source(url):
    raw_url = convert_github_url(url)
    print(f"   📥 Загрузка: {raw_url}")
    session = _create_session()
    try:
        resp = session.get(raw_url, timeout=45)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Ошибка запроса: {e}")
        return []

    content = resp.text.strip()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    print(f"   ✅ Получено {len(lines)} строк")
    return lines

def clean_name_in_key(key, ignore_words):
    """Очищает имя ключа (часть после # или поле ps) от игнорируемых слов."""
    if '#' in key:
        base_part, encoded_name = key.split('#', 1)
        encoded_name = encoded_name.rstrip('=')
        decoded_name = unquote(encoded_name)
        new_name = remove_ignored_words(decoded_name, ignore_words)
        if new_name:
            return f"{base_part}#{new_name}"
        else:
            return base_part

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
                decoded_ps = unquote(ps)
                new_ps = remove_ignored_words(decoded_ps, ignore_words)
                if new_ps != ps:
                    vmess['ps'] = new_ps
                    new_json = json.dumps(vmess, separators=(',', ':'), ensure_ascii=False)
                    new_b64 = base64.b64encode(new_json.encode()).decode().rstrip('=')
                    return f"vmess://{new_b64}"
            return key
        except Exception:
            return key
    return key

def classify_bridge(line):
    stripped = line.strip()
    if not stripped:
        return None
    lower = stripped.lower()
    if 'webtunnel' in lower:
        return 'webtunnel'
    if 'cert=' in lower:
        return 'obfs4'
    if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', stripped):
        return 'vanilla'
    parts = stripped.split()
    if parts and ':' in parts[0] and re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', parts[0]):
        return 'vanilla'
    return None

def extract_url_from_line(line):
    urls = re.findall(r'https?://\S+', line)
    if urls:
        return urls[-1]
    return line.strip()

def read_urls_from_file(filepath):
    if not os.path.exists(filepath):
        return []
    urls = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '#' in line:
                url = extract_url_from_line(line)
                if url and url.startswith('http'):
                    urls.append(url)
            else:
                urls.append(line)
    return urls

# ========== ОСНОВНАЯ ЛОГИКА ==========
def process_source(source_file, output_file, header_template, ignore_words, datetime_str, extra_keys=None):
    if extra_keys is None:
        extra_keys = []
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    urls = read_urls_from_file(source_file)
    print(f"   🔗 Найдено {len(urls)} URL в {source_file}")

    used_hostports = set()
    # Очищаем имена у ключей из Cript ДО добавления
    happ_keys = []
    for k in extra_keys:
        cleaned = clean_name_in_key(k, ignore_words)
        happ_keys.append(cleaned)

    normal_keys = []

    for url in urls:
        is_happ_source = False
        if url.startswith('happ://'):
            decrypted_url = decrypt_via_api(url)
            if decrypted_url:
                if VALID_PROTOCOLS.match(decrypted_url):
                    keys = [decrypted_url]
                    is_happ_source = True
                else:
                    keys = fetch_subscription(decrypted_url)
                    is_happ_source = True
            else:
                continue
        else:
            keys = fetch_subscription(url)
            is_happ_source = False

        for key in keys:
            if not VALID_PROTOCOLS.match(key):
                continue
            if key.startswith('ss://'):
                continue
            host = extract_host_from_key(key)
            if host and host in BANNED_HOSTS:
                print(f"   🚫 Удалён ключ с запрещённым хостом: {host}")
                continue
            hp = extract_host_port(key)
            if hp and hp in used_hostports:
                continue
            cleaned_key = clean_name_in_key(key, ignore_words)
            if hp:
                used_hostports.add(hp)
            if is_happ_source:
                happ_keys.append(cleaned_key)
            else:
                normal_keys.append(cleaned_key)

    final_keys = happ_keys + normal_keys
    print(f"   🧹 Итоговых ключей: {len(final_keys)} (из них happ: {len(happ_keys)})")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = header_template.format(count=len(final_keys), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))
    print(f"✅ Создан файл {output_file}")

# ---------- TG и TOR (без изменений) ----------
def process_tg_source(source_file, output_file, datetime_str):
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return
    urls = read_urls_from_file(source_file)
    print(f"   🔗 Найдено {len(urls)} URL в {source_file}")
    all_proxies = []
    for url in urls:
        url = convert_dropbox_url(convert_github_url(url))
        print(f"   📥 Загрузка: {url}")
        session = _create_session()
        try:
            resp = session.get(url, timeout=45)
            resp.raise_for_status()
        except Exception as e:
            print(f"   ❌ Ошибка запроса: {e}")
            continue
        lines = resp.text.strip().splitlines()
        proxy_re = re.compile(r'(tg://proxy\S+|tg://socks\S+|https://t\.me/proxy\S+)')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = proxy_re.search(line)
            if match:
                raw = match.group(0)
                raw = re.sub(r'[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]', '', raw)
                if raw.startswith('https://t.me/proxy'):
                    raw = re.sub(r'^https://t\.me/proxy', 'tg://proxy', raw)
                all_proxies.append(raw)
    print(f"   📊 Всего прокси до фильтрации: {len(all_proxies)}")
    seen = set()
    unique_proxies = []
    for proxy in all_proxies:
        match_server = re.search(r'\bserver=([^&]+)', proxy)
        match_port = re.search(r'\bport=(\d+)', proxy)
        match_secret = re.search(r'\bsecret=([^&]+)', proxy)
        if match_server and match_port and match_secret:
            server = match_server.group(1)
            if server in BANNED_HOSTS:
                print(f"   🚫 Удалён TG-прокси с запрещённым сервером: {server}")
                continue
            key = f"{server}:{match_port.group(1)}:{match_secret.group(1)}"
            if key not in seen:
                seen.add(key)
                unique_proxies.append(proxy)
        else:
            if not any(banned in proxy for banned in BANNED_HOSTS):
                unique_proxies.append(proxy)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = HEADER_TG.format(count=len(unique_proxies), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(unique_proxies))
    print(f"✅ Создан файл {output_file} с {len(unique_proxies)} прокси.")

def process_tor_source(source_file, output_file, date_str):
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return
    urls = read_urls_from_file(source_file)
    print(f"   🔗 Найдено {len(urls)} URL в {source_file}")
    bridges_by_type = {'obfs4': set(), 'vanilla': set(), 'webtunnel': set()}
    for url in urls:
        lines = fetch_tor_source(url)
        if not lines:
            continue
        sample = lines[:5]
        print(f"   🔎 Примеры строк:")
        for s in sample:
            print(f"      -> {s[:120]}")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
            bt = classify_bridge(stripped)
            if not bt and re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', stripped):
                bt = 'vanilla'
            if bt:
                stripped = re.sub(r'^\s*(obfs4|webtunnel)\s+', '', stripped, flags=re.IGNORECASE)
                bridges_by_type[bt].add(stripped)
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
                    prefix = f"{t} " if t != 'vanilla' else ""
                    f.write(f"{prefix}{bridge}\n")
    print(f"✅ Создан файл {output_file} с {total} мостами.")

def main():
    print("🔍 Загрузка игнорируемых слов...")
    ignore_words = load_ignore_words()

    cript_keys = load_and_decrypt_happ_links()

    now_ekb = datetime.now(ZoneInfo("Asia/Yekaterinburg"))
    datetime_str_main = now_ekb.strftime("%d-%m-%Y %H:%M")
    datetime_str_tg = now_ekb.strftime("%Y-%m-%d %H:%M:%S")
    date_str_tor = now_ekb.strftime("%Y-%m-%d")

    if CLOUDSCRAPER_AVAILABLE:
        print("🌩  Cloudscraper активирован.")
    else:
        print("ℹ️  Cloudscraper не установлен. Используем обычный requests.")

    print("\n===== 🥷 SURS ===================================")
    process_source(SURS_FILE, OUTPUT_SURS, HEADER_SURS, ignore_words, datetime_str_main, cript_keys)

    print("\n===== 📡 SURS-WHITE ===============================")
    process_source(SURS_WHITE_FILE, OUTPUT_WHITE, HEADER_WHITE, ignore_words, datetime_str_main, cript_keys)

    print("\n===== ✈️ TG PROXY =================================")
    process_tg_source(TG_SURS_FILE, OUTPUT_TG, datetime_str_tg)

    print("\n===== 🧅 TOR BRIDGES =============================")
    process_tor_source(TOR_SURS_FILE, OUTPUT_TOR, date_str_tor)

    print("\n🎉 Все подписки обновлены!")

if __name__ == "__main__":
    main()
