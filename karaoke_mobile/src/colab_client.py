"""Client for interacting with Google Colab MFA Alignment Server."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class ColabClientError(RuntimeError):
    pass


class ColabMFAClient:
    """HTTP client for Colab MFA Server."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url.strip().rstrip("/")

    def set_url(self, url: str) -> None:
        self.base_url = url.strip().rstrip("/")

    def ping(self) -> Dict[str, Any]:
        """Check if Colab server is reachable and MFA is running."""
        if not self.base_url:
            raise ColabClientError("URL сервера Colab не указан")

        req = urllib.request.Request(f"{self.base_url}/", headers={"User-Agent": "KaraokeMobile/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
                raise ColabClientError(f"Сервер ответил с кодом {resp.status}")
        except urllib.error.URLError as e:
            raise ColabClientError(f"Не удалось подключиться к Colab: {e.reason}")
        except Exception as e:
            raise ColabClientError(f"Ошибка проверки сервера: {e}")

    def align(
        self,
        audio_path_or_bytes: str | bytes,
        filename: str,
        transcript: str,
        language: str = "russian",
        timeout: int = 180,
    ) -> Dict[str, Any]:
        """Send audio and lyrics to Colab server for MFA alignment.

        Returns dict containing 'success', 'words', and 'ass_content'.
        """
        if not self.base_url:
            raise ColabClientError("URL сервера Colab не указан")

        if isinstance(audio_path_or_bytes, str):
            with open(audio_path_or_bytes, "rb") as f:
                audio_bytes = f.read()
        else:
            audio_bytes = audio_path_or_bytes

        boundary = "----KaraokeMobileBoundary" + "8492048291048291"
        body = bytearray()

        # 1. transcript field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="transcript"\r\n\r\n')
        body.extend(transcript.encode("utf-8"))
        body.extend(b"\r\n")

        # 2. language field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        body.extend(language.encode("utf-8"))
        body.extend(b"\r\n")

        # 3. audio file field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="audio"; filename="{filename}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n'.encode("utf-8")
        )
        body.extend(audio_bytes)
        body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            f"{self.base_url}/align",
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "KaraokeMobile/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("success", False):
                    raise ColabClientError(data.get("message", "Выравнивание не удалось"))
                return data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise ColabClientError(f"Ошибка сервера MFA ({e.code}): {err_body[:300]}")
        except urllib.error.URLError as e:
            raise ColabClientError(f"Ошибка соединения с Colab: {e.reason}")
        except Exception as e:
            raise ColabClientError(f"Ошибка во время выравнивания: {e}")
