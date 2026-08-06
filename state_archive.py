from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

from cryptography.fernet import Fernet


def encryption() -> Fernet:
    raw_key = os.environ.get("STATE_ENCRYPTION_KEY", "").strip().encode()
    if not raw_key:
        raise RuntimeError("STATE_ENCRYPTION_KEY is not configured")
    return Fernet(raw_key)


def pack(output_path: Path) -> None:
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        database_path = Path("shop.sqlite3")
        if database_path.is_file():
            archive.add(database_path, arcname="shop.sqlite3")
        log_directory = Path("logs")
        if log_directory.is_dir():
            archive.add(log_directory, arcname="logs")
    output_path.write_bytes(encryption().encrypt(archive_buffer.getvalue()))


def unpack(input_path: Path) -> None:
    decrypted = encryption().decrypt(input_path.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(decrypted), mode="r:gz") as archive:
        for member in archive.getmembers():
            member_name = Path(member.name)
            if member_name.is_absolute() or ".." in member_name.parts:
                raise RuntimeError("Unsafe state archive path")
            if member.name == "shop.sqlite3" and member.isfile():
                target = Path("shop.sqlite3")
            elif member.name.startswith("logs/") and member.isfile():
                target = Path(member.name)
            elif member.name == "logs" and member.isdir():
                Path("logs").mkdir(exist_ok=True)
                continue
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            target.write_bytes(extracted.read())


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"pack", "unpack"}:
        raise SystemExit("Usage: state_archive.py <pack|unpack> <path>")
    operation, raw_path = sys.argv[1], Path(sys.argv[2])
    if operation == "pack":
        pack(raw_path)
    elif raw_path.is_file():
        unpack(raw_path)


if __name__ == "__main__":
    main()
