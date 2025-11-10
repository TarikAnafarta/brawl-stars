import json

# generate_overrides.py — lightweight utility to regenerate overrides.json from current brawlers.json
# This script is optional; export_brawlers.py constructs overrides in-memory if overrides.json is missing.

try:
    with open('frontend/public/brawlers.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print('frontend/public/brawlers.json not found')
    exit(1)

out = {}
for r in data:
    name = r.get('Brawler')
    if not name:
        continue
    if str(name).upper() == 'TOTAL':
        continue
    out[name] = {'Hypercharge': 'Yes'}

with open('frontend/public/overrides.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print('WROTE', len(out), 'overrides')
