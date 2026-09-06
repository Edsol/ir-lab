from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import requests

from .errors import IrLabError

# Region -> base URL
_REGION_URLS = {
    "EU": "https://openapi.tuyaeu.com",
    "US": "https://openapi.tuyaus.com",
    "CN": "https://openapi.tuyacn.com",
    "IN": "https://openapi.tuyain.com",
}


class TuyaCloudError(IrLabError):
    pass


class TuyaCloudClient:
    def __init__(self, access_id: str, access_secret: str, region: str = "EU") -> None:
        self.access_id = access_id
        self.access_secret = access_secret
        self.base_url = _REGION_URLS[region.upper()]
        self._token: str | None = None
        self._token_expires: float = 0

    # ── Auth ────────────────────────────────────────────────────────────────

    def _sign(self, method: str, path: str, body: str = "", token: str = "") -> tuple[str, str]:
        ts = str(int(time.time() * 1000))
        content_hash = hashlib.sha256(body.encode()).hexdigest()
        string_to_sign = "\n".join([method, content_hash, "", path])
        msg = self.access_id + token + ts + string_to_sign
        sign = hmac.new(self.access_secret.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()
        return sign, ts

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        path = "/v1.0/token?grant_type=1"
        sign, ts = self._sign("GET", path)
        headers = {
            "client_id": self.access_id,
            "sign": sign,
            "t": ts,
            "sign_method": "HMAC-SHA256",
        }
        resp = requests.get(self.base_url + path, headers=headers, timeout=10)
        data = resp.json()
        if not data.get("success"):
            raise TuyaCloudError(f"Tuya authentication failed: {data.get('msg', data)}")
        result = data["result"]
        self._token = result["access_token"]
        self._token_expires = time.time() + result["expire_time"] - 60
        return self._token

    def _get(self, path: str) -> Any:
        token = self._get_token()
        sign, ts = self._sign("GET", path, token=token)
        headers = {
            "client_id": self.access_id,
            "access_token": token,
            "sign": sign,
            "t": ts,
            "sign_method": "HMAC-SHA256",
        }
        resp = requests.get(self.base_url + path, headers=headers, timeout=10)
        data = resp.json()
        if not data.get("success"):
            raise TuyaCloudError(f"Tuya API error on {path}: {data.get('msg', data)}")
        return data["result"]

    # ── IR Library ──────────────────────────────────────────────────────────

    def get_categories(self) -> list[dict]:
        """List IR categories (e.g. 'Air Conditioner', 'TV', ...)."""
        return self._get("/v2.0/infrareds/0/categories")

    def get_brands(self, category_id: int) -> list[dict]:
        """List brands for a category."""
        return self._get(f"/v2.0/infrareds/0/categories/{category_id}/brands")

    def get_remotes(self, category_id: int, brand_id: int) -> list[dict]:
        """List remotes available for a brand."""
        return self._get(f"/v2.0/infrareds/0/categories/{category_id}/brands/{brand_id}/remotes")

    def get_keys(self, category_id: int, brand_id: int, remote_index: int) -> list[dict]:
        """List the keys, with IR codes, for one remote."""
        return self._get(
            f"/v2.0/infrareds/0/categories/{category_id}/brands/{brand_id}/remotes/{remote_index}/rules"
        )

    def search_brand(self, category_id: int, name: str) -> list[dict]:
        """Search brands by name (case-insensitive)."""
        brands = self.get_brands(category_id)
        name_lower = name.lower()
        return [b for b in brands if name_lower in b.get("brand_name", "").lower()]
