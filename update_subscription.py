import base64
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, unquote, quote
from collections import OrderedDict
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
    if not os.path.exists(IGNOR_FILE):
        return []
    with open(IGNOR_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def remove_ignored_words(name, ignore_words):
    for word in ignore_words:
        name = re.sub(re.escape(word), '', name, flags=re.IGNORECASE)
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


def convert_github_url(url):
    """
    Если url ведёт на github.com/.../blob/..., преобразует его в raw.
    Иначе возвращает без изменений.
    """
    # Пример: https://github.com/user/repo/blob/branch/path/to/file
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)', url)
    if match:
        user, repo, branch, path = match.groups()
        return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    return url


def fetch_subscription(url):
    raw_url = convert_github_url(url)
    resp = requests.get(raw_url, timeout=30)
    content = resp.text.strip()
    try:
        missing = len(content) % 4
        if missing:
            content += '=' * (4 - missing)
        decoded = base64.b64decode(content).decode('utf-8')
        if any(p in decoded for p in ['vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://', 'tg://proxy']):
            content = decoded
    except Exception:
        pass
    return [line.strip() for line in content.splitlines() if line.strip()]


def process_source(source_file, output_file, header_template, ignore_words, datetime_str):
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

    seen_hostports = set()
    unique_keys = []
    for key in all_keys:
        hp = extract_host_port(key)
        if hp is None or hp not in seen_hostports:
            unique_keys.append(key)
            if hp:
                seen_hostports.add(hp)

    cleaned_keys = []
    for key in unique_keys:
        if '#' in key:
            base_part, name = key.split('#', 1)
            decoded_name = unquote(name)
            new_name = remove_ignored_words(decoded_name, ignore_words)
            if new_name:
                encoded_name = quote(new_name, safe='')
                cleaned_keys.append(f"{base_part}#{encoded_name}")
            else:
                cleaned_keys.append(base_part)
        else:
            cleaned_keys.append(key)

    final_keys = [k for k in cleaned_keys if VALID_PROTOCOLS.match(k)]

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    header = header_template.format(count=len(final_keys), datetime=datetime_str)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(final_keys))

    print(f"✅ Создан файл {output_file} с {len(final_keys)} ключами.")


def process_tg_source(source_file, output_file, datetime_str):
    if not os.path.exists(source_file):
        print(f"⚠️ Файл {source_file} не найден, пропускаю.")
        return

    with open(source_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    all_proxies = []
    for url in urls:
        try:
            lines = fetch_subscription(url)
            tg_lines = [l for l in lines if l.startswith('tg://proxy')]
            all_proxies.extend(tg_lines)
            print(f"[{source_file}] Загружено {len(tg_lines)} прокси из {url}")
        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

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
    Универсальный сборщик Tor-мостов.
    Понимает оба формата: с заголовками # VANILLA TOR BRIDGES и без них.
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

    # Шаблоны заголовков секций для Формата 1
    section_patterns = {
        'vanilla': re.compile(r'# *VANILLA.*BRIDGES', re.IGNORECASE),
        'obfs4': re.compile(r'# *(OBFS4|OBFSPROXY).*BRIDGES', re.IGNORECASE),
        'webtunnel': re.compile(r'# *WEBTUNNEL.*BRIDGES', re.IGNORECASE),
    }

    for url in urls:
        try:
            lines = fetch_subscription(url)
            print(f"[{source_file}] Загружено {len(lines)} строк из {url}")

            # --- Определяем формат: есть ли заголовки секций? ---
            has_sections = False
            for line in lines:
                for pattern in section_patterns.values():
                    if pattern.search(line):
                        has_sections = True
                        break
                if has_sections:
                    break

            # --- Парсинг в зависимости от формата ---
            if has_sections:
                print(f" -> Обнаружен формат с заголовками")
                current_type = None
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue

                    # Проверяем, не начало ли это новой секции
                    found_section = False
                    for btype, pattern in section_patterns.items():
                        if pattern.search(stripped):
                            current_type = btype
                            found_section = True
                            break
                    if found_section:
                        continue

                    # Пропускаем строки с # (комментарии, заголовки)
                    if stripped.startswith('#') or stripped.startswith('//'):
                        continue

                    # Если мы внутри секции
                    if current_type:
                        # Убираем возможный префикс (на случай, если он есть)
                        for prefix in ['obfs4', 'vanilla', 'webtunnel']:
                            if stripped.lower().startswith(prefix):
                                stripped = stripped[len(prefix):].strip()
                                break
                        bridges_by_type[current_type].add(stripped)
            else:
                print(f" -> Обнаружен формат с префиксами")
                # Ищем строки, начинающиеся с префикса
                bridge_pattern = re.compile(r'^(obfs4|vanilla|webtunnel)\b', re.IGNORECASE)
                for line in lines:
                    stripped = line.strip()
                    match = bridge_pattern.match(stripped)
                    if match:
                        btype = match.group(1).lower()
                        # Убираем префикс, чтобы сохранить единообразие
                        content = stripped[len(btype):].strip()
                        bridges_by_type[btype].add(content)

        except Exception as e:
            print(f"[{source_file}] Ошибка загрузки {url}: {e}")

    # Подсчёт
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
