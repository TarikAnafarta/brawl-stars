#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import sys
import json

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import pandas as pd


def to_int(s, default=0):
    if s is None:
        return default
    s = re.sub(r"[^0-9]", "", str(s))
    return int(s) if s != "" else default


def fetch_profile(url, html_file=None, timeout=20):
    """Fetch profile HTML. If html_file is provided and exists, read it.
    Uses requests with retries. On CI (GITHUB_ACTIONS) we avoid launching browsers.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }

    if html_file:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read HTML file {html_file}: {e}") from e

    # use requests with retries to be more robust against transient failures
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    try:
        r = session.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.exceptions.RequestException as req_err:
        # If running in GitHub Actions or other CI, avoid invoking Playwright
        # unless explicitly allowed by ALLOW_PLAYWRIGHT env var. This lets CI
        # opt-in to using Playwright by setting that environment variable.
        if os.environ.get('GITHUB_ACTIONS') and not os.environ.get('ALLOW_PLAYWRIGHT'):
            raise RuntimeError(f"Network fetch failed in CI: {req_err}") from req_err

        # try Playwright only when not in CI and playwright is available
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise RuntimeError(
                "Network fetch failed and Playwright is not installed.\nInstall Playwright and the browsers with:\n  pip install playwright\n  python -m playwright install"
            ) from req_err

        with sync_playwright() as p:
            # Extra flags for CI
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = browser.new_page(user_agent=headers['User-Agent'])
            # increase default timeouts
            page.set_default_navigation_timeout(90000)

            # Block heavy or irrelevant resource types and common analytics domains
            try:
                def _route_handler(route, request):
                    _rtype = request.resource_type
                    url_l = request.url.lower()
                    # abort images, stylesheets, fonts, and known analytics/ads providers to help networkidle
                    if _rtype in ('image', 'stylesheet', 'font'):
                        return route.abort()
                    if any(x in url_l for x in ('google-analytics', 'googletagmanager', 'doubleclick', 'adsservice', 'facebook.net', 'optimizely')):
                        return route.abort()
                    return route.continue_()

                page.route('**/*', _route_handler)
            except Exception:
                # routing may not be available in some older playwright versions, ignore silently
                pass

            last_err = None
            try:
                page.goto(url, wait_until='networkidle', timeout=90000)
            except Exception as e:
                last_err = e
                try:
                    page.goto(url, wait_until='load', timeout=90000)
                except Exception as e2:
                    last_err = e2
                    try:
                        page.goto(url, timeout=90000)
                        page.wait_for_timeout(3000)
                    except Exception as e3:
                        browser.close()
                        raise RuntimeError(f"Playwright failed to load {url}: {e3}") from e3

            # Ensure key content present before taking HTML
            try:
                page.wait_for_selector('div[id^="details-"]', timeout=5000)
            except Exception:
                # ignore: selector may not exist but page content might still be present
                pass

            html = page.content()
            browser.close()
            return html


def parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')

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

                # try to parse trio like (1/2/3) or 1/2/3 with flexible spacing
                txt = counts_div.get_text(" ", strip=True)
                m = re.search(r'\(?\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)?', txt)
                if m:
                    gadgets = to_int(m.group(1))
                    star_powers = to_int(m.group(2))
                    gears = to_int(m.group(3))
                else:
                    # fallback: try anywhere in the header
                    header_txt = header.get_text(" ", strip=True)
                    m2 = re.search(r'\(?\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)?', header_txt)
                    if m2:
                        gadgets = to_int(m2.group(1))
                        star_powers = to_int(m2.group(2))
                        gears = to_int(m2.group(3))
                    else:
                        # last-resort: look for explicit labels
                        g = re.search(r'gadgets\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                        spow = re.search(r'star\s*powers?\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                        gr = re.search(r'gears?\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                        if g: gadgets = to_int(g.group(1))
                        if spow: star_powers = to_int(spow.group(1))
                        if gr: gears = to_int(gr.group(1))
            else:
                # no counts_div - still try to extract from header text
                header_txt = header.get_text(" ", strip=True)
                m3 = re.search(r'\(?\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)?', header_txt)
                if m3:
                    gadgets = to_int(m3.group(1))
                    star_powers = to_int(m3.group(2))
                    gears = to_int(m3.group(3))
                else:
                    g = re.search(r'gadgets\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                    spow = re.search(r'star\s*powers?\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                    gr = re.search(r'gears?\s*[:\-]?\s*(\d+)', header_txt, flags=re.I)
                    if g: gadgets = to_int(g.group(1))
                    if spow: star_powers = to_int(spow.group(1))
                    if gr: gears = to_int(gr.group(1))

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
    parser = argparse.ArgumentParser(description='Export brawlers from brawlify profile')
    parser.add_argument('--url', '-u', default='https://brawlify.com/stats/profile/22PLQCR29')
    parser.add_argument('--html-file', '-f', help='Read profile HTML from local file')
    parser.add_argument('--output', '-o', default='frontend/public/brawlers.json')
    args = parser.parse_args()

    output_json = args.output

    try:
        html = fetch_profile(args.url, html_file=args.html_file)
    except Exception as e:
        # In CI we prefer to avoid failing if there's an existing output file.
        print(f"Warning: failed to fetch profile HTML: {e}")
        if os.path.exists(output_json):
            print(f"Using existing output file: {output_json}")
            return
        else:
            raise

    rows = parse_html(html)
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

    overrides_json = os.path.join(os.path.dirname(output_json), 'overrides.json')
    records = df.fillna('').to_dict(orient='records')

    os.makedirs(os.path.dirname(output_json), exist_ok=True)

    overrides_map = {}
    if os.path.exists(overrides_json):
        try:
            with open(overrides_json, 'r', encoding='utf-8') as of:
                overrides_map = json.load(of) or {}
        except Exception:
            overrides_map = {}
    else:
        for r in records:
            name = r.get('Brawler')
            if not name or str(name).strip().upper() == 'TOTAL':
                continue
            overrides_map[name] = {'Hypercharge': 'Yes'}

    merged_records = []
    for r in records:
        name = r.get('Brawler')
        extra = overrides_map.get(name, {})
        merged = {**r, **extra}
        merged_records.append(merged)

    prev_path = os.path.join(os.path.dirname(output_json), 'brawlers.prev.json')
    if os.path.exists(output_json):
        try:
            shutil.copyfile(output_json, prev_path)
        except Exception:
            pass

    with open(output_json, 'w', encoding='utf-8') as jf:
        json.dump(merged_records, jf, ensure_ascii=False, indent=2)

    print(f'Kaydedildi: {output_json}')


if __name__ == '__main__':
    main()