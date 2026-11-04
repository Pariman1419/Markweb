import hashlib
from pathlib import Path
import zipfile

MAX_ZIP_MEMBERS = 50
MAX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024  # 100MB


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract zip archive safely with protections against Zip Slip and Zip Bombs."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_ZIP_MEMBERS:
            raise ValueError(
                f"Zip bomb detected: member count {len(infolist)} exceeds limit ({MAX_ZIP_MEMBERS})"
            )

        total_size = sum(info.file_size for info in infolist)
        if total_size > MAX_UNCOMPRESSED_SIZE_BYTES:
            raise ValueError(
                f"Zip bomb detected: uncompressed size {total_size} bytes exceeds limit ({MAX_UNCOMPRESSED_SIZE_BYTES} bytes)"
            )

        target_dir_resolved = target_dir.resolve()
        for info in infolist:
            name = info.filename
            # Zip slip validation
            if name.startswith(("/", "\\")):
                raise ValueError(f"Zip slip detected: leading slash in '{name}'")
            if len(name) > 1 and name[1] == ":":
                raise ValueError(f"Zip slip detected: drive letter in '{name}'")

            p = Path(name)
            if any(part == ".." for part in p.parts):
                raise ValueError(f"Zip slip detected: parent directory traversal in '{name}'")

            dest = (target_dir / name).resolve()
            if not dest.is_relative_to(target_dir_resolved):
                raise ValueError(f"Zip slip detected: destination outside target directory for '{name}'")

        zf.extractall(target_dir)


def fingerprint_folder(folder: Path, extract_dir: Path) -> list[tuple[Path, str]]:
    """Scan folder recursively for PDFs and ZIPs.

    Extracts ZIPs into extract_dir/<zip_sha256>/, collects all PDFs, drops duplicates
    by sha256, and returns a sorted list of (pdf_path, sha256).
    """
    if not folder.is_dir():
        return []

    # Collect *.pdf and *.zip recursively in folder
    all_files = sorted([p for p in folder.rglob("*") if p.is_file()], key=lambda p: str(p))

    candidate_pdfs: list[Path] = []

    for file_path in all_files:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            candidate_pdfs.append(file_path)
        elif suffix == ".zip":
            zip_bytes = file_path.read_bytes()
            zip_sha = hashlib.sha256(zip_bytes).hexdigest()
            dest_dir = extract_dir / zip_sha
            if not dest_dir.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
                _safe_extract_zip(file_path, dest_dir)

            # Discover all PDFs extracted from this zip
            extracted_pdfs = sorted(
                [p for p in dest_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"],
                key=lambda p: str(p),
            )
            candidate_pdfs.extend(extracted_pdfs)

    # Deduplicate candidate PDFs by sha256
    results: list[tuple[Path, str]] = []
    seen_shas: set[str] = set()

    for pdf_path in candidate_pdfs:
        sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if sha not in seen_shas:
            seen_shas.add(sha)
            results.append((pdf_path, sha))

    # Return sorted by Path
    results.sort(key=lambda item: str(item[0]))
    return results
