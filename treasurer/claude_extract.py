"""ClaudeExtractor: reads a receipt photo with the Claude API.

Same `extract()` method as StubExtractor, so the app does not change.
The prompt says TRANSCRIBE, never reconcile: vision models sometimes alter
line items or invent a tax line so a receipt adds up, and our math check can
only catch an error the model leaves in place.

Needs ANTHROPIC_API_KEY in a local .env file (never commit it).
"""
from __future__ import annotations

import base64
import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .extract import ExtractionError
from .models import LineItem, Receipt

MODEL = "claude-sonnet-5-5"  # override with TALLYABLE_MODEL in .env
EFFORT = "medium"  # transcription, not deep reasoning; try "low" and compare scores
PRICE_PER_MTOK = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00),
                  "claude-haiku-5-5": (0.10, 0.50)}
# Rough upper bound per receipt: image + prompt in, transcription + thinking out.
EST_TOKENS_PER_RECEIPT = (2500, 1500)


def estimate(model: str, receipts: int) -> float:
    """Upper-bound dollars for reading `receipts` photos with `model`."""
    inp, out = PRICE_PER_MTOK.get(model, PRICE_PER_MTOK["claude-opus-5-5"])
    return receipts * (EST_TOKENS_PER_RECEIPT[0] * inp + EST_TOKENS_PER_RECEIPT[1] * out) / 1e6

SYSTEM = """You transcribe proof of purchase for a student club treasurer: a paper receipt, a
screenshot of an online or app order, a food-court or restaurant ticket, or a PDF invoice.

Copy what is printed or handwritten. Do not calculate, correct, or reconcile anything.
- If the items, tax and tip do not add up to the total, copy them anyway. A separate
  program checks the math, and it can only catch mistakes you leave in place.
- Never invent a line (no "tax", "fee" or "adjustment" line that is not on the paper).
- If part of the receipt is folded, torn, blurry or cut off, set `unreadable_note`
  to say where, and leave out what you cannot see. Do not guess.
- `price` is the unit price before tax. `unit` is the quantity. If only a line total is
  printed, put it in price with unit 1.
- `total` is the total as printed, even if it is handwritten or looks wrong. On an order
  screenshot it is the order total actually charged.
- Fees (delivery, service, bag, small-order) are their own lines, category Other.
- A discount, coupon, promo or member saving is its own line with a NEGATIVE price,
  category Other. Copy its wording as the item name.
- Dates as YYYY-MM-DD. Money as plain decimals with two places, no currency symbol.
- Receipts may be partly in Korean. Copy item names as printed; add an English gloss
  in parentheses only if you are sure of it.
- Category is the one field you judge rather than copy. Decide by what the item IS, not by
  words in its name:
  - Food: anything eaten, including sauces, dips, condiments and snacks.
  - Drink: anything drunk, plus ice bought to chill drinks.
  - Other: things that are not consumed: plates, cups, napkins, utensils, decorations, supplies.
  A container word in a name can mislead: judge the contents. "Salsa jar" is Food; an empty
  "mason jar" is Other. If you can't tell, pick the most likely and say so in `unreadable_note`.
- Set `returned` only if the receipt marks the item returned or refunded.
"""


class ExtractedItem(BaseModel):
    item: str
    category: Literal["Food", "Drink", "Other"]
    unit: int
    price: str = Field(description="Unit price before tax, e.g. '4.99'; negative for a discount, e.g. '-4.00'")
    returned: bool = False


class ExtractedReceipt(BaseModel):
    place: str
    date: str = Field(description="YYYY-MM-DD")
    items: list[ExtractedItem]
    tax: str = "0.00"
    tip: str = "0.00"
    total: str = Field(description="Total exactly as printed or handwritten")
    unreadable_note: str | None = None


def _money(text: str, field: str, filename: str) -> Decimal:
    t = str(text).replace("$", "").replace(",", "").replace("\u2212", "-").strip()
    if t.startswith("(") and t.endswith(")"):  # accounting style: (4.00) is -4.00
        t = "-" + t[1:-1]
    try:
        return Decimal(t or "0")
    except InvalidOperation as e:
        raise ExtractionError(f"Claude returned a bad {field} for {filename}: {text!r}") from e


class ClaudeExtractor:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL, effort: str = EFFORT):
        self._client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.usage: list[dict] = []  # per-receipt token counts

    def extract(self, image: bytes, filename: str, event_id: str, receipt_id: str) -> Receipt:
        ext = filename.lower().rsplit(".", 1)[-1]
        b64 = base64.standard_b64encode(image).decode()
        if ext == "pdf":  # Claude reads PDFs directly
            source = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
        else:
            media = {"png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
            source = {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}}
        try:
            resp = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                output_format=ExtractedReceipt,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # if a safety check declines, the API retries on another model
                messages=[{"role": "user", "content": [
                    source,
                    {"type": "text", "text": "Transcribe this receipt."},
                ]}],
            )
        except anthropic.AuthenticationError as e:
            raise ExtractionError("Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.") from e
        except anthropic.PermissionDeniedError as e:
            raise ExtractionError("The API key has no access. Check your credits and key permissions.") from e
        except anthropic.RateLimitError as e:
            raise ExtractionError(f"Rate limited while reading {filename}. Wait a minute and retry.") from e
        except anthropic.BadRequestError as e:
            raise ExtractionError(f"Claude could not read {filename}: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"Claude could not read {filename}: HTTP {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError(f"No connection while reading {filename}") from e

        self.usage.append({"receipt_id": receipt_id, "model": resp.model,
                           "input": resp.usage.input_tokens, "output": resp.usage.output_tokens})
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise ExtractionError(f"Claude did not return a receipt for {filename} ({resp.stop_reason})")

        x = resp.parsed_output
        try:
            d = date.fromisoformat(x.date)
            items = [LineItem(category=i.category, item=i.item, unit=max(i.unit, 1),
                              price=_money(i.price, "price", filename), returned=i.returned) for i in x.items]
            return Receipt(
                receipt_id=receipt_id, event_id=event_id, place=x.place, date=d,
                payer=None,  # payer comes from the upload tag, never from the AI
                items=items, tax=_money(x.tax, "tax", filename), tip=_money(x.tip, "tip", filename),
                total=_money(x.total, "total", filename), image_file=filename,
                image_hash=hashlib.sha256(image).hexdigest(), review_note=x.unreadable_note,
            )
        except ValueError as e:  # bad date, no items, negative money
            raise ExtractionError(f"Claude's reading of {filename} did not fit the receipt format: {e}") from e

    def cost(self) -> float:
        """Estimated dollars spent so far, at list prices."""
        total = 0.0
        for u in self.usage:
            inp, out = PRICE_PER_MTOK.get(u["model"], PRICE_PER_MTOK["claude-opus-5-5"])
            total += u["input"] * inp / 1e6 + u["output"] * out / 1e6
        return total
