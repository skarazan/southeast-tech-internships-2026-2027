import json
import os
import urllib.request
import hashlib

UPSTREAM_URL = "https://raw.githubusercontent.com/ctsc/southeast-tech-internships-2026-2027/main/data/jobs.json"
LOCAL_PATH = ".github/data/filtered_jobs.json"
NOTIFIED_PATH = ".github/data/notified_hashes.json"

SIBLING_HASH_URLS = [
    "https://raw.githubusercontent.com/skarazan/Summer2027-Internships/dev/.github/scripts/notified_hashes.json",
    "https://raw.githubusercontent.com/skarazan/Summer2026-Internships-NYC/dev/.github/scripts/notified_hashes.json",
    "https://raw.githubusercontent.com/skarazan/Internships-2026/main/.github/data/notified_hashes.json",
]

def is_phd(entry):
    role = (entry.get("role") or "").lower()
    return "phd" in role or "ph.d" in role or entry.get("requires_advanced_degree", False)

NON_US_KEYWORDS = ("uk", "united kingdom", "london", "england", "scotland",
                    "ireland", "canada", "india", "europe", "germany", "munich",
                    "toronto", "chennai", "hyderabad", "telangana", "tamil nadu")

def is_nyc_or_remote_usa(entry):
    locations = entry.get("locations", [])
    has_nyc = False
    has_remote_usa = False
    has_non_us = False

    for loc in locations:
        l = loc.lower()
        if any(kw in l for kw in NON_US_KEYWORDS):
            has_non_us = True
            continue
        if any(kw in l for kw in ("new york", "nyc", "brooklyn")):
            has_nyc = True
        if "manhattan" in l and "beach" not in l:
            has_nyc = True
        if "remote" in l:
            # only accept remote with US qualifiers or bare "Remote"
            if any(kw in l for kw in ("us", "usa", "united states")):
                has_remote_usa = True
            elif l.strip() in ("remote", "6314 remote", "teleworker us"):
                has_remote_usa = True
            # "Remote - Florida", "Remote - Virginia" etc. are US
            elif l.startswith("remote -") or l.startswith("remote in"):
                if not any(kw in l for kw in NON_US_KEYWORDS):
                    has_remote_usa = True

    # Only trust remote_friendly if listing has at least one US location
    # and no non-US locations that suggest it's international
    if entry.get("remote_friendly", False) and has_nyc:
        has_remote_usa = True

    return has_nyc or has_remote_usa

def is_fall_or_winter(entry):
    season = (entry.get("season") or "").lower()
    return "fall" in season or "winter" in season

def job_hash(entry):
    key = f"{entry.get('company','').lower().strip()}|{entry.get('role','').lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def fetch_sibling_hashes():
    hashes = set()
    for url in SIBLING_HASH_URLS:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                hashes.update(json.loads(resp.read()))
        except Exception:
            pass
    return hashes

print("Fetching upstream jobs...")
with urllib.request.urlopen(UPSTREAM_URL) as resp:
    data = json.loads(resp.read())

upstream = data.get("listings", [])
filtered = [
    e for e in upstream
    if is_fall_or_winter(e)
    and not is_phd(e)
    and is_nyc_or_remote_usa(e)
    and e.get("status") == "open"
]
print(f"Upstream: {len(upstream)} -> Filtered (Fall/Winter + NYC/Remote USA - no PhD): {len(filtered)}")

old_filtered = load_json(LOCAL_PATH)
old_ids = {e["id"] for e in old_filtered}

added = [e for e in filtered if e["id"] not in old_ids]

notified = set()
if os.path.exists(NOTIFIED_PATH):
    with open(NOTIFIED_PATH) as f:
        notified = set(json.load(f))
sibling_hashes = fetch_sibling_hashes()
all_known = notified | sibling_hashes

deduped = [e for e in added if job_hash(e) not in all_known]
skipped = len(added) - len(deduped)
print(f"New: {len(added)}, After dedup: {len(deduped)} (skipped {skipped})")

os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
with open(LOCAL_PATH, "w") as f:
    json.dump(filtered, f, indent=2)

output_file = os.environ.get("GITHUB_OUTPUT", "/dev/null")
if deduped:
    for e in deduped:
        notified.add(job_hash(e))
    with open(NOTIFIED_PATH, "w") as f:
        json.dump(sorted(notified), f)

    MAX_SHOW = 5
    lines = []
    for e in deduped[:MAX_SHOW]:
        locs = ", ".join(e.get("locations", []))
        if e.get("remote_friendly"):
            locs = f"{locs} (Remote)" if locs else "Remote"
        url = e.get("apply_url", "")
        lines.append(f"🆕 **{e['company']}** — {e['role']}\n📍 {locs}\n🔗 <{url}>")
    extra = len(deduped) - len(lines)
    if extra > 0:
        lines.append(f"...and **{extra} more** — check the README")
    message = "@everyone\n\n" + "\n\n".join(lines)
    with open(".github/scripts/discord_message.txt", "w") as f:
        f.write(message)
    with open(output_file, "a") as f:
        f.write("has_changes=true\n")
else:
    with open(output_file, "a") as f:
        f.write("has_changes=false\n")
    print("No new listings to notify.")
