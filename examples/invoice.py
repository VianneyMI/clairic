"""Extract an invoice with Clairic, then hand plain values to the rest of the program.

Run with `uv run python examples/invoice.py` after setting CLOUDFLARE_ACCOUNT_ID and
CLOUDFLARE_API_TOKEN (a local .env file works).
"""

import datetime as dt
from typing import Annotated

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from clairic import (
    Clairic,
    DateAnswer,
    Estimate,
    EstimateAnswer,
    Number,
    NumberAnswer,
    TextAnswer,
    TextListAnswer,
)

INVOICE = (
    "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. 4 pallets at $250.00 "
    "each, shipping $80.00. Contact: Dana Ruiz, Priya Shah."
)


class InvoiceExtraction(BaseModel):
    """What to extract, and how: each field is a Clairic answer."""

    invoice_number: TextAnswer
    due_date: DateAnswer = Field(description="Issue date plus the net payment days")
    total: Annotated[NumberAnswer[float], Number(decimals=2, unit="USD")] = Field(
        description="Amount due including shipping"
    )
    contacts: TextListAnswer
    po_number: TextAnswer = Field(description="Purchase order number")
    days_to_pay: Annotated[EstimateAnswer[int], Estimate(min=0, max=120, step=1)] = Field(
        description="Days after issue until this invoice is paid"
    )


class Invoice(BaseModel):
    """The plain domain object the rest of the program works with."""

    invoice_number: str
    due_date: dt.date
    total: float
    contacts: list[str]
    po_number: str | None
    days_to_pay: int


def main() -> None:
    load_dotenv()
    with Clairic() as clairic:
        result = clairic.extract(INVOICE, InvoiceExtraction, reference_date=dt.date(2026, 9, 2))

    data = result.data
    number, po, estimate = data.invoice_number, data.po_number, data.days_to_pay
    print(f"Invoice number: {number.value} (confidence {number.confidence:.4f})")
    print(f"Due date:       {data.due_date.value}")
    print(f"Total:          {data.total.value} USD")
    print(f"PO number:      {po.value} (p_null {po.p_null:.4f}, best guess {po.guess!r})")
    print(f"Days to pay:    {estimate.value} (80% interval {estimate.p10} to {estimate.p90})")
    print(f"Input tokens:   {result.usage.input_tokens} over {result.usage.passes} passes")
    print()
    print(result.values_as(Invoice))


if __name__ == "__main__":
    main()
