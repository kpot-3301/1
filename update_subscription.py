import sys
import base64
import json
import os
import re
import subprocess
import platform
import glob
import stat
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
BIN_DIR = "bin"

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

# --- BANNED HOSTS FILTER -----------------
BANNED_HOSTS = [
    '111.111.111.111',
    '0.0.0.0',
    'sub.limevpn.lol'
]
# -----------------------------------------

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

# ===== happ-decrypt =====
def get_platform_info():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == 'windows':
        return 'windows', 'x86_64'
    elif system == 'linux':
        if 'android' in platform.platform().lower() or 'termux' in os.environ.get('PREFIX', ''):
            if machine in ('aarch64', 'arm64'):
                return 'android', 'arm64'
            elif machine in ('armv7l', 'armv8l'):
                return 'android', 'armv7'
            else:
                return 'android', 'arm64'
        else:
            if machine in ('x86_64', 'amd64'):
                return 'linux', 'x86_64'
            else:
                return 'linux', 'unknown'
    else:
        return 'unknown', 'unknown'

def download_happ_decrypt():
    print("📥 Попытка автоматической загрузки happ-decrypt-universal...")
    os.makedirs(BIN_DIR, exist_ok=True)
    plat, arch = get_platform_info()
    if plat == 'unknown':
        print("❌ Не удалось определить платформу. Скачайте бинарник вручную.")
        return None
    mapping = {
        ('windows', 'x86_64'): 'windows-x64_x86.exe',
        ('linux', 'x86_64'): 'linux-x64_x86',
        ('android', 'arm64'): 'android-arm64-v8a',
        ('android', 'armv7'): 'android-armeabi-v7a',
    }
    key = (plat, arch)
    if key not in mapping:
        print(f"❌ Нет готового бинарника для {plat}/{arch}. Скачайте вручную.")
        return None
    filename = mapping[key]
    api_url = "https://api.github.com/repos/amurcanov/happ-decrypt-universal/releases/latest"
    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        release_data = resp.json()
    except Exception as e:
        print(f"❌ Не удалось получить информацию о релизе: {e}")
        return None
    asset_url = None
    for asset in release_data.get('assets', []):
        if asset['name'] == filename:
            asset_url = asset['browser_download_url']
            break
    if not asset_url:
        print(f"❌ Файл {filename} не найден в релизе.")
        return None
    try:
        print(f"   ⬇️ Скачивание {filename} ...")
        dl_resp = requests.get(asset_url, stream=True, timeout=30)
        dl_resp.raise_for_status()
        filepath = os.path.join(BIN_DIR, filename)
        with open(filepath, 'wb') as f:
            for chunk in dl_resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        if plat in ('linux', 'android'):
            os.chmod(filepath, os.stat(filepath).st_mode | stat.S_IEXEC)
        print(f"✅ Бинарник сохранён в {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ Ошибка при скачивании: {e}")
        return None

def get_happ_decrypt_binary():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [script_dir, os.path.join(script_dir, BIN_DIR)]
    possible_names = ['happ-decrypt', 'happ-decrypt.exe']
    plat, arch = get_platform_info()
    if plat == 'windows':
        possible_names.append('windows-x64_x86.exe')
    elif plat == 'linux':
        possible_names.append('linux-x64_x86')
    elif plat == 'android':
        if arch == 'arm64':
            possible_names.append('android-arm64-v8a')
        elif arch == 'armv7':
            possible_names.append('android-armeabi-v7a')
        else:
            possible_names.append('android-arm64-v8a')
    for base_dir in search_dirs:
        if not os.path.isdir(base_dir):
            continue
        for name in possible_names:
            candidate = os.path.join(base_dir, name)
            if os.path.isfile(candidate):
                if plat in ('linux', 'android') and not os.access(candidate, os.X_OK):
                    try:
                        os.chmod(candidate, os.stat(candidate).st_mode | stat.S_IEXEC)
                    except:
                        pass
                return candidate
        for f in glob.glob(os.path.join(base_dir, '*')):
            if os.path.isfile(f) and os.access(f, os.X_OK):
                if 'happ' in f.lower() or 'decrypt' in f.lower():
                    return f
    downloaded = download_happ_decrypt()
    if downloaded:
        return downloaded
    print("⚠️  Бинарник happ-decrypt не найден и не удалось скачать. Расшифровка happ:// недоступна.")
    return None

