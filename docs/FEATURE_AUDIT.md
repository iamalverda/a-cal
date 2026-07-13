# A-Cal Feature Audit — cal.com, Gmail, Calendly vs A-Cal

> Comprehensive feature inventory of Calendly, Google Gmail, and cal.com,
> mapped against A-Cal's current implementation. Gaps are prioritized by
> impact on the user's stated goal: unified multi-account email + scheduling
> platform.

---

## 1. Calendly — Feature Inventory

### Scheduling & Event Types
- One-off meeting links (single-use)
- Recurring event types (daily/weekly/monthly)
- Round-robin scheduling (distribute among team members)
- Collective scheduling (all team members attend)
- Managed event types (admin assigns team member)
- Secret event types (not on public profile)
- Group events (multiple attendees, capacity limit)
- Custom event duration (fixed or flexible)
- User-selectable duration (attendee picks 15/30/60)
- Buffer time before/after events
- Padding between meetings
- Minimum scheduling notice (e.g. 24h ahead)
- Maximum scheduling window (e.g. 60 days out)
- Event color coding
- Custom questions per event type
- Require approval before booking confirmed
- Cancellation policy per event type
- Reschedule by attendee (self-service)
- Cancel by attendee (self-service)
- No-show tracking
- Adhoc meeting (instant / no scheduling)

### Availability
- Availability schedules (per day, time ranges)
- Multiple availability schedules per user
- Date-specific overrides (vacation, travel)
- Timezone detection (auto-detect attendee timezone)
- Timezone display in attendee's local time
- Calendar sync for real-time availability (Google, Outlook, iCloud)
- Double-booking prevention (live calendar check)
- Connected calendar conflict detection
- Schedule limits (max events per day, per week)

### Booking Page & Branding
- Public booking page (custom URL slug)
- Custom branding (logo, colors, fonts)
- Cover image / hero image
- Custom subdomain (calendly.com/yourname)
- Custom domain (your.domain.com)
- Landing page customization
- Multi-language booking pages
- Social proof / testimonials section
- Event type grouping/categories
- Inline embed (iframe)
- Popup widget embed
- Popup text link embed
- WordPress plugin
- Squarespace integration
- Wix integration

### Notifications & Reminders
- Email confirmations (booking created)
- Email reminders (custom timing: 1h, 24h before)
- SMS reminders (via Twilio)
- WhatsApp reminders
- Follow-up emails (after meeting)
- Customizable email templates
- Confirmation/rejection emails to host
- Cancellation emails
- Reschedule emails
- Attendee email branding

### Integrations
- Google Calendar (two-way sync)
- Outlook/Office 365 Calendar
- iCloud Calendar
- Zoom (auto-generate meeting link)
- Google Meet (auto-generate)
- Microsoft Teams (auto-generate)
- Webex
- GoToMeeting
- Salesforce CRM
- HubSpot CRM
- Pipedrive CRM
- Zoho CRM
- Stripe (paid meetings)
- PayPal (paid meetings)
- Square (paid meetings)
- Mailchimp
- ActiveCampaign
- Zapier
- Make (Integromat)
- Slack notifications
- Discord notifications
- Intercom
- Zendesk
- Piktochart
- Eventbrite
- Facebook Pixel
- Google Analytics
- LinkedIn Ads

### Team Features
- Team scheduling pages
- Round-robin assignment
- Collective availability
- Team member profiles
- Admin management
- User roles & permissions
- Event type assignment per member
- Team analytics

### Analytics & Reporting
- Booking metrics (total, completed, cancelled)
- No-show rate
- Revenue tracking (paid events)
- Event type performance
- Booking source tracking
- Attendee geography
- Conversion funnel
- Custom date ranges
- Export to CSV
- Weekly email reports

### Billing & Payments
- Paid event types (charge for booking)
- Subscription pricing
- Tiered pricing
- Coupon codes
- Refund management
- Tax handling
- Currency support
- Stripe Connect for teams

### Workflow Automation
- Calendly Workflows (trigger-based automations)
- Pre-event workflows (send prep email)
- Post-event workflows (send follow-up)
- Cancelled event workflows
- Rescheduled event workflows
- No-show workflows
- Conditional logic in workflows
- Delay steps in workflows

### Admin & Security
- SSO (SAML)
- SCIM provisioning
- Audit logs
- Data residency
- HIPAA compliance (Premium)
- GDPR compliance
- SOC 2 compliance
- Two-factor authentication
- IP allowlisting

---

## 2. Google Gmail — Feature Inventory

