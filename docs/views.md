# Views

## Role-Based Access

The app uses two roles determined by profile models:

- **Photographer**: user has a `PhotographerProfile`
- **Customer**: user has a `Customer` profile

The `home` view redirects authenticated users to the appropriate dashboard.

## Service Catalog

### Service List (`/photographer/services/`)

Table of all services with name, unit type, default rate, active status. Photographer only.

### Add/Edit Service (`/photographer/services/add/`, `/photographer/services/<id>/edit/`)

Form with name, description, unit type (Per Hour, Per Image, Per Km, Flat Fee, Each), default rate, sort order, and active toggle.

## Quotations

### Quotation Edit (`/photographer/event/<event_id>/quote/<customer_id>/`)

Photographer creates or edits a quotation. Features:

- **Quick-add from catalog**: buttons for each active service, pre-fills description and rate
- **Dynamic line items**: add/remove rows with JavaScript, live price calculation (qty × unit cost)
- **Deposit amount** and **valid until** date fields
- **Notes** field for freeform terms
- Saves and recalculates totals (subtotal, tax from photographer profile, total)

### Quotation View (`/photographer/event/<event_id>/quote/<customer_id>/view/`)

Print-friendly quotation document. Shows:

- Photographer contact details and branding
- Customer and event details
- Line items table with qty, unit cost, price
- Subtotal, deposit, tax, total
- ACCEPTED / DECLINED / EXPIRED stamp overlay
- "Accept on Behalf of Customer" button (for draft/sent quotes)

### Photographer Accept (`POST /photographer/event/<event_id>/quote/<customer_id>/accept/`)

Photographer marks a quote as accepted. Creates an Order with hours/rate/deposit pre-filled. Redirects to the order detail page.

### Customer Quotation View (`/my-quotes/<event_id>/`)

Customer views their quote. Same template as photographer view, but with Accept/Decline buttons instead of the edit link.

- Expired quotes show a warning instead of action buttons
- Accept creates the Order and redirects to My Selections

### Customer Accept/Decline (`POST /my-quotes/<event_id>/accept/`, `POST /my-quotes/<event_id>/decline/`)

Customer accepts (creates Order) or declines (sets status to Declined). Expired quotes cannot be accepted.

## Customer Views

### Event Gallery (`/gallery/<event_id>/`)

Browse watermarked photos with filter tabs (All, Digital, Print & Digital, Rejected). Make selections via HTMX toggle buttons. Counts update live via OOB swaps.

### My Selections (`/my-selections/`)

View all selections grouped by event. Shows payment status, download/share buttons when paid. Supports `?event=<id>` filter.

### Selection Invoice (`/invoice/<event_id>/`)

View the invoice for an order. Creates/updates the Invoice model on each view. Shows PAID/UNPAID stamp, line items, deposit, tax, amount due, payment instructions.

### Customer Download (`/download/<event_id>/`)

ZIP download of original (unwatermarked) photos. Requires:
- Order is paid
- Within 30 days of payment
- Increments download counter

### Share Links

- **Create** (`POST /share/<event_id>/create/`): generates a new 6-char code, deletes any previous link
- **Deactivate** (`POST /share/<event_id>/deactivate/`): marks link inactive
- **Public page** (`/shared/<code>/`): shows download button or expired message
- **Public download** (`/shared/<code>/download/`): ZIP of digital selections

## Photographer Views

### Dashboard (`/photographer/`)

Overview of all events with action buttons: Quotes & Orders, Details, Upload, Gallery. Links to Services and Customers. Uses a card layout on small screens and a table on medium+ screens for responsive display.

### Event Management (`/photographer/event/<id>/`)

Edit event details, manage linked customers.

### Upload Photos (`/photographer/event/<id>/upload/`)

Bulk photo upload with automatic watermarking, thumbnail generation, and EXIF extraction.

- Files can be selected individually or by folder
- Uploads are sent in **batches of 20** via JavaScript `fetch()` to avoid OS file descriptor limits on large shoots (400+ files)
- A progress bar shows batch progress and running totals
- On upload, three image versions are created: original, thumbnail (800px watermarked), full-res watermarked

### Regenerate Thumbnails (`POST /photographer/event/<id>/regenerate-thumbnails/`)

Re-processes all thumbnails and watermarked images for an event using the current `WATERMARK_TEXT` and `WATERMARK_OPACITY` settings. Useful after changing watermark settings.

- Processes in batches of 20 photo IDs (sent from the browser) with a progress bar
- Reads the stored original image and regenerates both thumbnail and full-res watermarked versions
- Skips photos with missing original files
- Returns `{"processed": N, "skipped": N}` per batch
- A cache-busting query parameter (`?v=<timestamp>`) on image URLs ensures browsers display the updated thumbnails immediately

### Customer Order Detail (`/photographer/event/<id>/customer/<id>/`)

View order status, set photographer fee (hours, rate, deposit), manage share links, download originals, view photo grids with print sizes.

### Photographer Invoice (`/photographer/event/<id>/customer/<id>/invoice/`)

Same invoice template as customer view, with back-navigation to order detail.

## Customer Management

- **List** (`/photographer/customers/`): table with active/inactive filter
- **Add** (`/photographer/customers/add/`): creates User + Customer
- **Edit** (`/photographer/customers/<id>/edit/`)
- **Toggle Active** (`POST`): deactivates/reactivates customer and Django user
- **Delete** (`POST`): only if no linked events, orders, or selections
