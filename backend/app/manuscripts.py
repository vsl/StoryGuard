import asyncio
import hashlib
import logging
import os
import uuid
from pathlib import PurePath
from typing import BinaryIO
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.manuscript_version import ManuscriptVersion
from app.db.models.project import Project
from app.ai.extraction_models import ExtractionModel, default_extraction_model

logger = logging.getLogger(__name__)

MIME_TYPES = {
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
}


def object_key(project_id: uuid.UUID, version_id: uuid.UUID, suffix: str) -> str:
    return f"projects/{project_id}/manuscripts/{version_id}/original{suffix}"


def inspect_upload(
    filename: str, mime_type: str, stream: BinaryIO
) -> tuple[str, int, str]:
    safe_name = PurePath(filename.replace("\\", "/")).name
    suffix = PurePath(safe_name).suffix.lower()
    if not safe_name or mime_type not in MIME_TYPES.get(suffix, set()):
        raise ValueError("Unsupported manuscript file type")

    size = 0
    digest = hashlib.sha256()
    limit = int(os.environ.get("MANUSCRIPT_MAX_BYTES", 50 * 1024 * 1024))
    try:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("Manuscript exceeds the upload size limit")
            digest.update(chunk)
    finally:
        stream.seek(0)
    if size == 0:
        raise ValueError("Manuscript is empty")
    return safe_name, size, digest.hexdigest()


def minio_client() -> Minio:
    url = urlsplit(os.environ["MINIO_URL"])
    if url.scheme not in {"http", "https"} or not url.netloc or url.path not in {"", "/"}:
        raise ValueError("MINIO_URL must be an HTTP(S) origin")
    return Minio(
        url.netloc,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=url.scheme == "https",
    )


def _store(stream: BinaryIO, key: str, size: int, mime_type: str) -> None:
    client = minio_client()
    bucket = os.environ["MINIO_BUCKET"]
    if not client.bucket_exists(bucket):
        try:
            client.make_bucket(bucket)
        except S3Error as exc:
            if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise
    client.put_object(bucket, key, stream, size, content_type=mime_type)


def _remove(key: str) -> None:
    minio_client().remove_object(os.environ["MINIO_BUCKET"], key)


async def create_manuscript_version(
    session: AsyncSession,
    project_id: uuid.UUID,
    filename: str,
    mime_type: str,
    stream: BinaryIO,
    extraction_model: ExtractionModel | None = None,
) -> ManuscriptVersion:
    selected_model = (
        ExtractionModel(extraction_model)
        if extraction_model is not None
        else default_extraction_model()
    )
    safe_name, size, content_hash = inspect_upload(filename, mime_type, stream)
    version_id = uuid.uuid4()
    key = object_key(project_id, version_id, PurePath(safe_name).suffix.lower())
    stored = False
    try:
        project = await session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if project is None:
            raise LookupError("Project not found")
        version_number = 1 + (
            await session.scalar(
                select(func.coalesce(func.max(ManuscriptVersion.version_number), 0)).where(
                    ManuscriptVersion.project_id == project_id
                )
            )
        )
        await asyncio.to_thread(_store, stream, key, size, mime_type)
        stored = True
        version = ManuscriptVersion(
            id=version_id,
            project_id=project_id,
            version_number=version_number,
            object_key=key,
            original_filename=safe_name,
            mime_type=mime_type,
            file_size=size,
            content_hash=content_hash,
            extraction_model=selected_model.value,
        )
        session.add(version)
        await session.commit()
        await session.refresh(version)
        return version
    except Exception:
        await session.rollback()
        if stored:
            try:
                await asyncio.to_thread(_remove, key)
            except Exception:
                # ponytail: best-effort compensation; add an orphan sweeper if leaks occur.
                logger.exception("Failed to remove orphaned MinIO object %s", key)
        raise
