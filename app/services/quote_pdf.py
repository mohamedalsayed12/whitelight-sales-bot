"""A one-page quote PDF.

The file is plain text in a PDF wrapper so a salesman can send it on WhatsApp.
No PDF library: a quote is one page, and the project stays on the current stack.
"""

from decimal import Decimal

from app.services.quotes import QuoteView

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT = 50
TOP = 800
LINE_HEIGHT = 16


def render_quote_pdf(quote: QuoteView) -> bytes:
    stream = _stream(_lines(quote))
    return _pdf(stream)


def _lines(quote: QuoteView) -> list[str]:
    rows = [
        "White Light Trading",
        f"Quote {quote.id}",
        f"Client: {quote.client_name}",
        f"Salesman: {quote.salesman_name}",
        f"Valid until: {quote.valid_until.isoformat()}",
        "",
    ]
    for line in quote.lines:
        amount = (line.quantity * line.unit_price).quantize(Decimal("0.001"))
        rows.append(f"{line.sku}  {line.name}")
        rows.append(
            f"  {line.quantity} x {line.unit_price} BHD = {amount:.3f} BHD"
        )
    rows.append("")
    rows.append(f"Total: {quote.total:.3f} BHD")
    return rows


def _stream(rows: list[str]) -> bytes:
    parts = ["BT", "/F1 12 Tf", f"{LEFT} {TOP} Td"]
    for index, row in enumerate(rows):
        if index:
            parts.append(f"0 -{LINE_HEIGHT} Td")
        parts.append(f"({_escape(row)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def _escape(text: str) -> str:
    # Helvetica uses Latin-1. Anything else becomes a question mark.
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(stream: bytes) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{PAGE_WIDTH} {PAGE_HEIGHT}".encode("ascii")
            + b"] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)
