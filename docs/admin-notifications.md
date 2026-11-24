# Supabase Admin Notifications

This guide configures Supabase Database Webhooks to send selected account and administration events to the Quiz Space Telegram bot. The bot only sends notifications; it does not update application records.

## Telegram setup

1. Open the bot in Telegram and send `/start` at least once so Telegram permits the bot to message your account.
2. Set `TELEGRAM_ADMIN_CHAT_ID` in Railway to your Telegram numeric user ID (or the intended private admin chat ID), then redeploy.
3. If `TELEGRAM_ADMIN_CHAT_ID` is unset, admin notifications fall back to `TELEGRAM_ALERT_CHANNEL_ID`; if that is also unset, they are sent to configured Admin/Owner Telegram users.
4. Set `SUPABASE_WEBHOOK_SECRET` in Railway to a long random value. Store the same value only in the Supabase webhook header; never commit it or put it in a URL.

## Bot endpoint

Use the public Railway domain and this endpoint:

```text
POST https://<bot-domain>/webhooks/supabase
Header: X-Webhook-Secret: <same SUPABASE_WEBHOOK_SECRET>
Content-Type: application/json
```

The service listens on Railway's injected `PORT`. When `PORT` is absent, it uses `TELEGRAM_WEBHOOK_PORT` (default `8080`). Configure Railway's health check to use `GET /health` as before.

## Create Supabase Database Webhooks

In Supabase, open **Database → Webhooks → Create a new webhook**. For each hook, select the `public` schema, use the endpoint above, add the `X-Webhook-Secret` header, and choose these tables/events:

| Table | Events | Telegram notification |
|---|---|---|
| `premium_requests` | `INSERT`, `UPDATE` | New paid/standard activation request; trial request; approval or rejection status transition |
| `users` | `INSERT` | New user (this Quiz Space project uses `uid` as the user key) |
| `subscription_plans` | `INSERT`, `UPDATE`, `DELETE` | Administrative table change |

The handler accepts only these tables in the `public` schema. It also accepts `profiles` inserts for legacy deployments, but the current Quiz Space database has a `users` table and no `profiles` table. Other tables/events are ignored. Keep webhook requests within the service's 1 MiB request limit.

## Fields and privacy

For `premium_requests` inserts, the bot reads only scalar values from these optional field names:

- Plan/package: `plan_name`, `plan`, `subscription_plan`, `package_name`, `package`, `subscription_type`
- Amount: `amount`, `payment_amount`, `payable_amount`, `total_amount`, `price`
- Payment method: `payment_method`, `method`, `payment_type`
- Request ID: `id`, `user_id`, `profile_id`, or `request_id`. User-created notifications use `uid` first, matching the current `users` table.

Trial requests are detected from true-valued `is_trial`, `trial`, `is_trial_request`, or `trial_request` fields, or from a `request_type`, `type`, plan, or package value containing “trial”, “demo”, “تجريبي”, or “تجربة”. Approval/rejection notices are sent when one of `status`, `approval_status`, `request_status`, or `state` transitions to an approved/rejected value; a boolean `approved` transition is also supported.

Messages show no more than the first eight characters of an identifier. The bot never copies email addresses, phone numbers, receipt images, or the full webhook record into Telegram. For `users` (or legacy `profiles`), only a short identifier is sent. For `subscription_plans`, only the table name, event action, and short row identifier are sent. Incoming payloads are not written to logs.

Telegram HTML text is escaped before sending. A missing/incorrect secret receives HTTP `401`; malformed JSON receives `400`. If Telegram notification delivery fails, the endpoint returns `503` so the webhook sender can retry. Unsupported tables or events are acknowledged and ignored.

## Telegram webhook mode note

The recommended deployment for this receiver is the bot's default long-polling mode (`TELEGRAM_USE_WEBHOOK=false`), with the HTTP receiver bound to Railway's `PORT`. Telegram webhook mode uses `TELEGRAM_WEBHOOK_PORT` for its Telegram listener; hosting both listeners through one public ingress may require host-level path routing or a separate public endpoint. Do not assume a second internal port is publicly reachable on Railway.

## Example payload shape

Supabase Database Webhooks send a record envelope similar to:

```json
{
  "type": "INSERT",
  "schema": "public",
  "table": "premium_requests",
  "record": {
    "id": "12345678-1234-1234-1234-123456789012",
    "plan_name": "Monthly",
    "amount": 100,
    "payment_method": "bank_transfer"
  },
  "old_record": null
}
```

Do not include real customer data in manual test payloads or issue examples in public support channels.