### Inbox & Organization
- Inbox (default)
- Starred
- Snoozed (snooze to later time/date)
- Important (priority inbox markers)
- Sent
- Drafts
- Scheduled send (send later)
- Spam
- Trash
- All Mail (archive of everything)
- Priority Inbox (smart sorting)
- Multiple Inboxes (lab feature)
- Categories: Primary, Social, Promotions, Updates, Forums
- Bundles (auto-grouped emails)
- Custom labels (user-created, color-coded)
- Nested labels (label/sublabel hierarchy)
- Filters (auto-apply rules on incoming)
- Search within label

### Composing & Sending
- Rich text editor (bold, italic, underline, strikethrough)
- Font family/size/color selection
- Bullet/numbered lists
- Alignment (left, center, right, justify)
- Indentation
- Attachments (drag-and-drop, 25MB limit)
- Inline images
- CC and BCC
- Reply / Reply All / Forward
- Reply from address (multiple From)
- Signature (text, image, multiple signatures)
- Vacation responder (auto-reply)
- Email templates (canned responses)
- Send + Archive (shortcut)
- Undo send (cancel within 5-30s)
- Confidential mode (expiry, no forwarding)
- Request read receipt (Google Workspace)
- Delivery status notifications
- Schedule send (pick date/time)
- Smart Compose (AI suggestions while typing)
- Smart Reply (suggested quick replies)
- External recipient warning
- Attachment reminder (mentions "attached" but no file)

### Reading & Viewing
- Conversation/thread view (group by thread)
- Message preview pane (vertical or horizontal split)
- Reading pane toggle
- Star messages (single star, multiple star colors)
- Mark as read/unread
- Mark important/unimportant
- Archive (remove from inbox, keep in All Mail)
- Mute thread (auto-archive future replies)
- Report spam / phishing
- Block sender
- Print message
- Download message (.eml)
- Show original (raw headers)
- Open attachments
- Save attachments to Google Drive
- Attachment preview (inline)
- Show trimmed content (expand collapsed replies)

### Search
- Search bar with autocomplete
- Search operators: from:, to:, subject:, has:attachment, label:, is:unread, is:starred, before:, after:, larger:, filename:, in:anywhere, OR, AND, NOT, group by
- Search across all accounts (Gmail multi-account)
- Search suggestions
- Search history
- Advanced search form

