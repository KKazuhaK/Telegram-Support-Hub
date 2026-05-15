import re


def normalize_phone(value: str | None) -> str:
    phone = str(value or "").strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not re.fullmatch(r"\+?\d{6,16}", phone):
        return ""
    return phone if phone.startswith("+") else f"+{phone}"


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "同意", "已授权", "授权"}


def split_line(line: str) -> list[str]:
    delimiter = "\t" if "\t" in line else ","
    return [part.strip().strip('"') for part in line.split(delimiter)]


def parse_customer_text(text: str, source: str | None, assume_consent: bool) -> tuple[list[dict], list[dict]]:
    rows = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not rows:
        return [], []

    first = [cell.lower() for cell in split_line(rows[0])]
    header_names = {"phone", "mobile", "手机号", "电话", "name", "姓名", "tags", "标签", "consent", "授权"}
    has_header = any(cell in header_names for cell in first)
    header = first if has_header else []
    body = rows[1:] if has_header else rows

    def idx(names: set[str], fallback: int) -> int:
        for name in names:
            if name in header:
                return header.index(name)
        return fallback

    phone_index = idx({"phone", "mobile", "手机号", "电话"}, 0)
    name_index = idx({"name", "姓名", "客户名"}, 1)
    tags_index = idx({"tags", "标签"}, 2)
    consent_index = idx({"consent", "authorized", "opt_in", "授权", "同意"}, -1)

    imported: list[dict] = []
    rejected: list[dict] = []
    for line in body:
        cells = split_line(line)
        phone = normalize_phone(cells[phone_index] if phone_index < len(cells) else "")
        if not phone:
            rejected.append({"line": line, "reason": "invalid_phone"})
            continue
        imported.append(
            {
                "phone": phone,
                "name": cells[name_index] if name_index < len(cells) else None,
                "tags": [tag.strip() for tag in (cells[tags_index] if tags_index < len(cells) else "").split("|") if tag.strip()],
                "source": source or "manual",
                "consent": parse_bool(cells[consent_index]) if 0 <= consent_index < len(cells) else assume_consent,
            }
        )
    return imported, rejected
