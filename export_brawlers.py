#!/usr/bin/env python3

import os
import json
import requests
import urllib.parse
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from zoneinfo import ZoneInfo

# Credentials must be provided via environment variables for security
# Trim whitespace and allow TAG to be provided with or without a leading '#'
API_KEY = os.environ.get('BRAWL_API_KEY', '').strip()
TAG = os.environ.get('BRAWL_TAG', '').strip().lstrip('#')
OUTPUT_JSON = os.environ.get('OUTPUT_JSON') or 'frontend/public/brawlers.json'
HISTORY_JSON = os.path.join(os.path.dirname(OUTPUT_JSON), 'hourly_changes.json')
HISTORY_MAX = 24


def to_int(s, default=0):
    if s is None:
        return default
    try:
        return int(s)
    except Exception:
        s = ''.join(ch for ch in str(s) if ch.isdigit() or ch == '-')
        try:
            return int(s)
        except Exception:
            return default


def points_and_coins_to_max_for_power(power):
    """Return (points_to_max, coins_to_max) required to reach power 11 from current power.
    Upgrade costs are per-level (cost to go from level L to L+1) as provided.
    """
    upgrade_costs = [
        (20, 20),    # 1->2
        (30, 35),    # 2->3
        (50, 75),    # 3->4
        (80, 140),   # 4->5
        (130, 290),  # 5->6
        (210, 480),  # 6->7
        (340, 800),  # 7->8
        (550, 1250), # 8->9
        (890, 1875), # 9->10
        (1440, 2800) # 10->11
    ]

    p = to_int(power, default=1)
    if p < 1:
        p = 1
    if p >= 11:
        return 0, 0

    total_points = 0
    total_coins = 0
    for lvl in range(p, 11):
        pts, coins = upgrade_costs[lvl - 1]
        total_points += pts
        total_coins += coins

    return total_points, total_coins


def fetch_player_from_brawlstars(tag, api_key, timeout=20):
    """Fetch player JSON from the official Brawl Stars API using the provided API key.
    The player tag may be provided with or without the leading '#'.

    Returns parsed JSON dict on success or raises an exception on error.
    """
    if not api_key:
        raise RuntimeError('API key is required to fetch from Brawl Stars API')

    # Ensure tag is safe for use in a URL; the API expects the tag to be prefixed with '%23' (encoded '#')
    safe_tag = urllib.parse.quote(tag, safe='')
    url = f'https://api.brawlstars.com/v1/players/%23{safe_tag}'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
        'User-Agent': 'Brawl Exporter/1.0'
    }

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    try:
        r = session.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, 'status_code', None)
        # Provide a clearer error for authentication/permission issues
        if status in (401, 403):
            raise RuntimeError(
                f'Brawl Stars API returned {status} (Unauthorized/Forbidden).\n'
                'Possible causes: invalid API key, missing permissions, or API key not available to this runner.\n'
                'Ensure repository secret BRAWL_API_KEY exists and the workflow exposes it via env.'
            ) from e
        raise

    return r.json()


def parse_player_json(data):
    """Convert Brawl Stars player JSON into the rows structure used by the project.
    """
    rows = []
    if not isinstance(data, dict):
        return rows

    brawlers = data.get('brawlers') or []
    for b in brawlers:
        name = b.get('name') or b.get('id') or 'UNKNOWN'
        power = to_int(b.get('power'))
        trophies = to_int(b.get('trophies'))

        gadgets_val = b.get('gadgets')
        gadgets = len(gadgets_val) if isinstance(gadgets_val, list) else to_int(gadgets_val)

        star_val = b.get('starPowers') or b.get('star_powers')
        star_powers = len(star_val) if isinstance(star_val, list) else to_int(star_val)

        gears_val = b.get('gears') or b.get('gear')
        gears = len(gears_val) if isinstance(gears_val, list) else to_int(gears_val)

        points_to_max, coins_to_max = points_and_coins_to_max_for_power(power)

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


def load_json_safe(path):
    """Load JSON data from a file, return None if any error occurs."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_json_safe(path, data):
    """Save JSON data to a file, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_trophies_map(records):
    """Build a map of brawler names to trophy counts from the records."""
    return {r.get('Brawler'): to_int(r.get('Trophies')) for r in records if r.get('Brawler')}


def format_changes(prev_map, curr_map):
    """Format the changes in trophies between two maps for display."""
    # calculate diffs for brawlers present in either
    names = set(prev_map.keys()) | set(curr_map.keys())
    changes = []
    total = 0
    for n in sorted(names):
        prev = prev_map.get(n, 0)
        curr = curr_map.get(n, 0)
        diff = curr - prev
        if diff != 0:
            sign = '+' if diff > 0 else ''
            changes.append(f"{n} {sign}{diff}")
            total += diff
            if len(changes) >= 24:
                break
    return changes, total


def current_turkey_timestamp():
    """Return the current timestamp in Turkey timezone."""
    tz = ZoneInfo('Europe/Istanbul')
    now = datetime.now(tz)
    return now.strftime('%Y-%m-%d %H:%M %Z')


def main():
    # ensure credentials provided
    if not API_KEY:
        print('Error: BRAWL_API_KEY environment variable is not set or is empty.')
        print('Set it in your environment or GitHub Actions secrets as BRAWL_API_KEY and expose it to the workflow (env: BRAWL_API_KEY: ${{ secrets.BRAWL_API_KEY }}).')
        sys.exit(2)
    if not TAG:
        print('Error: BRAWL_TAG environment variable is not set or is empty.')
        print('Set it in your environment or GitHub Actions secrets as BRAWL_TAG (without the leading #).')
        sys.exit(2)

    # fetch current data from API
    try:
        player_json = fetch_player_from_brawlstars(TAG, API_KEY)
    except RuntimeError as e:
        print(f'Error: {e}')
        sys.exit(2)
    except requests.exceptions.RequestException as e:
        print(f'Network/API request failed: {e}')
        sys.exit(2)

    rows = parse_player_json(player_json)

    if not rows:
        print('No brawlers found in API response.')
        return

    # compute totals and append TOTAL row
    total_trophies = sum(to_int(r.get('Trophies')) for r in rows)
    total_points = sum(to_int(r.get('Points to MAX')) for r in rows)
    total_coins = sum(to_int(r.get('Coins to MAX')) for r in rows)

    total_row = {
        'Brawler': 'TOTAL',
        'Power': '',
        'Trophies': total_trophies,
        'Gadgets': '',
        'Star Powers': '',
        'Gears': '',
        'Points to MAX': total_points,
        'Coins to MAX': total_coins
    }

    merged_records = rows + [total_row]

    # read previous output (if any) to compute trophy changes
    prev_records = load_json_safe(OUTPUT_JSON) or []
    prev_map = build_trophies_map(prev_records)
    curr_map = build_trophies_map(rows)

    changes, total_diff = format_changes(prev_map, curr_map)

    # prepare history card
    timestamp = current_turkey_timestamp()
    card_lines = changes[:24]
    # ensure total line last
    card = {
        'timestamp': timestamp,
        'lines': card_lines,
        'total': total_diff
    }

    # load existing history, prepend new card, trim to HISTORY_MAX
    history = load_json_safe(HISTORY_JSON) or []
    history.insert(0, card)
    if len(history) > HISTORY_MAX:
        history = history[:HISTORY_MAX]

    # write outputs
    save_json_safe(OUTPUT_JSON, merged_records)
    save_json_safe(HISTORY_JSON, history)

    print(f'Saved: {OUTPUT_JSON} and updated history with timestamp {timestamp}')


if __name__ == '__main__':
    main()