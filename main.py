
import os
import requests



def main():
    print("Hello from system-one-extract!")


    ACCOUNT_ID = "your-account-id"
    AUTH_TOKEN = os.environ.get("CLOUDFLARE_AUTH_TOKEN")

    response = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clairic",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={
            "model": "clairic",
            "state": "Invoice INV-2291 from Northwind Supply, issued 2026-09-02, net 30. 4 pallets at $250.00 each, shipping $80.00. Contact: Dana Ruiz, Priya Shah.",
            "fields": {
                "invoice_number": {"type": "text"},
                "due_date": {
                    "type": "date",
                    "instructions": "Issue date plus the net payment days",
                },
                "total": {
                    "type": "number",
                    "decimals": 2,
                    "unit": "USD",
                    "instructions": "Amount due including shipping",
                },
                "contacts": {"type": "list", "items": "text"},
                "po_number": {"type": "text", "instructions": "Purchase order number"},
                "days_to_pay": {
                    "type": "estimate",
                    "min": 0,
                    "max": 120,
                    "step": 1,
                    "instructions": "Days after issue until this invoice is paid",
                },
            },
        },
    )
    print(response.json())


if __name__ == "__main__":
    main()
