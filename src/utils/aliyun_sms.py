from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests


logger = logging.getLogger(__name__)


@dataclass
class SmsSendResult:
    success: bool
    message: str


def _percent_encode(value: Any) -> str:
    return quote(str(value), safe="~")


def _sign_rpc_params(params: dict[str, Any], access_key_secret: str) -> str:
    canonicalized = "&".join(
        f"{_percent_encode(key)}={_percent_encode(params[key])}"
        for key in sorted(params)
    )
    string_to_sign = f"POST&%2F&{_percent_encode(canonicalized)}"
    key = f"{access_key_secret}&".encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_sms_verify_code(phone: str, code: str) -> SmsSendResult:
    access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    sign_name = os.getenv("ALIYUN_SMS_SIGN_NAME", "速通互联验证码")
    template_code = os.getenv("ALIYUN_SMS_TEMPLATE_CODE", "100001")

    if not access_key_id or not access_key_secret:
        return SmsSendResult(success=False, message="短信服务未配置")

    endpoint = "https://dypnsapi.aliyuncs.com/"
    params: dict[str, Any] = {
        "Action": "SendSmsVerifyCode",
        "Version": "2017-05-25",
        "Format": "JSON",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "PhoneNumber": phone,
        "SignName": sign_name,
        "TemplateCode": template_code,
        "TemplateParam": json.dumps({"code": code, "min": "5"}, ensure_ascii=False, separators=(",", ":")),
    }
    params["Signature"] = _sign_rpc_params(params, access_key_secret)

    try:
        response = requests.post(endpoint, data=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("[阿里云短信] 发送异常: %s", exc)
        return SmsSendResult(success=False, message="短信发送失败")

    response_code = data.get("Code") or data.get("code")
    response_message = data.get("Message") or data.get("message") or "发送失败"
    is_success = response_code == "OK" or data.get("Success") is True or data.get("success") is True

    logger.info(
        "[阿里云短信] 发送响应: phone=%s, response_code=%s",
        f"{phone[:3]}****{phone[-4:]}",
        response_code,
    )

    if is_success:
        return SmsSendResult(success=True, message=response_message or "发送成功")
    return SmsSendResult(success=False, message=response_message)
