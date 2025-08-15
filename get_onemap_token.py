import os
import json
import sys
import getpass
import requests
from pathlib import Path

AUTH_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ENV_PATH = Path(__file__).parent / ".env"

def main():
    print("OneMap token fetcher (writes ONEMAP_TOKEN to .env)")

    # Prefer non-interactive credentials from env or .env
    email = os.getenv("ONEMAP_LOGIN_EMAIL")
    password = os.getenv("ONEMAP_LOGIN_PW")

    if (not email or not password) and ENV_PATH.exists():
        # Try to read from local .env if not already in process env
        env_vals = {}
        for line in ENV_PATH.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vals[k.strip()] = v.strip()
        email = email or env_vals.get("ONEMAP_LOGIN_EMAIL")
        password = password or env_vals.get("ONEMAP_LOGIN_PW")

    # Final fallback to prompt if still missing
    if not email:
        email = input("Email: ").strip()
    if not password:
        password = getpass.getpass("Password: ")

    try:
        resp = requests.post(AUTH_URL, json={"email": email, "password": password}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        sys.exit(1)

    data = resp.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    if not token:
        print("No token found in response:")
        print(json.dumps(data, indent=2))
        sys.exit(1)

    # Write/update .env
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    existing["ONEMAP_TOKEN"] = token
    ENV_PATH.write_text("\n".join([f"{k}={v}" for k, v in existing.items()]) + "\n")

    print(f"Wrote ONEMAP_TOKEN to {ENV_PATH}")

if __name__ == "__main__":
    main()
