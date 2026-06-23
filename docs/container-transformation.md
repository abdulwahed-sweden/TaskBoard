# TaskBoard → Container Operations Platform — Transformation Report

**Prepared:** 2026-06-23
**Baseline:** `main` @ `26959ca`, 141 tests passing, clean tree
**Verification basis:** the `organizations/` and `tasks/` source was read directly
(models, permissions, custom_fields, workflow, importer, api, serializers), plus
`settings.py`, root `urls.py`, and the realtime stubs. Claims below are grounded
in that code; inferences are flagged explicitly.

---

## 1. Current architecture map

### Django apps
Two domain apps, plus the project package:

| App | Responsibility |
|---|---|
| `organizations` | Tenancy + the configurable engine: `Organization`, `Membership`, `Project`, `ProjectType`, `FieldDefinition`, `StatusDefinition`; permission helpers; the two shared validators (`custom_fields.py`, `workflow.py`); session active-org helpers; context processor. |
| `tasks` | The work item: `Task`, `Comment`, `Activity`, `NotificationPreference`, `SavedView`; CBVs; DRF viewsets; importer; notifications; activity log. |
| `TaskBoard/` | Settings, root URLconf, WSGI/ASGI, **dead** Channels stubs. |

### Core models & relationships
```
Organization 1─∞ Membership ∞─1 auth.User          # role-based join table
Organization 1─∞ Project
ProjectType  1─∞ Project          (FK nullable, PROTECT)
ProjectType  1─∞ FieldDefinition  (the custom-field schema)
ProjectType  1─∞ StatusDefinition (the workflow)
Project      1─∞ Task
Task         ∞─1 auth.User        (owner = single assignee, nullable)
Task         1─∞ Comment
Task         1─∞ Activity         (append-only)
Project      1─∞ SavedView
auth.User    1─1 NotificationPreference
```
**Multi-tenancy finding:** `ProjectType`, `FieldDefinition`, and `StatusDefinition`
have **no `organization` FK** — `ProjectType.name` is globally unique. Schemas/
workflows are therefore **global, shared across all tenants**, configured via the
Django admin only. Fine for a single-operator deployment; matters for the new
domain (see §2).

### Permission model
- Roles `TextChoices` with numeric precedence: `owner(4) > admin(3) > member(2) > viewer(1)` (`ROLE_RANK` / `role_rank()`).
- Single predicate `has_role(user, org, min_role)` — anonymous/non-members always `False`.
- Web: `RequireRoleMixin` + `ActiveOrganizationMixin`; `OrgScopedTaskMixin.get_queryset()` filters to `project__organization__members=request.user` (read boundary, foreign objects 404).
- API: `IsOrgMemberForWrites` — reads need `viewer`, writes need `member`, per-object via `get_object_organization`. Viewsets never `.all()`.
- **Crown jewel.** Clean, centralized, tested. Reuse verbatim.

### Import flow
`tasks/importer.py` — pure pipeline, no DB writes until `commit`:
`parse_upload` (CSV/XLSX, BOM-tolerant, `MAX_ROWS=1000`) → `target_fields` →
`auto_mapping` → `map_row` → `clean_row` (string coercion, then reuses
`validate_custom_fields` + `validate_status`) → `preview` → `commit` (creates
valid rows, logs activity, returns `{created, skipped:[{row_number, errors}]}` —
partial import, invalid rows reported not dropped). **Caveat:** `commit()` is
hardcoded to `Task(...)`; parse/map/preview are generic.

### API structure
- DRF `ModelViewSet`s (`TaskViewSet`, `ProjectViewSet`) on a `DefaultRouter` under `/tasks/api/v1/`.
- Auth: session or token (`POST /api/token/`); unauthenticated → 403.
- Pagination (size 20), django-filter, ordering, search.
- OpenAPI via drf-spectacular: `/api/schema/`, `/api/docs/`, `/api/redoc/`.
- Serializers re-run the shared validators on write.

### ProjectType / custom fields / workflow
- `ProjectType` owns ordered `FieldDefinition`s and `StatusDefinition`s.
- `Task.custom_fields` validated by `validate_custom_fields`; `Task.status` by `validate_status`; `is_done` derived in `Task.save()` from `is_terminal_status`.
- **Key limitation:** any status → any status. **No transition rules exist yet.**

