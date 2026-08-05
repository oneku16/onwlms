# OwnSIS frontend

The OwnSIS portal is a Next.js application for platform administrators,
organization members, students, teachers, guardians, staff, and guests. It uses
the backend as the authority for authentication, tenant membership,
authorization, entitlements, validation, and scheduling conflicts.

## Local development

Requirements: Node.js 24 or newer and npm 11 or newer.

```sh
cp .env.example .env.local
npm ci
npm run dev
```

`BACKEND_URL` is a server-only backend origin. Browser requests use the
same-origin `/api/v1` proxy; do not expose the backend origin through a
`NEXT_PUBLIC_` variable.

Run all frontend checks with:

```sh
npm run validate
```

## Authentication and tenant context

- OwnID login begins with `POST /api/v1/auth/login` and the browser follows the
  returned authorization URL.
- The server renders identity from `/api/v1/auth/me`, discovers active tenant
  memberships from `/api/v1/auth/memberships`, and validates organization
  details with an `X-Organization-ID` request.
- The active organization is stored only as an HttpOnly organization identifier
  after the switch endpoint revalidates membership. It is not an authorization
  grant.
- Cookie-authenticated writes read the `ownsis_csrf` cookie at action time and
  send its value as `X-CSRF-Token`. Access, refresh, and ID tokens never enter
  browser storage.

## TypeScript toolchain

Application type checking runs the TypeScript 7 native CLI. Next.js still needs
a programmatic compiler API for framework-generated types, so the official
TypeScript 6 compatibility package is installed side-by-side and used only by
Next's build phase. `npm run build` always runs the strict TypeScript 7 check
first.

## API types

Runtime adapters deliberately normalize only the response fields rendered by
the portal. The backend OpenAPI document and
`lib/api/generated/openapi.ts` are checked-in, machine-owned contract artifacts.
Regenerate both from the repository root after changing a route or API schema:

```sh
make openapi
```

`make openapi-check` verifies both artifacts without changing them. Generation
uses a separately locked OpenAPI CLI toolchain, keeping its TypeScript 5 peer
isolated from the application's TypeScript 6 compatibility and TypeScript 7
native compilers.

## Deliberately unavailable areas

Guardian attendance is disabled until an attendance API exists. Guardian
payments are disabled because this release has no finance model. Other portal
collections surface backend `404`, permission, validation, and service errors
explicitly when their corresponding first-release read endpoint is not yet
available; the frontend does not fabricate records.
