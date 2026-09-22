# Web Push notifications for Tryton 7.8

Reusable module for web-user inboxes, manual communications, scheduled messages,
plain-text templates, per-category preferences and Web Push delivery. Depends on
`web_user` and `company`; application-specific integrations belong in separate
modules.

## Installation

Install this module alongside your other Tryton modules and install its Python
requirements in the server environment:

```sh
pip install -r requirements.txt
```

These versions were verified with cryptography 50.0.1 and pyOpenSSL 26.4.0.
py-vapid 1.9.4 requires cryptography >= 46; upgrade older pyOpenSSL installations
alongside it. Earlier py-vapid releases may fail to generate VAPID keys with
`TypeError: curve must be an EllipticCurve instance`.
Update the module list and activate `notification_web_push` (or
upgrade a module that depends on it). Run the Tryton cron service. For larger
scheduled messages also run a Tryton queue worker and configure `[queue] worker = True`.

Two scheduled actions are installed: dispatch scheduled messages and enqueue push
notifications, both every minute. Sending takes place in separate queue tasks,
after the transaction that stores the inbox message has committed. HTTP calls
never occur while confirming an order.

When upgrading the initial campaign-based implementation, update both
`notification_web_push` and any installed integrating modules,
then restart the HTTP, cron and worker processes. Registration migrates the
scheduled-message tables, recipient relations, inbox links and cron method to
`notification.web.scheduled_message`, preserving record IDs and content.
Existing XML identifiers are retained so menus and permissions are updated in
place.

## Configure an application

Administrators configure applications under **Notifications → Configuration → Applications**:
company, name, lowercase code, public HTTPS origin and application path (leading
and trailing slash). For example `https://orders.example.com` and `/`.

Generate a persistent VAPID key pair in a protected directory using the `vapid`
command from py-vapid:

```sh
umask 077
vapid --gen
vapid --applicationServerKey
```

Keep `private_key.pem` outside the repository and web root. Copy the printed
application server key into the application's **VAPID Public Key**. Store the
private-key path in the Tryton server configuration; for application code
`customer_portal`:

```ini
[web_push]
vapid_private_key_customer_portal = /protected/path/private_key.pem
```

Set **VAPID Contact** to a contact URI, e.g. `mailto:admin@example.com`, and enable
push sending. Use the same key/configuration on the HTTP, cron and worker
processes. Restart these processes after changing server configuration. Do not
regenerate keys on every deployment: existing subscriptions depend on them.

The public browser-facing API belongs to the integrating application. It must
validate authentication and CSRF, associate devices with the actual authenticated
user, and restrict inbox/preference changes to that user. The integrating module
supplies these endpoints. Endpoints to push providers are HTTPS-only and restricted to
FCM, Mozilla and Apple. Additional trusted hosts may be configured in
`[web_push] allowed_hosts` (comma-separated exact hosts). Redirects are disabled.

## Send and manage messages

Assign the **Notifications** group to operators to consult notifications and
delivery history for their allowed companies. Assign **Notifications -
Configuration** to users who manage applications, templates and scheduled
messages under **Notifications → Configuration**. This group inherits the
general notification access and is assigned to the administrator by default.

Create a scheduled message, select an application and recipients, and enter title/body.
Optionally choose a template to copy its content, then adjust it. Supported
placeholders are `${customer}`, `${company}` and `${reference}` (empty for manual
scheduled messages). Templates use string substitution, never Python expressions or HTML.
Links are relative to the application, e.g. `sales`; absolute/external URLs and
parent-path traversal are rejected.

Use **Send Test** for a selected test recipient (their normal preferences apply).
Use **Schedule / Send** with a future date to schedule or leave the date empty to
send on the next cron run. Scheduled content/recipients cannot be edited: cancel
and copy the scheduled message to change them. Cancellation is possible before dispatch.

* Order/service messages always remain in the inbox. Their push channel can be
  disabled independently.
* Promotions and cart reminders require opt-in and are omitted when disabled.
* A push subscription is per application, user and device. It does not opt the
  user into promotions or reminders.
* Preferences are checked again when sending. Revoked, expired, reassigned and
  inactive-user subscriptions are skipped. 404/410 deactivate devices; temporary
  failures retry up to five attempts with backoff. Push expires after two days.
* “Accepted by Push Service” is not proof of display or reading. `read_at` records
  the app's explicit read action. The inbox remains available without push.

The outbox prevents normal duplicate dispatch and rechecks already accepted
records. As with other external side effects, a crash after provider acceptance
but before database commit may cause a retry. A stable notification tag replaces
repeated visible notifications for the same message.

## Integration API

Within the business transaction call the pool model's `publish` method:

```python
Message = Pool().get('notification.web.message')
Message.publish(application, web_user, title='Order received',
    body='Your order has been received.', path='orders/123', category='service')
```

Use a trusted server context. Extend `Application.eligible_user` to enforce
application-specific recipient membership and `Message.can_deliver` for business
conditions that must still hold at send time. The browser must implement service
worker registration, opt-in subscription, notification display and click handling.

## Verification

From the monorepository root, use the test-workflow runner with module
`notification_web_push` and scenario `notifications`. The scenario uses Proteus,
an isolated database, real subscription-key validation and mocked external push
responses. It never sends messages to real devices.

## Scheduled messages

The Scheduled Messages screen supports a single send (Next Send At) or a daily
send at a local time and IANA time zone. Daily rules remain scheduled, advancing
the next execution atomically with publication. A delayed cron sends one batch,
then advances to the next future occurrence without replaying missed days.
Recipients may be selected explicitly or resolved from all eligible application
users at dispatch time. Promotions continue to require opt-in.

The Devices screen preserves the original user-agent string and derives the
device type, operating system, browser and available device model from it,
including for existing subscriptions. Unknown models remain empty. Integrating
applications may provide `reported_device_model` when the browser exposes its
model through User-Agent Client Hints; this takes precedence over the parsed
model. Device information is descriptive and must not be used for authorization.

Business modules extend the message type selection and `publish_messages` for
conditional audiences; scheduling and delivery remain reusable infrastructure.
