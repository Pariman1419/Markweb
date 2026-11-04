import re

READ_ONLY_TXN: str = "SET TRANSACTION READ ONLY"

_FORBIDDEN_WORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "DROP",
    "ALTER",
    "CREATE",
    "GRANT",
    "TRUNCATE",
    "EXECUTE",
    "CALL",
    "BEGIN",
    "DECLARE",
    "LOCK",
    "COMMIT",
)

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_WORDS) + r")\b",
    re.IGNORECASE,
)
_FOR_UPDATE_PATTERN = re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE)


def assert_select_only(sql: str) -> None:
    """Raises PermissionError unless sql is a SELECT/WITH query or SET TRANSACTION READ ONLY."""
    if sql == READ_ONLY_TXN:
        return

    # Strip block comments /* ... */
    cleaned = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Strip line comments -- ...
    cleaned = re.sub(r"--.*$", " ", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    if not cleaned:
        raise PermissionError("SQL statement is empty")

    if cleaned == READ_ONLY_TXN or cleaned.rstrip(";").strip() == READ_ONLY_TXN:
        return

    # Semicolon check: allow at most one trailing semicolon
    if cleaned.endswith(";"):
        body = cleaned[:-1].strip()
    else:
        body = cleaned

    if ";" in body:
        raise PermissionError("Multiple SQL statements with semicolon are not allowed")

    # Must start with SELECT or WITH
    if not re.match(r"^(SELECT|WITH)\b", body, flags=re.IGNORECASE):
        raise PermissionError("Only SELECT or WITH statements are allowed")

    # Must block FOR UPDATE
    if _FOR_UPDATE_PATTERN.search(body):
        raise PermissionError("FOR UPDATE is not allowed in read-only queries")

    # Must block DML/DDL keywords
    forbidden_match = _FORBIDDEN_PATTERN.search(body)
    if forbidden_match:
        raise PermissionError(f"Forbidden SQL keyword: {forbidden_match.group(0)}")