### Multi-Account
- Add multiple Gmail accounts
- Switch between accounts (avatar dropdown)
- All-inbox view (see all accounts at once)
- Account-specific inbox
- Unified notifications across accounts
- Account color coding
- Separate signatures per account
- Account-specific labels
- Gmail on web: 5 accounts max in browser
- Google Workspace + personal account coexistence
- delegated access (access another's mailbox)

### Keyboard Shortcuts
- 100+ keyboard shortcuts
- Shortcut customization
- Quick keys: j/k (navigate), e (archive), # (delete), r (reply), a (reply all), f (forward), s (star), c (compose)
- ? to show shortcuts
- Vim-like navigation

### Labels & Filters
- Create label (with color)
- Apply label manually or via filter
- Multiple labels per message
- Show/hide label in list
- Show label in message list
- Filter: from, to, subject, includes words, excludes words, has attachment, size, date range
- Filter actions: skip inbox, mark read, star, apply label, forward to, delete, never send to spam, mark important, categorize
- Import/export filters

### Security & Privacy
- 2-Step Verification
- App passwords
- Security checkup
- Recent activity / account activity
- Show details (sessions, IP)
- Remote sign-out
- Less secure apps (deprecated)
- Confidential mode
- Block sender
- Unsubscribe (one-click)
- Phishing protection
- Spam filtering
- Attachment virus scanning

### Settings & Customization
- Display density (default, comfortable, compact)
- Theme (light, dark, custom)
- Inbox type (default, important first, unread first, starred first, priority)
- Reading pane on/off
- Preview pane
- Notification settings (desktop, mobile, sound)
- Vacation responder
- Signature management
- Forwarding (auto-forward to another address)
- POP/IMAP access
- Send mail as (multiple from addresses)
- Alias management
- Vacation dates
- Out of office
- Custom from (SMTP relay)

### Mobile
- iOS app
- Android app
- Push notifications
- Swipe actions (customize)
- Multiple accounts
- Unified inbox on mobile
- Offline mode
- Widget

### Gmail-specific AI features
- Smart Compose
- Smart Reply
- Summarize this email (Gemini)
- Help me write (Gemini)
- Priority markers (AI-based)
- Nudges (AI suggests following up)
- Summary cards (order tracking, flights, etc.)

---

## 3. cal.com — Feature Inventory

> cal.com is the open-source alternative to Calendly with many
> additional developer-focused features.

### Core Scheduling
- Event types (fixed duration, flexible, secret)
- Recurring events
- Round-robin / collective / managed event types
- Group events with capacity
- Buffered events (before/after)
- Minimum notice / maximum booking window
- Requires confirmation / approval workflow
- Reschedule / cancel by attendee
- Recurring event series support
- Unavailable / vacation scheduling
- Multi-day events
- Location per event (in-person, online link, phone, custom)
- Secret events
- Event type metadata / custom fields

### Availability
- Availability schedules (per-day time slots)
- Date overrides (specific date availability)
- Timezone-aware scheduling
- Detect attendee timezone
- Connected calendar conflicts (Google, Outlook, CalDAV, iCloud, Exchange)
- Double-booking prevention
- Schedule limits
- Working hours per event type
- Multi-timezone support for team members

### Booking Flow
- Public profile page with event types
- Custom branding / themes
- Custom domain support
- Embed (iframe, popup, inline)
- Multi-language support (20+ languages)
- Attendee enters name, email, optional notes
- Custom questions / form fields
- Captcha / bot protection
- Payment at booking (Stripe)
- Tipping option
- Add-on options (upsells)
- Waitlist / wait queue when slot is full

### Integrations
- Google Calendar
- Microsoft Outlook / Office 365
- Apple iCloud
- CalDAV (generic)
- Zoom
- Google Meet
- Microsoft Teams
- Webex
- Jitsi
- Daily.video
- HubSpot
- Salesforce
- Pipedrive
- Close
- Notion
- Stripe
- PayPal
- Slack
- Discord
- Telegram
- Zapier
- Make
- Google Analytics
- Meta Pixel
- HubSpot ads
- Segment
- Amplitude
- PostHog
- Close
- Shopify
- Zoho

### Team / Organization
- Organization / team management
- Team event types (round-robin, collective, managed)
- Team member profiles
- Team availability
- Team booking pages
- Routing forms (route to right person based on answers)
- Delegation (book on behalf of)
- Managed event types (admin controls)
- Member routing
- Team-level workflows

### Workflows & Automation
- Automated email/SMS reminders
- Custom workflow triggers (event created, rescheduled, cancelled, no-show, completed)
- Workflow actions (email, SMS, webhook)
- Conditional workflows
- Time-delayed workflows
- Custom templates with variables
- No-show workflows
- Post-event follow-ups
- Pre-event prep emails
- Webhook events for external automation

### Apps & Ecosystem
- App Store (100+ apps)
- Custom app development
- OAuth app platform
- Webhooks
- REST API (full CRUD)
- GraphQL API
- TypeScript SDK (@calcom/sdk)
- Embedded (@calcom/embed)
- CLI tools
- Self-hosting (Docker)
- Vercel deployment

### Developer Features
- Full REST API
- GraphQL API
- Webhooks (event-driven)
- Custom apps (OAuth, API keys)
- Zapier app
- TypeScript SDK
- React embed component
- Self-hostable (MIT/AGPL)
- Custom database backend
- Event type API
- Booking API
- Availability API
- Routing form API
- Workflow API
- API keys management
- Webhook signatures

### Analytics
- Booking analytics
- Revenue analytics
- Attendee analytics
- Routing form analytics
- Team member performance
- Event type performance
- Conversion tracking
- UTM tracking
- Custom date ranges
- CSV export

### Payments
- Stripe integration (paid events)
- PayPal
- Subscription payments
- Partial payments / deposits
- Refunds
- Currency support
- Tax handling
- Tipping

### Seating & Special Types
- Seated events (assign seats)
- Workshops
- Classes
- Group lessons
- Limited capacity events

### Admin
- User management
- Organization management
- Audit logs
- SSO (SAML/OIDC)
- SCIM
- Domain management
- Custom branding (org level)
- Feature flags
- API key management
- Webhook management

### Routing Forms
- Custom routing forms (route to right team member)
- Conditional routing logic
- Form analytics
- Skip routing (direct booking)
- Custom fields on forms

### Availability Sharing
- Share availability (without booking)
- Poll for meeting time (find best time among group)
- Recurring availability shares

---

## 4. A-Cal Current State — Feature Audit

### What A-Cal HAS (strengths)
| Feature | Status | Notes |
|---------|--------|-------|
| Sub-account hierarchy | ✅ Strong | One identity, many linked provider accounts |
| Google Calendar provider | ✅ | Direct REST API, OAuth |
| Outlook provider | ✅ | OAuth |
| CalDAV provider | ✅ | Generic CalDAV support |
| Gmail email provider | ✅ | Direct Gmail API, OAuth |
| IMAP/SMTP email provider | ✅ | Any email server |
| Email listing (inbox) | ✅ Basic | Fetches messages, shows subject/from/snippet |
| Email send | ✅ | Via connected provider |
| Email reply | ✅ Basic | Threading headers |
| Calendar-invite detection | ✅ | Headers + labels |
| Email scheduling scan | ✅ | Detects meeting proposals, conflicts |
| Agent conductor | ✅ Strong | Routes NL to 5 specialists |
| Self-model | ✅ Strong | Pattern memory, attention, identity |
| Federated swarm negotiation | ✅ | Sub-account conflict resolution |
| Model routing (BYOK) | ✅ | 11+ providers, privacy-tiered |
| Sync engine (4 modes) | ✅ | Mirror, merge, federation, per-sub-agent |
| Sync rules | ✅ | Include/exclude/transform/agent |
| Skill modes (Simple/Pro/Dev) | ✅ | Additive, reversible |
| Marketplace | ✅ | Share/remix/install configs |
| Plugin system | ✅ | Python plugins, hooks |
| Config-as-code | ✅ | Export/import JSON |
| Agent spec CRUD | ✅ | Custom agents |
| Visual workflow builder | ✅ | Chain agent steps |
| REST API | ✅ Strong | 127 endpoints |
| TypeScript SDK | ✅ | Full API coverage |
| Analytics | ✅ | Busy times, meeting stats |
| Event types | ✅ Basic | Scheduling types, availability |
| Free slot finder | ✅ | Search available time |
| Auth (demo + persistent) | ✅ | Session-based |
| PostgreSQL support | ✅ | Production DB |
| Docker self-hosting | ✅ | docker compose |
| E2E tests (Playwright) | ✅ | 83 tests |

### What A-Cal LACKS — Gap Analysis

#### Email Gaps (HIGH PRIORITY — user explicitly requested)
| Gap | Priority | Source |
|-----|----------|--------|
| Unified inbox (all accounts in one view) | 🔴 Critical | Gmail |
| Per-account inbox filtering | 🔴 Critical | Gmail |
| Account badge on each email (which account) | 🔴 Critical | Gmail |
| Folders (Sent, Drafts, Starred, Spam, Trash, All Mail) | 🔴 High | Gmail |
| Star/unstar messages | 🔴 High | Gmail |
| Mark read/unread | 🔴 High | Gmail |
| Archive | 🟡 Medium | Gmail |
| Delete / trash | 🟡 Medium | Gmail |
| Search across all accounts | 🟡 High | Gmail |
| Thread/conversation view | 🟡 Medium | Gmail |
| Snooze | 🟢 Low | Gmail |
| Labels (custom, color-coded) | 🟢 Low | Gmail |
| Filters (auto-apply rules) | 🟢 Low | Gmail |
| Rich text compose editor | 🟡 Medium | Gmail |
| Multiple From addresses | 🟡 Medium | Gmail |
| Signature management per account | 🟡 Medium | Gmail |
| Attachments (send + receive) | 🟡 High | Gmail |
| Forward | 🟡 Medium | Gmail |
| Reply All | 🟡 Medium | Gmail |
| Scheduled send | 🟢 Low | Gmail |
| Undo send | 🟢 Low | Gmail |
| Vacation responder | 🟢 Low | Gmail |
| Email templates (canned) | 🟢 Low | Gmail |
| Priority inbox / categories | 🟢 Low | Gmail |
| Keyboard shortcuts | 🟢 Low | Gmail |
| Smart Compose / Smart Reply | 🟢 Low | Gmail (AI) |
| AI email summarization | 🟡 Medium | Gmail (Gemini) |
| Mobile app | 🟢 Low | Gmail |

#### Scheduling Gaps (HIGH PRIORITY — cal.com/Calendly)
| Gap | Priority | Source |
|-----|----------|--------|
| Public booking page (shareable link) | 🔴 High | Calendly/cal.com |
| Custom booking page URL/slug | 🔴 High | Calendly/cal.com |
| Custom branding (logo, colors) | 🟡 Medium | Calendly/cal.com |
| Recurring event types | 🟡 Medium | Calendly/cal.com |
| Group events (capacity) | 🟡 Medium | Calendly/cal.com |
| Round-robin scheduling | 🟡 Medium | Calendly/cal.com |
| Collective scheduling | 🟡 Medium | Calendly/cal.com |
| Buffer time before/after | 🟡 Medium | Calendly/cal.com |
| Min notice / max booking window | 🟡 Medium | Calendly/cal.com |
| Require approval before booking | 🟡 Medium | Calendly/cal.com |
| Attendee self-reschedule/cancel | 🟡 Medium | Calendly/cal.com |
| Custom questions per event type | 🟡 Medium | Calendly/cal.com |
| Email/SMS reminders | 🟡 Medium | Calendly/cal.com |
| Booking confirmation/rejection emails | 🟡 Medium | Calendly/cal.com |
| Zoom/Meet/Teams auto-link | 🟡 Medium | Calendly/cal.com |
| Paid events (Stripe) | 🟢 Low | Calendly/cal.com |
| Team scheduling pages | 🟢 Low | Calendly/cal.com |
| Routing forms | 🟢 Low | cal.com |
| Embed widget (iframe/popup) | 🟡 Medium | Calendly/cal.com |
| Custom domain | 🟢 Low | Calendly/cal.com |
| Multi-language booking pages | 🟢 Low | cal.com |
| No-show tracking | 🟢 Low | Calendly |
| Waitlist when full | 🟢 Low | Calendly |
| Workflow automations (trigger-based) | 🟡 Medium | Calendly/cal.com |
| Webhook events | 🟡 Medium | cal.com |
| GraphQL API | 🟢 Low | cal.com |
| Availability sharing (no booking) | 🟢 Low | cal.com |
| Poll for meeting time | 🟢 Low | cal.com |
| Attendee notifications | 🟡 Medium | Calendly/cal.com |

#### Calendar Gaps
| Gap | Priority | Source |
|-----|----------|--------|
| Calendar event CRUD (create/edit/delete) | 🔴 High | All |
| Drag-to-reschedule | 🟡 Medium | cal.com |
- Event color coding | 🟡 Medium | Calendly |
| All-day events | 🟡 Medium | All |
| Recurring events | 🟡 Medium | All |
| Attendee management | 🟡 Medium | All |
| Reminders/notifications | 🟡 Medium | All |
| Calendar sharing (public/private) | 🟢 Low | Google Calendar |

---

## 5. Priority Implementation Roadmap

### Phase 1 — Unified Multi-Account Email (this session)
1. Unified inbox: all email accounts in one view
2. Per-account filtering (account switcher)
3. Account badge on each message
4. Folders: Inbox, Starred, Sent, Drafts, All Mail
5. Star/unstar, mark read/unread, delete
6. Search across all accounts
7. Compose with account selector (send from any account)
8. Reply / Reply All / Forward
9. Attachments (send + receive display)

### Phase 2 — Scheduling Improvements
1. Public booking page with custom slug
2. Recurring event types
3. Buffer time, min notice, max window
4. Custom questions per event type
5. Email/SMS reminders
6. Booking confirmation emails
7. Zoom/Meet/Teams auto-link generation
8. Embed widget (iframe)

### Phase 3 — Calendar Improvements
1. Full event CRUD
2. Drag-to-reschedule
3. All-day + recurring events
4. Attendee management
5. Event color coding

### Phase 4 — Advanced Email
1. Labels (custom, color-coded)
2. Filters (auto-apply rules)
3. Snooze
4. Scheduled send
5. Vacation responder
6. Email templates
7. AI summarization
8. Keyboard shortcuts

### Phase 5 — Team & Payments
1. Team scheduling pages
2. Round-robin / collective
3. Paid events (Stripe)
4. Routing forms
5. Workflow automations
6. Webhooks

### Phase 6 — Developer & Platform
1. GraphQL API
2. Public booking page embed
3. Custom domain support
4. Mobile app

---

## Summary

A-Cal already has a strong agentic foundation that cal.com, Gmail, and
Calendly do not have: unified identity, agent swarm, self-model, marketplace,
and developer layer. The gaps are concentrated in two areas:

1. **Email UX** — Gmail-class inbox management (unified view, folders, search,
   star, read/unread, labels, filters). This is the user's explicit request
   and Phase 1 priority.

2. **Scheduling UX** — Calendly/cal.com-class booking pages (public links,
   custom questions, reminders, video link auto-generation, embed widgets).
   This is Phase 2.

The combination of A-Cal's agentic layer + Gmail-class email + Calendly-class
scheduling would make it genuinely competitive with all three products.
