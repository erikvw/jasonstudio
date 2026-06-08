# Workflow

The end-to-end flow from initial customer contact through to digital delivery.

## Overview

```
Service Catalog ──► Quotation ──► Order ──► Event ──► Selections ──► Invoice ──► Payment ──► Download
```

## 1. Service Catalog

The photographer defines reusable services with default rates. These are pulled into quotations to avoid retyping rates for every job.

| Service | Unit Type | Example Rate |
|---------|-----------|-------------|
| Photography | Per Hour | $150.00/hr |
| Image Processing | Per Image | $2.00/image |
| Travel | Per Km | $0.55/km |
| Gallery Hosting | Flat Fee | $50.00 |
| Equipment Rental | Each | $75.00 |

Services can be marked active/inactive and are sorted by `sort_order`.

## 2. Quotation

The photographer prepares a quotation for a customer on a specific event.

**Creating a quote:**
1. Navigate to the event's orders page
2. Click "Quote" for the customer
3. Add line items from the service catalog (quick-add buttons) or freeform
4. Set the deposit amount and validity date
5. Save — totals are auto-calculated (subtotal, tax, total)

**Quote structure:**

```
Photography          3.00 hrs × $150.00    $450.00
Image Processing    50.00 img ×   $2.00    $100.00
Travel              80.00 km  ×   $0.55     $44.00
Gallery Hosting      1.00      ×  $50.00     $50.00
                                ──────────────────
                                Subtotal    $644.00
                          Deposit Required  -$100.00
                             Tax (13.00%)    $83.72
                                ──────────────────
                                   Total    $627.72
```

**Status flow:**

```
Draft ──► Sent ──► Accepted ──► (Order created)
                └─► Declined
                └─► Expired (past valid_until date)
```

**Acceptance:** either the customer accepts through the app, or the photographer marks it accepted on their behalf.

## 3. Order Creation

When a quotation is accepted:
- An **Order** is automatically created
- Photographer hours and rate are pre-filled from the per-hour line item
- The deposit amount carries over from the quotation
- The order is linked back to the quotation (`order.quotation`)

## 4. Event & Photo Upload

The photographer creates the event, links customers, and uploads photos after the shoot.

- Files are uploaded in **batches of 20** via JavaScript to handle large shoots (400+ files) without hitting OS file descriptor limits
- Files can be selected individually or by choosing an entire folder
- A progress bar tracks batch-by-batch progress
- Three image versions are generated on upload: original, thumbnail (800px watermarked), full-res watermarked
- EXIF metadata is extracted (camera, aperture, shutter speed, ISO, focal length)
- Photos are sorted by `sort_order`, then upload time
- Watermark text and opacity are configurable via `WATERMARK_TEXT` and `WATERMARK_OPACITY` settings (see [Configuration](configuration.md))

### Regenerate Thumbnails

If watermark settings are changed after upload, the photographer can regenerate all thumbnails and watermarked images for an event using the **Regenerate Thumbnails** button on the upload page. This re-processes photos in batches from the stored originals.

## 5. Customer Selections

Customers log in and browse the watermarked gallery. For each photo they choose:

| Choice | Description |
|--------|-------------|
| **Digital** | Digital delivery only |
| **Print & Digital** | Print (with size selection) plus digital |
| **Reject** | Not wanted |

Print sizes: 4x6, 5x7, 8x10, 4x4, 8x8, 4x5.3

Selection counts update live via HTMX as the customer clicks.

## 6. Invoice

The invoice is generated from the order and the customer's selections.

```
Photography          2.00 hrs × $150.00    $300.00
Print & Digital — 5×7  (photo1.jpg)         $0.00
Print & Digital — 8×10 (photo2.jpg)         $0.00
Digital images       3 ×          $0.00     $0.00
                                ──────────────────
                                Subtotal    $300.00
                                 Deposit   -$100.00
                             Tax (13.00%)    $39.00
                                ──────────────────
                              Amount Due    $239.00
```

- Tax is calculated on the **full subtotal** (not reduced by deposit)
- The deposit is a credit against the total
- Invoice numbers are auto-generated: `INV-00001`

## 7. Payment & Download

Once the photographer marks the order as **Paid**:

- `paid_at` timestamp is recorded
- Customer sees a download link on their selections page
- Download link is valid for **30 days** from payment
- Each download increments a counter

## 8. Share Codes

A paid customer can generate a **6-character share code** to give friends access to the digital photos.

- Friends visit `/shared/<CODE>/` — no login required
- The code is valid as long as the order's download is available and the event isn't archived
- Customer or photographer can deactivate the code
- Generating a new code deletes the old one (fresh code each time)
