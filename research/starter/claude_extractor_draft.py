"""DRAFT ClaudeExtractor for week 2. Untested: no API key existed when it was written.

It implements the same `Extractor` protocol as treasurer/extract.py's StubExtractor,
so the app does not change. The prompt is the important part: it tells the model to
TRANSCRIBE, never to reconcile. A 2026 benchmark (ReceiptBench, arXiv 2605.22413)
found vision models alter line items or invent a tax line so a receipt adds up.
Our math check can only catch an error the model leaves in place.

Setup:  pip install anthropic   and put ANTHROPIC_API_KEY in a local .env (never commit it).
"""
from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from treasurer.extract import ExtractionError
from treasurer.models import LineItem, Receipt

MODEL = "claude-opus-5-5"  # measure claude-haiku-5-5 on the fake event too, and pick with data

SYSTEM = """You transcribe store receipts for a student club treasurer.

Copy what is printed or handwritten. Do not calculate, correct, or reconcile anything.
- If the items, tax and tip do not add up to the total, copy them anyway. A separate
  program checks the math, and it can only catch mistakes you leave in place.
- Never invent a line (no "tax", "fee" or "adjustment" line that is not on the paper).
- If part of the receipt is folded, torn, blurry or cut off, set `unreadable_note`
  to say where, and leave out what you cannot see. Do not guess.
- `price` is the unit price before tax. `unit` is the quantity. If only a line total is
  printed, put it in price with unit 1.
- `total` is the total as printed, even if it is handwritten or looks wrong.
- Dates as YYYY-MM-DD. Money as plain decimals with two places, no currency symbol.
- Receipts may be partly in Korean. Copy item names as printed; add an English gloss
  in parentheses only if you are sure of it.
- Category: Food, Drink, or Other (supplies, decorations, anything not eaten or drunk).
"""


class ExtractedItem(BaseModel):
    item: str
    category: Literal["Food", "Drink", "Other"]
    unit: int = Field(gt=0)
    price: str = Field(description="Unit price before tax, e.g. '4.99'")
    returned: bool = Field(default=False, description="True only if the receipt marks it returned or refunded")


class ExtractedReceipt(BaseModel):
    place: str
    date: str = Field(description="YYYY-MM-DD")
    items: list[ExtractedItem]
    tax: str = "0.00"
    tip: str = "0.00"
    total: str = Field(description="Total exactly as printed or handwritten")
    unreadable_note: str | None = Field(default=None, description="Where the receipt could not be read, if anywhere")


class ClaudeExtractor:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self._client = client or anthropic.Anthropic()
        self._model = model
        self.usage: list[dict] = []  # per-receipt token counts, for the cost line in the README

    def extract(self, image: bytes, filename: str, event_id: str, receipt_id: str) -> Receipt:
        media = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        try:
            resp = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=SYSTEM,
                output_format=ExtractedReceipt,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media,
                                                  "data": base64.standard_b64encode(image).decode()}},
                    {"type": "text", "text": "Transcribe this receipt."},
                ]}],
            )
        except anthropic.APIStatusError as e:  # 4xx/5xx after the SDK's own retries
            raise ExtractionError(f"Claude could not read {filename}: {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError(f"No connection while reading {filename}") from e

        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise ExtractionError(f"Claude did not return a receipt for {filename}")
        self.usage.append({"receipt_id": receipt_id, "input": resp.usage.input_tokens,
                           "output": resp.usage.output_tokens})

        x = resp.parsed_output
        return Receipt(
            receipt_id=receipt_id, event_id=event_id, place=x.place, date=date.fromisoformat(x.date),
            payer=None,  # payer comes from the upload tag, never from the AI
            items=[LineItem(category=i.category, item=i.item, unit=i.unit, price=Decimal(i.price),
                            returned=i.returned) for i in x.items],
            tax=Decimal(x.tax), tip=Decimal(x.tip), total=Decimal(x.total),
            image_file=filename, review_note=x.unreadable_note,
        )
