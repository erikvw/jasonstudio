# Models

## Gallery App

### Service

Reusable service catalog item with default rates.

| Field | Type | Description |
|-------|------|-------------|
| name | CharField | Service name |
| description | TextField | Optional description |
| default_rate | Decimal | Default rate for this service |
| unit_type | CharField | Per Hour, Per Image, Per Km, Flat Fee, or Each |
| is_active | Boolean | Whether this service appears in quote forms |
| sort_order | int | Display ordering |

### Quotation

A quote prepared for a customer before the event.

| Field | Type | Description |
|-------|------|-------------|
| quote_number | CharField | Auto-generated `QUO-00001` |
| event | FK → Event | The event being quoted |
| customer | FK → Customer | The customer receiving the quote |
| status | CharField | Draft, Sent, Accepted, Declined, Expired |
| valid_until | DateField | Quote expiry date (optional) |
| deposit_amount | Decimal | Deposit required before the shoot |
| subtotal | Decimal | Sum of line item prices |
| tax_rate | Decimal | Tax percentage at time of quote |
| tax_amount | Decimal | Computed tax |
| total | Decimal | subtotal - deposit + tax |
| accepted_at | DateTime | When the quote was accepted |
| accepted_by | CharField | Who accepted: `customer` or `photographer` |
| notes | TextField | Freeform notes on the quote |

Unique constraint: one quotation per (event, customer).

The `accept(by)` method sets the status to Accepted and auto-creates an Order with photographer hours/rate and deposit pre-filled from the quote's line items.

### QuotationLineItem

Individual line on a Quotation.

| Field | Type | Description |
|-------|------|-------------|
| quotation | FK → Quotation | Parent quotation |
| service | FK → Service | Optional link to catalog service |
| sort_order | int | Display order |
| description | str | Line item description |
| qty | Decimal | Quantity |
| unit_cost | Decimal | Cost per unit |
| price | Decimal | Line total (qty × unit_cost) |

### Event

Represents a photography event (wedding, portrait session, etc.).

| Field | Type | Description |
|-------|------|-------------|
| name | CharField | Event name |
| date | DateField | Event date |
| location | CharField | Event location |
| description | TextField | Optional description |
| status | CharField | Draft, Published, or Archived |
| customers | M2M → Customer | Customers linked to this event |

### Photo

A single photograph uploaded to an event.

- Three versions stored: **original**, **thumbnail** (800px watermarked), **watermarked** (full-res)
- EXIF metadata extracted on upload (camera, focal length, aperture, shutter speed, ISO)
- Sorted by `sort_order`, then `uploaded_at`
- `modified` (auto_now) — updated on every save; used as a cache-busting query parameter on image URLs so browsers fetch fresh thumbnails after regeneration

### Selection

A customer's choice for a specific photo.

| Choice | Description |
|--------|-------------|
| Digital | Customer wants digital delivery only |
| Print & Digital | Customer wants a print (with size) plus digital |
| Reject | Customer does not want this photo |

Print sizes: 4x6, 5x7, 8x10, 4x4, 8x8, 4x5.3

Unique constraint: one selection per (photo, customer).

### Order

Tracks the overall order for one customer on one event.

| Field | Type | Description |
|-------|------|-------------|
| ref | CharField | Auto-generated `ORD-00001` |
| quotation | OneToOne → Quotation | The accepted quote that created this order (optional) |
| event | FK → Event | |
| customer | FK → Customer | |
| status | CharField | Pending Payment, Paid, In Progress, Delivered |
| photographer_hours | Decimal | Pre-filled from quote's per-hour line item |
| photographer_rate | Decimal | Pre-filled from quote's per-hour line item |
| deposit_amount | Decimal | Pre-filled from quote's deposit |
| download_count | int | Incremented each time files are downloaded |
| paid_at | DateTime | Auto-set when status changes to Paid |

Key properties:
- `is_paid`: True for Paid, In Progress, or Delivered
- `download_available`: True if paid and within 30 days of `paid_at`
- `download_expires_at`: `paid_at` + 30 days

### Invoice

Financial document generated from an Order.

| Field | Type | Description |
|-------|------|-------------|
| invoice_number | CharField | Auto-generated `INV-00001` |
| order | FK → Order | |
| status | CharField | Draft, Issued, Paid, Void |
| subtotal | Decimal | Sum of line item prices |
| deposit | Decimal | Deposit credited from the order |
| tax_rate | Decimal | Tax percentage at time of invoice |
| tax_amount | Decimal | Computed tax on full subtotal |
| amount_due | Decimal | subtotal - deposit + tax |
| issued_at | DateTime | Auto-set when status changes to Issued |

Tax is calculated on the **full subtotal**, not reduced by the deposit. The deposit is a payment credit.

### InvoiceLineItem

Individual line on an Invoice. Auto-generated from the order's selections.

| Field | Type | Description |
|-------|------|-------------|
| sort_order | int | Display order |
| description | str | Line item description |
| filename | str | Associated photo filename (if applicable) |
| qty | Decimal | Quantity |
| unit_cost | Decimal | Cost per unit |
| price | Decimal | Line total |

### Payment

Records a payment received against an Invoice.

- Methods: Cash, E-Transfer, Credit Card, Cheque, Other
- `reference` field is encrypted (transaction IDs, cheque numbers)
- Linked to Invoice (nullable for legacy data)

### ShareLink

Short code allowing friends to download digital photos from an order.

- 6-character alphanumeric code (uppercase + digits)
- `is_valid`: active AND order download available AND event not archived
- Can be deactivated by customer or photographer
- Creating a new link deletes the old one (fresh code each time)

## Accounts App

### Customer

- Linked 1:1 to Django User
- Fields: company_name, phone (encrypted), is_active, notes
- Protected from deletion when linked to events, orders, or selections

### PhotographerProfile

- Linked 1:1 to Django User
- Invoice settings: tax_rate, payment_terms, payment_instructions (encrypted), invoice_notes
- Contact: business_name, phone (encrypted), email (encrypted), address (encrypted)
