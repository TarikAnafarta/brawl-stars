import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json


def to_int(s, default=0):
    if s is None:
        return default
    s = re.sub(r"[^0-9]", "", str(s))
    return int(s) if s != "" else default


def fetch_profile(url, out_path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }

    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        html = r.text
    except requests.exceptions.HTTPError as http_err:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise RuntimeError(
                "requests returned HTTP error and Playwright is not installed.\nInstall Playwright and the browsers with:\n  pip install playwright\n  playwright install"
            ) from http_err

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=headers['User-Agent'])
            page.goto(url, wait_until='networkidle')
            html = page.content()
            browser.close()
    except Exception:
        raise

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)


def parse_file(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        soup = BeautifulSoup(f, 'html.parser')

    rows = []
    blocks = soup.find_all('div', id=re.compile(r'^\d+$'))

    for block in blocks:
        header = block.find('div', attrs={'data-bs-toggle': 'collapse'})

        name = 'UNKNOWN'
        power = 0
        trophies = 0
        gadgets = 0
        star_powers = 0
        gears = 0
        points_to_max = 0
        coins_to_max = 0

        if header:
            h3 = header.find('h3')
            if h3:
                span = h3.find('span')
                name = span.get_text(strip=True) if span and span.get_text(strip=True) else h3.get_text(strip=True)
            else:
                img = header.find('img', class_='emoji-ico')
                if img and img.has_attr('alt'):
                    name = img['alt'].strip()

            counts_div = header.find('div', class_=lambda c: c and 'd-none' in c and 'd-sm-block' in c)
            if counts_div:
                trophy_span = None
                for sp in counts_div.find_all('span'):
                    cl = sp.get('class') or []
                    if any('text-orange' == x or 'text-orange' in x for x in cl) and sp.find('img'):
                        trophy_span = sp
                        break
                if trophy_span:
                    trophies = to_int(trophy_span.get_text())

                txt = counts_div.get_text(" ", strip=True)
                m = re.search(r'\((\d+)\/(\d+)\/(\d+)\)', txt)
                if m:
                    gadgets = to_int(m.group(1))
                    star_powers = to_int(m.group(2))
                    gears = to_int(m.group(3))

        details = block.find('div', id=lambda x: x and str(x).startswith('details-'))
        if details:
            table = details.find('table', class_=lambda c: c and 'tb-stats' in c)
            if table:
                for tr in table.find_all('tr'):
                    th = tr.find('th')
                    td = tr.find('td')
                    if not th or not td:
                        continue
                    label = th.get_text(" ", strip=True).lower()
                    val = td.get_text(" ", strip=True)
                    if 'power' in label and 'points to max' not in label:
                        power = to_int(val)
                    elif 'points to max' in label:
                        points_to_max = to_int(val)
                    elif 'coins to max' in label:
                        coins_to_max = to_int(val)

        rows.append({
            'Brawler': name,
            'Power': power,
            'Trophies': trophies,
            'Gadgets': gadgets,
            'Star Powers': star_powers,
            'Gears': gears,
            'Points to MAX': points_to_max,
            'Coins to MAX': coins_to_max
        })

    return rows


def main():
    input_path = r'c:\Users\tarik\Desktop\brawl\22PLQCR29'
    output_path = r'c:\Users\tarik\Desktop\brawl\brawlers.xlsx'

    fetch_profile('https://brawlify.com/stats/profile/22PLQCR29', input_path)

    rows = parse_file(input_path)
    if not rows:
        print('Hiç brawler bulunamadı. Dosya yolunu kontrol edin.')
        return

    df = pd.DataFrame(rows, columns=['Brawler', 'Power', 'Trophies', 'Gadgets', 'Star Powers', 'Gears', 'Points to MAX', 'Coins to MAX'])

    total_trophies = int(df['Trophies'].sum()) if 'Trophies' in df.columns else 0
    total_points_to_max = int(df['Points to MAX'].sum()) if 'Points to MAX' in df.columns else 0
    total_coins_to_max = int(df['Coins to MAX'].sum()) if 'Coins to MAX' in df.columns else 0

    total_row = {
        'Brawler': 'TOTAL',
        'Power': '',
        'Trophies': total_trophies,
        'Gadgets': '',
        'Star Powers': '',
        'Gears': '',
        'Points to MAX': total_points_to_max,
        'Coins to MAX': total_coins_to_max
    }
    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Brawlers')
        ws = writer.sheets['Brawlers']
        ws['J1'] = 'Total Trophies'
        ws['J2'] = total_trophies
        ws['K1'] = 'Total Points to MAX'
        ws['K2'] = total_points_to_max
        ws['L1'] = 'Total Coins to MAX'
        ws['L2'] = total_coins_to_max

    # write JSON (same data)
    output_json = r'c:\Users\tarik\Desktop\brawl\brawlers.json'
    records = df.fillna('').to_dict(orient='records')
    with open(output_json, 'w', encoding='utf-8') as jf:
        json.dump(records, jf, ensure_ascii=False, indent=2)

    print(f'Kaydedildi: {output_path} and {output_json}')


if __name__ == '__main__':
    main()