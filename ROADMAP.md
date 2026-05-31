# ROADMAP — Evolving TaskBoard into a multi-domain work platform

This document describes where TaskBoard is going and how to drive Claude Code
to build it. It is meant to be committed to the repo and used as the source of
truth for planned work. Each phase is a reviewable, shippable slice with its own
Claude Code prompt.

---

## 1. Product direction

Today TaskBoard manages one kind of thing (a task) for one user. The goal is a
platform where teams manage **any kind of work** — software tasks, translation
jobs, support tickets, onboarding checklists — without writing new code per
domain.

The enabling idea: **a generic work-item with a domain-specific shape.**

```
Organization (tenant)
  └── Membership (user ⇄ org, with a role)
        └── Project  (belongs to an org, has a ProjectType)
              └── Task (the work item: typed core fields + validated custom_fields)

ProjectType  → declares the custom-field schema + the status workflow
               (e.g. "Software Tasks", "Translation Jobs", "Generic Work")
```

- **Core fields** every task has: title, status, assignee, due date, timestamps.
- **Custom fields** come from the project's type and live in a validated
  `JSONField` (e.g. a translation job adds `source_lang`, `target_lang`,
  `word_count`; a software task adds `priority`, `component`).
- **Statuses/workflow** are defined per project type, not hard-coded.

This keeps one model and one set of views/endpoints while supporting unlimited
domains. Prefer this over one model per work type unless a single domain becomes
heavy enough to justify its own table.

### Key early decisions (make these before Phase 1)
1. **Keep the model name `Task`** as the generic work item (low churn), rather
   than renaming to `WorkItem`. "Task" reads fine for any domain.
2. **Custom fields = `JSONField` validated against the project type's schema.**
   Validation happens in the form and serializer, not in the database.
3. **Tenancy scoping replaces owner-scoping.** "You see your own tasks" becomes
   "you see tasks in projects inside orgs you belong to," filtered by role.
4. **Project types ship as seeded templates** (data migration / fixture), and
   can later become org-editable.

---

## 2. How to work with Claude Code

Follow this loop for every phase. It is what keeps an ambitious build from
drifting.

**Per phase:**
1. Start the session by pointing Claude Code at `CLAUDE.md` and this file.
2. For any phase touching the data model, ask for a **short written plan
   first** (models, migrations, endpoints, test list). Approve it before code.
3. Work on a **feature branch**, one phase per PR.
4. Definition of done — the agent must verify all of these before claiming
   completion:
   - `pytest` is green (new tests added for new behaviour)
   - `python manage.py makemigrations` produces no unexpected changes
   - `python manage.py check` passes
   - `CLAUDE.md` is updated to reflect the new architecture
5. Review the diff. If it grew beyond the phase scope, ask it to split.

**Standing rules to remind it of (already in CLAUDE.md):**
- Acceptance criteria over implementation detail — let it design, you approve.
- Catch specific exceptions; use `logging`, not `print`.
- Never hand-edit an applied migration; generate a new one.
- Don't add dependencies or layers that don't clearly earn their place.
- Migrate existing data — every schema change needs a data migration so the
  current database keeps working.

**Anti-patterns to avoid:**
- "Build the whole platform" in one prompt.
- Letting a phase land without tests "to save time."
- Big speculative abstractions before a second domain actually needs them.

---

## 3. Phased plan with prompts

Each prompt is written to paste directly into Claude Code. Adjust wording to
taste; keep the acceptance criteria.

### Phase 1 — Organizations & membership (multi-tenancy core)

> Read `CLAUDE.md` and `ROADMAP.md` first. Implement Phase 1.
>
> Goal: introduce multi-tenancy. Add an `Organization` model and a `Membership`
> model linking `User` to `Organization` with a `role` field
> (`owner`, `admin`, `member`, `viewer`). A user can belong to several orgs and
> has one "active" org in the session.
>
> Requirements:
> - On signup, create a personal organization and make the user its owner.
> - Add an org switcher in the navigation; store the active org in the session.
> - Add a data migration that creates an organization for every existing user
>   and migrates their data into it.
> - Add permission helpers (e.g. `require_role`) for use in views.
>
> Acceptance: tests cover org creation on signup, membership roles, and the
> active-org switch. `pytest` green, migrations clean, `check` passes,
> `CLAUDE.md` updated. Do not touch the `Task` model yet beyond what's needed to
> attach it to an org in Phase 2.

### Phase 2 — Projects, and scoping tasks to them

