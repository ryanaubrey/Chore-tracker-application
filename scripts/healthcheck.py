import os
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


port = int(os.environ.get("PORT", "8000"))
origin = os.environ.get("CHORES_PUBLIC_URL", "")
headers = {"Host": urlsplit(origin).netloc} if origin else {}
probe = Request(f"http://127.0.0.1:{port}/healthz", headers=headers)
with build_opener(ProxyHandler({})).open(probe, timeout=3) as response:
    if response.status != 200:
        raise SystemExit(1)
