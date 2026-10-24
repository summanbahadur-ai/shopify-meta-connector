"""Generate a product-specific WhatChimp button callback URL."""
import argparse
from pathlib import Path
import sys
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.schemas.button_webhook import ButtonClickPayload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--action", default="view_details", choices=["view_details"])
    parser.add_argument("--base-url", default="https://shopify-meta-connector.techsupport-e35.workers.dev")
    args = parser.parse_args()
    parts = urlsplit(args.base_url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        parser.error("Base URL must be an HTTPS origin")
    try:
        payload = ButtonClickPayload(product_id=args.product_id, action=args.action)
    except ValueError:
        parser.exit(1, "Cannot generate URL: check product ID and action.\n")
    print(args.base_url.rstrip("/") + "/api/whatsapp/button-click?" + urlencode(payload.model_dump()))


if __name__ == "__main__":
    main()