def decrypt_happ_link(link):
    binary = get_happ_decrypt_binary()
    if not binary:
        return None

    # Удаляем непечатаемые символы
    clean_link = re.sub(r'[\x00-\x1f\x7f]', '', link).strip()
    # Отрезаем суффикс ff, если есть
    if clean_link.endswith('ff'):
        clean_link = clean_link[:-2]
    # Оставляем только корректную часть (до последнего допустимого символа)
    match = re.match(r'(happ://crypt5/[A-Za-z0-9+/=]+)', clean_link)
    if match:
        clean_link = match.group(1)
    else:
        valid = re.search(r'[A-Za-z0-9+/=]+$', clean_link)
        if valid:
            clean_link = clean_link[:valid.end()]
        else:
            print(f"   ⚠️ Не удалось очистить ссылку: {link[:80]}...")
            return None

    print(f"   🔑 Очищенная ссылка: {clean_link[:80]}...")

    # Попытка 1: обычный вызов
    try:
        proc = subprocess.run([binary, clean_link], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            output = proc.stdout.strip()
            match_res = re.search(r'^Result\s+(.*)$', output, re.MULTILINE)
            if match_res:
                return match_res.group(1).strip()
            lines = output.splitlines()
            for line in reversed(lines):
                if line and not line.startswith('Input') and not line.startswith('payload') and not line.startswith('marker'):
                    return line.strip()
        else:
            print(f"   ⚠️ Обычный вызов не удался (код {proc.returncode}), пробуем --cli...")
    except Exception as e:
        print(f"   ⚠️ Ошибка при обычном вызове: {e}")

    # Попытка 2: интерактивный режим --cli
    try:
        proc = subprocess.run(
            [binary, '--cli'],
            input=clean_link + '\n',
            capture_output=True,
            text=True,
            timeout=10
        )
        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or proc.stdout.strip()
            if err_msg:
                print(f"   ❌ Ошибка расшифровки (--cli): {err_msg}")
            return None
        output = proc.stdout.strip()
        match_res = re.search(r'^Result\s+(.*)$', output, re.MULTILINE)
        if match_res:
            return match_res.group(1).strip()
        lines = output.splitlines()
        for line in reversed(lines):
            if line and not line.startswith('Input') and not line.startswith('payload') and not line.startswith('marker'):
                return line.strip()
        return None
    except Exception as e:
        print(f"   ❌ Ошибка при вызове бинарника с --cli: {e}")
        return None

# ===== НОВАЯ ФУНКЦИЯ ДЛЯ ЗАГРУЗКИ И РАСШИФРОВКИ ССЫЛОК ИЗ ФАЙЛА Cript =====
def load_and_decrypt_happ_links():
    """Читает файл Cript, собирает ссылки happ:// и расшифровывает их."""
    print(f"📂 Загрузка и расшифровка ссылок из {CRIPT_FILE}...")
    happ_keys = []
    if not os.path.exists(CRIPT_FILE):
        print(f"   ⚠️ Файл {CRIPT_FILE} не найден, пропускаю.")
        return []

    try:
        with open(CRIPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            content = content.replace('\n', '').replace('\r', '').strip()
            
            happ_links = re.findall(r'happ://crypt5/[A-Za-z0-9+/=]+', content)
            
            if not happ_links:
                print(f"   ⚠️ В файле {CRIPT_FILE} не найдено ссылок happ://")
                return []

            print(f"   🔗 Найдено {len(happ_links)} зашифрованных ссылок в {CRIPT_FILE}")

            for link in happ_links:
                decrypted = decrypt_happ_link(link)
                if decrypted:
                    if VALID_PROTOCOLS.match(decrypted):
                        happ_keys.append(decrypted)
                        print(f"   ✅ Расшифрован ключ: {decrypted[:50]}...")
                    else:
                        print(f"   ⚠️ Расшифрованная строка не является ключом: {decrypted[:50]}...")
                else:
                    print(f"   ❌ Не удалось расшифровать ссылку: {link[:80]}...")
                    
    except Exception as e:
        print(f"   ❌ Ошибка при чтении или обработке {CRIPT_FILE}: {e}")
    
    print(f"   🧹 Итоговое количество расшифрованных ключей из Cript: {len(happ_keys)}")
    return happ_keys

# ---------- Остальные функции ----------
def load_ignore_words():
    if not os.path.exists(IGNOR_FILE):
        print(f"⚠️  Файл {IGNOR_FILE} не найден, фильтрация отключена.")
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8-sig') as f:
        words = [line.strip() for line in f if line.strip()]
    print(f"📝 Загружено {len(words)} игнорируемых слов")
    return words

def remove_ignored_words(name, ignore_words):
    for word in ignore_words:
        name = re.sub(re.escape(word), '', name)
    return name.strip()

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
    if not re.search(r'<!DOCTYPE|<html', content, re.IGNORECASE):
        try:
            missing_padding = len(content) % 4
            if missing_padding:
                content += '=' * (4 - missing_padding)
            decoded = base64.b64decode(content).decode('utf-8')
            content = decoded
        except Exception:
            pass

    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if not any(VALID_PROTOCOLS.match(line) for line in lines):
        found = re.findall(r'(vmess|vless|trojan|ss|ssr|hysteria2?|tuic|socks5)://[^\s\"\'<>]+', content)
        if found:
            lines = found
            print(f"   🔎 Найдено {len(found)} ссылок в HTML")
        else:
            print(f"   ⚠️ Ключи не найдены. Показываю первые 200 символов:\n{content[:200]}")
            return []

    print(f"   ✅ Получено {len(lines)} строк")
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

# ========== ОСНОВНАЯ ЛОГИКА (С НОВЫМ ПАРАМЕТРОМ extra_keys) ==========
def process_source(source_file, output_file, header_template, ignore_words, datetime_str, extra_keys=None):
    if extra_keys is None:
        extra_keys = []
    
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    urls = read_urls_from_file(source_file)
    print(f"   🔗 Найдено {len(urls)} URL в {source_file}")

    used_hostports = set()
    happ_keys = list(extra_keys)
    normal_keys = []

    for url in urls:
        is_happ_source = False
        if url.startswith('happ://'):
            decrypted = decrypt_happ_link(url)
            if decrypted:
                keys = [decrypted]
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

# ---------- Обработка TG и TOR ----------
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

# ---------- Главная функция ----------
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
