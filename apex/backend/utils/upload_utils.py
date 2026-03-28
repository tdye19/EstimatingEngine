import os
import shutil
from pathlib import Path

UPLOAD_TEMP_DIR = Path(os.getenv("UPLOAD_TEMP_DIR", "/tmp/apex_uploads"))


def get_chunk_path(upload_id: str, chunk_index: int) -> Path:
    """Returns temp file path for a single chunk."""
    dir = UPLOAD_TEMP_DIR / upload_id
    dir.mkdir(parents=True, exist_ok=True)
    return dir / f"chunk_{chunk_index:04d}.bin"


def assemble_chunks(upload_id: str, total_chunks: int, output_path: Path) -> bool:
    """Assembles ordered chunks into output_path. Returns True on success."""
    with open(output_path, "wb") as outfile:
        for i in range(total_chunks):
            chunk_file = get_chunk_path(upload_id, i)
            if not chunk_file.exists():
                return False
            outfile.write(chunk_file.read_bytes())
    return True


def cleanup_chunks(upload_id: str) -> None:
    """Removes temp chunk directory after successful assembly."""
    dir = UPLOAD_TEMP_DIR / upload_id
    if dir.exists():
        shutil.rmtree(dir)