### Safe to reuse directly
- Tenancy (`Organization`, `Membership`, roles, `has_role`, `RequireRoleMixin`, active-org session + context processor).
- The configurable engine (`ProjectType`/`FieldDefinition`/`StatusDefinition` + both validators).
- DRF scaffolding (router, token auth, pagination/filter/ordering, spectacular, `IsOrgMemberForWrites`).
- Import pipeline parse→map→preview (generalize `commit`).
- Activity log + notifications pattern.
- Infra (`settings.py`, Docker/compose, CI).

### Honest caveats
- **WebSocket "groundwork" is non-functional.** `channels` not in requirements; consumers import a missing package; `routing.py` never wired into `asgi.py`. Real-time = greenfield, not reuse.
- Doubled URL prefix `/tasks/tasks/Task/...` (scaffolding artifact).
- `Unassigned` org backfill (migration `tasks/0003`).
- ProjectType is global, not org-scoped.
- Not yet read in full: `tasks/views.py`, `forms.py`, `organizations/views.py`, templates, `admin.py`, test bodies.

---

## 2. Domain transformation proposal (concept mapping)

| TaskBoard | Container Ops | Approach |
|---|---|---|
| Organization | Operating company / tenant | Reuse as-is |
| Membership/role | Staff roles | Reuse |
| Project | Customer account (engine substrate) | Keep; add real Customer/Site |
| Task | ServiceRequest | New model, not a rename |
| ProjectType | ServiceType schema | Reuse engine |
| FieldDefinition | Service-specific fields | Reuse engine |
| StatusDefinition | Operational lifecycle | Reuse + transition rules |
| Task.owner | Assignee → Driver via Assignment | Keep owner; add Assignment |
| due_date | requested_date / scheduled_date | Two fields |

**Recommendation:** rename UI language first, keep internal model names — build
**new** first-class domain models in a new `containers` app, reuse the engine by
composition (`custom_fields` + `status` validated by the existing validators),
keep `tasks`/`Task` installed and untouched, relabel UI now, defer any internal
`Task` rename indefinitely.

---

## 3. New domain model design (first version)

Principles: every tenant-owned model has an `organization` FK; reuse
`validate_custom_fields`/`validate_status`; index filtered/scoped columns.
Recommended early additive change: `ProjectType.organization` (nullable) so
service schemas can be tenant-specific.

- **Customer** — organization, name, customer_number(unique/org), org_number, email, phone, billing_address, notes, is_active, timestamps.
- **Site** — organization, customer, label, street, postal_code, city, municipality, country, lat/long, access_notes, is_active.
- **Container** — organization, customer, site, qr_uid(unique, opaque), pin_hash, container_type, size, serial_number, waste_category, status, placed_at, notes.
- **ServiceType** — wraps/extends ProjectType (code, default_sla_days, requires_pin, category) with custom fields per type.
- **Driver/Worker** — organization, user(nullable), name, phone, license_class, is_active.
- **Assignment** — service_request, driver, vehicle, scheduled_date/window, sequence, status, completed_at, notes.
- **ServiceRequest** — organization, customer, site, container, service_type, reference, source, requested_date, scheduled_date, status, priority, owner, contact, notes, custom_fields.
- **Optional** — Vehicle, Route, Attachment (needs media storage), NotificationLog.

(Full per-model fields/indexes/validation/admin/API/import detail in the original
report; this section is the production design that drives the migration plan.)

---

## 4. QR customer portal

Flow: scan QR → resolve `qr_uid` → PIN gate → safe info → pick service type →
requested date → notes → submit → lands in admin as `source=qr, status=new`.

- **URLs:** `/c/<qr_uid>/`, `/verify/`, `/request/`, `/done/<ref>/` (opaque qr_uid, never pk).
- **Views:** landing, verify_pin (rate-limited, signed time-boxed token), request_form/submit, done.
- **Forms:** PinForm; QRServiceRequestForm (service_type/requested_date/contact/notes only — no status/owner/customer selection).
- **Security:** derive org/customer/site server-side from container; PIN before any disclosure; signed time-boxed token; CSRF; honeypot/captcha; reject past dates; active containers only.
- **Rate limiting:** PIN verify 5/15min per qr_uid+IP with lockout; submit 3/hour. (`django-ratelimit` — new dep, needs approval.)
- **PIN storage:** hashed via Django hashers (`make_password`/`check_password`); min length; never plaintext.
- **Never exposed:** financials, customer_number, org_number, other tenants' data, serial_number, internal notes, driver/assignment data, DB pks, pin_hash.