> Implement Phase 2. Add a `Project` model belonging to an `Organization`.
> Move `Task` under a `Project` (FK `task.project`). Replace owner-scoping with
> membership-scoping: a user sees tasks in projects within orgs they belong to,
> filtered by role (viewers read-only).
>
> Requirements:
> - Data migration: create a default "General" project per existing org and
>   attach existing tasks to it.
> - Project list/detail pages; task list is now filtered by the selected project.
> - Update the REST API to be org/project scoped.
>
> Acceptance: scoping is enforced in both the web views and the API (a user
> cannot read or write another org's tasks — add tests for the negative case).
> `pytest` green, migrations clean, `check` passes, `CLAUDE.md` updated.

### Phase 3 — Project types & custom fields (the core capability)

> Implement Phase 3 — this is the key feature. Add a `ProjectType` that declares
> a custom-field schema, and store per-task custom data in a validated
> `JSONField` on `Task`.
>
> Design:
> - `ProjectType` has a name and a list of `FieldDefinition`s (name, label,
>   field type from a fixed enum: text/number/date/choice/boolean, required
>   flag, choices for `choice`).
> - `Project.project_type` selects the type.
> - `Task.custom_fields` is a `JSONField`; validate it (in the form AND the DRF
>   serializer) against the project's type schema — reject unknown keys, enforce
>   required fields and types.
> - Seed two project types via data migration: "Software Tasks"
>   (priority: choice, component: text) and "Translation Jobs"
>   (source_lang: text, target_lang: text, word_count: number, deadline: date).
> - Task create/edit forms render custom fields dynamically from the schema.
>
> Acceptance: creating a task under each seeded type works end to end (web + API),
> validation rejects bad/missing/unknown custom fields, and switching a project's
> type is handled sanely. Strong test coverage on the validation logic.
> `pytest` green, migrations clean, `check` passes, `CLAUDE.md` updated.

### Phase 4 — Configurable status workflows

> Implement Phase 4. Move task status from a hard-coded value to a workflow
> defined by the `ProjectType` (an ordered list of statuses). Validate that a
> task's status is one of its project type's statuses, and optionally restrict
> transitions. Seed sensible workflows for the two existing types.
>
> Acceptance: status options are driven by the project type in the UI and API;
> invalid statuses are rejected. Tests cover allowed/disallowed statuses.
> `pytest` green, migrations clean, `check` passes, `CLAUDE.md` updated.

### Phase 5 — Collaboration: comments, activity log, attachments

> Implement Phase 5. Add `Comment` (user, task, body, created) and an append-only
> `Activity` log that records task create/update/status-change/assignment events.
> Optionally add file attachments on tasks. Surface comments and activity on the
> task detail page.
>
> Acceptance: activity is recorded automatically on the relevant events (test
> this), comments are scoped to project members. `pytest` green, migrations
> clean, `check` passes, `CLAUDE.md` updated.

### Phase 6 — Data import ("messy data in, working board out")

> Implement Phase 6. Add a CSV/XLSX importer: the user uploads a file, maps its
> columns to the target project type's core + custom fields, previews the parsed
> rows with validation errors highlighted, then commits the import. Reuse the
> Phase 3 validation. Use a well-maintained library for parsing; keep the mapping
> logic testable and side-effect free until commit.
>
> Acceptance: a sample CSV imports into a project as valid tasks; invalid rows
> are reported, not silently dropped. Tests cover parsing, mapping, and the
> validation path. `pytest` green, migrations clean, `check` passes,
> `CLAUDE.md` updated.

### Phase 7 — API hardening

> Implement Phase 7. Add token authentication for the API, plus filtering,
> ordering, and pagination on the task endpoints. Generate an OpenAPI schema and
> serve interactive docs. Ensure all endpoints remain org/project scoped.
>
> Acceptance: token auth works, listing supports filter/order/paginate, schema
> is generated and documented. Tests cover auth and scoping. `pytest` green,
> migrations clean, `check` passes, `CLAUDE.md` updated.

### Phase 8 — Notifications & email

> Implement Phase 8. Build on the existing email setup to notify assignees on
> assignment and on comments/status changes, with per-user notification
> preferences. Keep the console backend as the dev default.
>
> Acceptance: notifications fire on the right events and respect preferences
> (test with the locmem/console backend). `pytest` green, migrations clean,
> `check` passes, `CLAUDE.md` updated.

### Phase 9 — Dashboards & saved views

> Implement Phase 9. Add per-project saved filters/views and a simple dashboard
> (counts by status, overdue, recent activity) scoped to the active org.
>
> Acceptance: saved views persist and reload correctly; dashboard numbers match
> the underlying data (test the aggregation). `pytest` green, migrations clean,
> `check` passes, `CLAUDE.md` updated.

### Phase 10 — Production readiness

> Implement Phase 10. Add a Postgres configuration path (keep SQLite for dev),
> a Dockerfile + compose for local Postgres, a settings split or env-based
> config for prod, static file handling, and a CI workflow that runs
> `pytest` and `manage.py check --deploy`.
>
> Acceptance: `docker compose up` runs the app against Postgres; CI is green on
> a clean checkout. `CLAUDE.md` updated with the new run/deploy instructions.

---

## 4. Suggested order & dependencies

Phases 1 → 2 → 3 are the backbone and must go in order. 4 depends on 3. After
that, 5–9 are largely independent and can be reordered by priority; 10 can begin
in parallel once the model has stabilized (after Phase 3). Ship each as its own
PR and keep `CLAUDE.md` current as you go — that file is what keeps every future
Claude Code session aligned with the architecture you've built.
