"""Check a built dashboard page before it is published: its inline JavaScript parses and its data block is there.
    python tests/check_page.py site/index.html [max_hours_old]
With max_hours_old, also fail when the newest reading in the page is older than that (ingestion stopped)."""
import datetime as dt
import pathlib
import re
import subprocess
import sys
import tempfile

html = pathlib.Path(sys.argv[1]).read_text()
scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if s.strip()]
assert scripts, "no inline script in the page"
for s in scripts:
    with tempfile.NamedTemporaryFile("w", suffix=".js") as f:
        f.write(s); f.flush()
        subprocess.run(["node", "--check", f.name], check=True)
m = re.search(r'"last_snapshot":\s*(?:"([^"]+)"|null)', html)
assert m, "no last_snapshot in the page data"
if len(sys.argv) > 2:
    assert m.group(1), "the page has no data at all"
    age = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.datetime.fromisoformat(m.group(1))).total_seconds() / 3600
    assert age < float(sys.argv[2]), f"newest reading is {age:.0f} h old: ingestion stopped?"
print(f"page ok: {len(scripts)} script(s) parse, last_snapshot={m.group(1)}")