---

## 5. Operations workflow

Statuses: `new → verified → scheduled → assigned → in_progress → completed`,
plus `cancelled`, `rejected`, `invoice_ready → invoiced`. Terminal: completed/
invoiced, cancelled, rejected.

**Must build:** a transition table + `can_transition(role, from, to)` (mirrors
`has_role`). Drivers advance only their assigned jobs; dispatchers (member)
schedule; admins reject/cancel/invoice. Notes required on rejected/cancelled.
Email triggers wired to the existing `notifications.py` + a `NotificationLog`.

---

## 6. Migration strategy (no big-bang)

| # | Step | Risk |
|---|---|---|
| 0 | Branch + baseline tag | none |
| 1 | New `containers` app (empty) | very low |
| 2 | Additive `ProjectType.organization` (nullable) | low |
| 3 | Customer/Site/Container/ServiceType/Driver models | low |
| 4 | ServiceRequest + Assignment + validator wiring | medium |
| 5 | Transition layer | medium |
| 6 | Seed service types + workflows | low |
| 7 | Admin | very low |
| 8 | API under `/containers/api/v1/` | medium |
| 9 | Generalize importer | medium-high |
| 10 | QR portal (public) | medium-high |
| 11 | UI relabel + Swedish i18n | low |
| 12 | Deprecate tasks (later) | high — defer |

Through step 8 everything is additive and cannot break the 141-test baseline.

---

## 7. UI/UX transformation

Nav: Dashboard · Customers · Sites · Containers · Service Requests · Schedule ·
Drivers · Imports · Reports · Settings.
Swedish: Översikt · Kunder · Adresser · Behållare · Serviceförfrågningar ·
Schema · Förare · Import · Rapporter · Inställningar.
Dashboard cards, list filters, status-timeline detail pages, purposeful empty
states, mobile-first QR portal (single column, ≥48px targets, 3-step progress).

---

## 8. API transformation

New router `/containers/api/v1/`: customers, sites, containers, service-requests,
drivers, assignments — all authenticated + org-scoped via `IsOrgMemberForWrites`.
Public QR endpoints `/api/public/c/<qr_uid>/[request/]` — `AllowAny` + PIN token
+ throttle + strict whitelisting serializers. Tenant scoping identical to today's
pattern. Update spectacular title/tags; mark public endpoints.

---

## 9. Import transformation

Generalize the importer (parse/map/preview already generic) with per-entity
catalogs + commit builders:
- Customers — req name, customer_number; dup by customer_number/org.
- Sites — req customer_number(FK), street, postal_code, city.
- Containers — req customer/site, container_type; qr_uid auto-gen; pin hashed.
- Service requests — req customer_number, service_type code; validated via the
  shared validators.
Keep the `{created, skipped:[…]}` partial-import contract and preview-before-write.

---

## 10. Implementation roadmap (small safe commits)

1. branch + baseline tag
2. scaffold containers app
3. org-scope ProjectType (nullable FK)
4. Customer/Site/Container models + admin
5. ServiceType + seed services/workflows
6. ServiceRequest + Assignment + validation
7. status transition layer
8. containers REST API + docs
9. generalize importer + entity catalogs
10. QR portal (public, PIN, rate-limited)
11. operations UI + Swedish i18n
12. deprecate tasks UI (deferred)

Each commit: independently green (`pytest` + `check --deploy`), revertible.

---

## Honest summary

The tenancy + role engine, the schema/workflow validators, the org-scoped DRF
layer, and the import pipeline are exactly the reusable substrate this product
needs, and they are clean and tested. The real work is net-new domain models, a
transition-rules layer (which does not exist yet), a generalized importer, and a
public QR surface — all additive, so the 141-test baseline stays green. Two
corrections to the project's own framing: the WebSocket "groundwork" is dead
code, and ProjectType is currently global rather than tenant-scoped.
