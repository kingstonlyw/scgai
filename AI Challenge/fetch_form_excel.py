import argparse
import base64
import os
from pathlib import Path
from typing import Optional

# THIS FILE IS NOT WORKING YET, NEED MORE ACCESS TO USE

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _b64u_no_pad(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _get_token() -> str:
    tenant = os.getenv("MS_TENANT_ID")
    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    if not all([tenant, client_id, client_secret]):
        raise SystemExit(
            "Missing MS_TENANT_ID, MS_CLIENT_ID, or MS_CLIENT_SECRET. Set in .env or environment."
        )

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = requests.post(token_url, data=data, timeout=30)
    resp.raise_for_status()
    tok = resp.json().get("access_token")
    if not tok:
        raise SystemExit("Failed to obtain access token")
    return tok


def _download(url: str, token: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)


def fetch_via_share_link(share_link: str, token: str, dest: Path) -> None:
    encoded = _b64u_no_pad(share_link)
    # Direct content download
    url = f"{GRAPH_BASE}/shares/u!{encoded}/driveItem/content"
    _download(url, token, dest)


def fetch_from_onedrive_user(user: str, file_path: str, token: str, dest: Path) -> None:
    # file_path is a path under the user's OneDrive root, e.g. "Apps/Microsoft Forms/My Form/Responses.xlsx"
    url = f"{GRAPH_BASE}/users/{user}/drive/root:/{file_path}:/content"
    _download(url, token, dest)


def fetch_from_sharepoint_site(site_host: str, site_path: str, file_path: str, token: str, dest: Path) -> None:
    # Resolve site id
    site_url = f"{GRAPH_BASE}/sites/{site_host}:{site_path}"
    site_resp = requests.get(site_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    site_resp.raise_for_status()
    site_id = site_resp.json().get("id")
    if not site_id:
        raise SystemExit("Could not resolve SharePoint site id")
    # Default drive (Documents)
    url = f"{GRAPH_BASE}/sites/{site_id}/drive/root:/{file_path}:/content"
    _download(url, token, dest)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch the Forms response Excel via Microsoft Graph")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--share-link", help="Sharing URL to the Excel file (internal share link)")
    src.add_argument("--user", help="User principal name or id that owns the OneDrive (e.g., alice@contoso.com)")
    ap.add_argument("--file-path", help="Path under OneDrive or SharePoint drive root to the Excel file")
    ap.add_argument("--site-host", help="SharePoint host, e.g., contoso.sharepoint.com")
    ap.add_argument("--site-path", help="Site path, e.g., /sites/TeamName")
    ap.add_argument(
        "--dest",
        default=str(Path(__file__).parent / "data" / "form_data.xlsx"),
        help="Destination path to save the Excel (defaults to data/form_data.xlsx)",
    )
    args = ap.parse_args()

    token = _get_token()
    dest = Path(args.dest)

    if args.share_link:
        fetch_via_share_link(args.share_link, token, dest)
    elif args.user and args.file_path:
        fetch_from_onedrive_user(args.user, args.file_path, token, dest)
    elif args.site_host and args.site_path and args.file_path:
        fetch_from_sharepoint_site(args.site_host, args.site_path, args.file_path, token, dest)
    else:
        raise SystemExit(
            "Provide either --share-link OR --user + --file-path OR --site-host + --site-path + --file-path"
        )

    print(f"Downloaded to {dest}")


if __name__ == "__main__":
    main()
