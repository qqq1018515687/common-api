import base64
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SOFFICE_COMMAND = "/usr/bin/soffice"
OFFICE_TO_PDF_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx"}
OFFICE_TO_PDF_TYPES = {
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CONVERSION_SEMAPHORE = threading.BoundedSemaphore(1)

app = FastAPI(title="Office Converter Service")


class ConvertToPdfRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=255)
    file_content_base64: str = Field(..., min_length=1)


def _converter_token() -> str:
    return (os.getenv("OFFICE_CONVERTER_TOKEN") or "").strip()


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name.strip()).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="file_name 不合法")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="file_name 不合法")
    if not re.match(r"^[A-Za-z0-9._\-\u4e00-\u9fff ]+$", name):
        raise HTTPException(status_code=400, detail="file_name 包含不支持的字符")
    return name


def _file_suffix(file_name: str, content_type: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix in OFFICE_TO_PDF_SUFFIXES:
        return suffix
    if content_type == "application/msword":
        return ".doc"
    if content_type == "application/vnd.ms-powerpoint":
        return ".ppt"
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return ".docx"
    if content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return ".pptx"
    raise HTTPException(status_code=400, detail="当前文件类型不支持转换")


def _decode_file_content(content_base64: str) -> bytes:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="file_content_base64 解析失败") from exc
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10MB")
    return content


def _check_auth(authorization: Optional[str]) -> None:
    token = _converter_token()
    if not token:
        raise HTTPException(status_code=500, detail="转换服务未配置 OFFICE_CONVERTER_TOKEN")
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="转换服务鉴权失败")


@app.get("/health")
def health() -> dict:
    return {
        "ok": Path(SOFFICE_COMMAND).exists(),
        "soffice": SOFFICE_COMMAND,
    }


@app.post("/convert-to-pdf")
def convert_to_pdf(
    request: ConvertToPdfRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _check_auth(authorization)
    file_name = _safe_file_name(request.file_name)
    suffix = _file_suffix(file_name, request.content_type)
    file_content = _decode_file_content(request.file_content_base64)

    if not CONVERSION_SEMAPHORE.acquire(timeout=120):
        raise HTTPException(status_code=429, detail="Office 文件转换繁忙，请稍后重试")

    try:
        with tempfile.TemporaryDirectory(prefix="office-converter-") as work_dir:
            input_path = Path(work_dir) / f"source{suffix}"
            input_path.write_bytes(file_content)
            try:
                completed = subprocess.run(
                    [
                        SOFFICE_COMMAND,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        work_dir,
                        str(input_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=500, detail=f"LibreOffice 执行文件不存在: {SOFFICE_COMMAND}") from exc
            except PermissionError as exc:
                raise HTTPException(status_code=500, detail=f"LibreOffice 执行文件无执行权限: {SOFFICE_COMMAND}") from exc
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=504, detail="LibreOffice 转换超时") from exc

            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise HTTPException(status_code=500, detail=f"Office 文件转换失败: {detail or 'LibreOffice 未返回可用错误信息'}")

            pdf_path = input_path.with_suffix(".pdf")
            if not pdf_path.exists():
                raise HTTPException(status_code=500, detail="Office 文件转换失败: 未生成 PDF 文件")
            pdf_content = pdf_path.read_bytes()
    finally:
        CONVERSION_SEMAPHORE.release()

    return {
        "file_name": f"{Path(file_name).stem or 'office-document'}.pdf",
        "content_type": "application/pdf",
        "size": len(pdf_content),
        "file_content_base64": base64.b64encode(pdf_content).decode("ascii"),
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("OFFICE_CONVERTER_HOST", "0.0.0.0")
    port = int(os.getenv("OFFICE_CONVERTER_PORT", "8010"))
    uvicorn.run(app, host=host, port=port)

