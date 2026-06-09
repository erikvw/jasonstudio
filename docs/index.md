# Jason Studio

Photography studio management application built with Django.

## Features

- **Service catalog** — reusable services with default rates (per hour, per image, per km, flat fee)
- **Quotations** — prepare quotes from the service catalog, send to customers for acceptance
- **Event management** — create events, bulk upload photos (batched for large shoots) with automatic watermarking
- **Watermark control** — configurable watermark text and opacity, with thumbnail regeneration
- **Customer galleries** — customers log in to view watermarked photos and make selections
- **Selection workflow** — Digital, Print & Digital (with size choice), or Reject
- **Orders & Invoicing** — orders auto-created from accepted quotes, invoices with deposit, tax, amount due
- **Payment gating** — downloads only available after payment, 30-day expiry
- **Share codes** — customers share download access with friends via short codes
- **Customer management** — add, edit, activate/deactivate, delete (with protection)
- **Google Drive integration** — upload customer photo zips to Google Drive for easy sharing
- **Field encryption** — sensitive data (phone, email, address, payment references) encrypted at rest with Fernet
- **Responsive UI** — mobile-friendly layouts with card views on small screens, tables on desktop

## Contents

```{toctree}
:maxdepth: 2

getting-started
workflow
models
views
configuration
google_drive_setup
```
