"""Telegram Desktop `tdata` folder → Telethon SQLite session conversion.

Used by the account-import-zip flow when the operator uploads a zip
produced by Telegram Desktop's session export (one folder per phone,
each containing `tdata/`). Telethon — the library we drive the rest of
the app with — uses a different on-disk format, so we convert at
import time and write the resulting `.session` file under the normal
session_dir layout.

`opentele` is lazy-imported because it pulls in pyrogram + tgcrypto
(C extension); we don't want a missing wheel to break the whole app
or block local dev. Callers that hit a tdata zip without opentele
installed get a friendly error pointing to the dependency.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _have_opentele() -> bool:
    try:
        import opentele  # noqa: F401
        return True
    except Exception:
        return False


def is_tdata_layout(zf: zipfile.ZipFile) -> dict[str, str]:
    """Detect tdata-style entries in a zip and return a dict mapping the
    top-level folder (= phone) to the zip-path prefix of its tdata
    subtree. Empty dict when the zip isn't a tdata export.

    Recognition signal: any entry matching `<stem>/tdata/key_datas`.
    """
    found: dict[str, str] = {}
    for name in zf.namelist():
        norm = name.replace("\\", "/")
        # 'PHONE/tdata/key_datas' is the canonical telegram-desktop
        # marker — file exists in every exported session.
        if norm.endswith("/tdata/key_datas"):
            stem = norm.split("/tdata/", 1)[0]
            if stem and "/" not in stem:
                found[stem] = stem
    return found


def convert_tdata_zip_entry(zf: zipfile.ZipFile, stem: str) -> bytes:
    """Extract `<stem>/tdata/*` to a tempdir, run opentele to convert
    to a Telethon SQLite session, return the session file bytes."""
    if not _have_opentele():
        raise RuntimeError(
            "tdata 格式需要 `opentele` 依赖，请在服务器上 pip install opentele "
            "并重启镜像（Dockerfile 已声明此依赖）",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        prefix = f"{stem}/"
        extracted = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            norm = info.filename.replace("\\", "/")
            if not norm.startswith(prefix):
                continue
            rel = norm[len(prefix):]
            # Only need files under tdata/ for the conversion — 2Fa.txt
            # is ignored in option A (see docs/plan).
            if not rel.startswith("tdata/"):
                continue
            target = tmp_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            extracted += 1
        if extracted == 0:
            raise RuntimeError(f"未找到 {stem}/tdata/* 文件，zip 结构异常")
        _add_legacy_filename_aliases(tmp_root / "tdata")
        return _run_conversion(tmp_root)


def _add_legacy_filename_aliases(tdata_dir: Path) -> None:
    """Newer Telegram Desktop writes session files with a trailing 's'
    (`key_datas`, `<id>s`). opentele 1.15.x still looks them up under
    the singular form (`key_data`, `<id>`) and raises
    `TFileNotFound: Could not open key_data` on the new layout. Drop a
    sibling copy under the singular name to satisfy both lookups.

    Skipped when a directory of the same name already exists at that
    path — that's a tdata account-data folder, not a candidate for the
    file alias.
    """
    if not tdata_dir.is_dir():
        return
    for child in list(tdata_dir.iterdir()):
        if not child.is_file():
            continue
        if not child.name.endswith("s"):
            continue
        legacy = child.with_name(child.name[:-1])
        if legacy.exists():
            continue
        try:
            legacy.write_bytes(child.read_bytes())
        except OSError as exc:
            logger.warning("failed to alias %s -> %s: %s", child.name, legacy.name, exc)


def _run_conversion(tdata_parent: Path) -> bytes:
    """tdata_parent contains a `tdata/` subfolder; convert to .session."""
    # Late import; lets the module load even without opentele installed
    # so tests can mock convert_tdata_zip_entry without the dependency.
    from opentele.td import TDesktop
    from opentele.api import UseCurrentSession, API

    # opentele wants the path TO the tdata folder, not its parent —
    # despite the constructor name. Passing the parent makes it look
    # for key_data / D877.../maps directly in the parent, which fails
    # immediately with TFileNotFound.
    tdata_dir = tdata_parent / "tdata"
    out_path = tdata_parent / "out.session"

    async def _do() -> bytes:
        tdesk = TDesktop(str(tdata_dir))
        if not tdesk.isLoaded():
            raise RuntimeError("tdata 解析失败：不是有效的 Telegram Desktop 会话数据")
        client = await tdesk.ToTelethon(
            session=str(out_path),
            flag=UseCurrentSession,  # reuse existing auth, no new login
            api=API.TelegramDesktop,
        )
        try:
            await client.disconnect()
        except Exception:
            pass
        return out_path.read_bytes()

    return asyncio.run(_do())
