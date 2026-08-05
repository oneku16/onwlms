# Backend Engineering Guide

## Purpose

This document is the authoritative backend engineering and implementation guide
for agents working on OwnSIS. It imports the company's Python and FastAPI
engineering standard from the FastAPI DDD template and applies it to the OwnSIS
backend. Treat the rules and examples as engineering conventions, not as a
completed product design.

## Scope

Follow these rules when adding or changing Python backend code under
`backend/src`, backend tests, persistence adapters, Alembic migrations, backend
container definitions, and Python project configuration. The guide preserves
Python 3.14, FastAPI, PostgreSQL, SQLAlchemy 2, Alembic, asynchronous I/O, `uv`,
Ruff, strict mypy, Domain-Driven Design, ports and adapters, and modular-monolith
conventions.

The guide governs backend implementation and engineering conventions. It does
not create a business feature, approve an API or database schema, select an
additional datastore, or redefine a module boundary.

## Responsibilities

Backend contributors and agents are responsible for following every applicable
rule in this guide, preserving stricter security and tenant-isolation
requirements, and verifying changes with the checks named in the completion
checklist. Reviewers are responsible for rejecting backend changes that violate
dependency direction, resource ownership, typing, migration safety, or boundary
rules even when the changed code appears to work.

## Documentation Authority

A direct human instruction has higher priority than repository documentation.
The repository documents then have distinct responsibilities:

- [`AGENTS.md`](../AGENTS.md) governs agent authorization, behavior, review, and
  approval stops across the repository.
- Accepted ADRs govern the architectural decisions within their recorded scope.
- [`docs/03_ARCHITECTURE.md`](03_ARCHITECTURE.md) governs system-level
  boundaries, data authority, tenancy, runtime shape, and allowed architectural
  evolution.
- This guide governs Python backend implementation and engineering conventions.
- [`docs/08_CODING_STANDARD.md`](08_CODING_STANDARD.md) governs general
  cross-stack coding quality and remains applicable where this backend-specific
  guide is silent.

A local feature convention may refine this guide only when it is compatible with
these authorities and at least as strict. When documents conflict, stop and
surface the conflict; do not silently select the more convenient rule.

## OwnSIS Invariants

- OwnSIS remains one versioned modular-monolith application and release boundary
  unless an accepted ADR authorizes a different architectural boundary.
- Each backend feature module preserves the `domain`, `application`,
  `infrastructure`, and `presentation` dependency direction.
- Each organization is one tenant. Tenant-owned operations, repositories,
  events, caches, jobs, integrations, and tests preserve verified organization
  context and fail closed when that context is absent or inconsistent.
- OwnID is the sole identity provider and the only authority for human
  authentication. OwnSIS owns organization membership, permissions, and
  authorization.
- Moodle owns learning delivery only. MCP-based AI remains a governed,
  permission-aware integration. Neither may bypass OwnSIS application and
  domain rules.
- Names, routes, persistence models, constraints, and Redis or SQLite adapters
  shown in examples illustrate coding conventions only. They are not approved
  OwnSIS modules, APIs, schemas, dependencies, or infrastructure. Adopting a new
  dependency or datastore still requires the review and approval required by
  [`AGENTS.md`](../AGENTS.md) and the architecture documents.

## title: architectural style

```text
backend/src/
├── <feature>/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── presentation/
├── core/
└── shared/
```

description/explanation:

Build a typed asynchronous modular monolith with DDD and ports-and-adapters
boundaries. Organize business capabilities as feature modules rather than by
framework type alone.

- `domain` contains business concepts, rules, value objects, and domain errors.
- `application` contains use cases and orchestration services.
- `infrastructure` implements persistence and external-service adapters.
- `presentation` contains FastAPI routers and HTTP translation.
- `core` contains application-wide primitives and contracts.
- `shared` contains genuinely reusable technical infrastructure.

Dependencies point inward. Presentation and infrastructure may depend on
application/domain contracts. Domain and application code must not depend on
FastAPI, Redis, SQLAlchemy models, or a vendor SDK.

Do not place new feature-specific behavior in `shared` merely because more than
one file uses it. Move code to `shared` only when it represents a stable,
cross-feature abstraction.

Within OwnSIS, both `core` and `shared` remain subject to the small
shared-kernel rule. Neither location may contain feature-specific domain
behavior, provide access to another module's persistence, or become an escape
from explicit module contracts.

## title: feature module structure

```text
backend/src/<feature>/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── models.py
│   └── exceptions.py
├── application/
│   ├── __init__.py
│   ├── ports.py
│   └── service.py
├── infrastructure/
│   ├── __init__.py
│   ├── models.py
│   └── repository.py
└── presentation/
    ├── __init__.py
    └── router.py
```

description/explanation:

Use this layout for substantial new capabilities. Small modules may begin with
fewer files, but their dependency direction must remain the same. Split files by
responsibility when a module starts mixing business rules, HTTP concerns, and
technical implementations.

## title: module and package naming

```text
auth/
database_settings.py
redis_session_repository.py
test_auth_flows.py
```

description/explanation:

Use lowercase `snake_case` for modules, packages, and filenames. Prefer concrete
names that identify the business or technical responsibility. Avoid vague names
such as `utils.py`, `helpers.py`, `common.py`, or `manager.py` when a more precise
name is available.

Test modules use `test_<subject>.py` or `test_<workflow>.py`.

## title: class naming

```python
class AuthenticationService:
    ...


class SessionRepository(Protocol):
    ...


class RedisSessionRepository:
    ...


class ApplicationUserModel:
    ...


class OwnIDSettings(BaseSettings):
    ...
```

description/explanation:

Use `PascalCase`. The suffix communicates the class's architectural role.

- Application orchestrators end in `Service`.
- Repository contracts use the role name, such as `SessionRepository`.
- Adapters include their technology, such as `RedisSessionRepository`.
- SQLAlchemy persistence entities end in `Model`.
- Environment configuration classes end in `Settings`.
- Reusable model behavior ends in `Mixin`.
- Exceptions end in `Error`.
- Test doubles begin with `Fake` when they contain working behavior.

Do not prefix protocols with `I`, and do not use generic suffixes such as
`Manager` when `Service`, `Repository`, `Provider`, or `Resolver` is accurate.

## title: function and method naming

```python
async def complete_authorization(
    self,
    session_id: str,
    code: str,
    state: str,
) -> AuthenticatedIdentity:
    """Complete the authorization flow and return the verified identity."""
```

description/explanation:

Use `snake_case` verb phrases that describe the operation and outcome. Examples
include `start_login`, `resolve_or_create`, `get_current_user`, and
`create_session_repository`.

Use `async def` for database, network, Redis, filesystem, and other asynchronous
I/O. Do not mark purely computational functions async.

Prefix implementation-only helpers with `_`. Do not expose a helper merely to
make it easier to test; test behavior through the public boundary when possible.

## title: function signatures

Do not:

```python
def calculate(a, b, c):
    return a + b + c
```

Do:

```python
def calculate_total(
    subtotal: int,
    tax: int,
    discount: int,
) -> int:
    """Calculate the final total after tax and discount."""

    total = subtotal + tax - discount
    return total
```

description/explanation:

Every production function and method must have parameter and return type
annotations. When a function accepts multiple parameters, put one parameter per
line and include a trailing comma. Use keyword-only parameters for options that
would be ambiguous positionally.

Give production functions and methods a concise docstring explaining their
contract. Test names normally document test functions, so test docstrings are
optional. Comments and docstrings should explain intent, constraints, ownership,
or security decisions rather than narrating obvious statements.

## title: import style

Do not:

```python
from backend.src.auth.domain.models import ApplicationUser, SessionRecord
```

```python
from backend.src.auth.domain.models import (
    ApplicationUser,
    SessionRecord,
)
```

Do:

```python
from backend.src.auth.domain.models import ApplicationUser
from backend.src.auth.domain.models import SessionRecord
```

description/explanation:

Import one symbol per line. Separate standard-library, third-party, and local
application imports with a blank line. Let Ruff order imports.

Use absolute imports across architectural boundaries. Relative imports are
acceptable only within the same small package when they improve clarity. Never
use wildcard imports.

Place `from __future__ import annotations` immediately after the module docstring
when postponed annotations are needed.

## title: type annotations

```python
async def get(
    self,
    session_id: str,
) -> SessionRecord | None:
    """Return a session when it exists and remains valid."""
```

description/explanation:

Treat strict typing as part of the design.

- Use `T | None` instead of `Optional[T]`.
- Use built-in generics such as `list[str]` and `dict[str, object]`.
- Give functions explicit return types, including `-> None`.
- Use `Annotated` for FastAPI dependency values.
- Use `Protocol` for ports and replaceable collaborators.
- Avoid `Any`; isolate it at untyped vendor boundaries when unavoidable.
- Do not use `# type: ignore` without a narrow error code and a real reason.
- Preserve strict mypy compliance.

## title: domain data classes

```python
@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    issuer: str
    subject: str
    email: str | None = None
    name: str | None = None
```

description/explanation:

Use dataclasses for framework-independent business values and application
results. Prefer `frozen=True, slots=True` for immutable values. Use mutable
dataclasses only when the object represents intentionally changing state, such
as a server-side session record.

Do not pass SQLAlchemy models or FastAPI request/response models through the
domain layer when a small domain value can represent the contract.

The identity value above illustrates immutable dataclass style; it does not
define the complete OwnSIS user, membership, or tenant model. A production value
used for tenant-owned work must be bound to verified organization context in the
owning application contract.

## title: ports and adapters

```python
class ApplicationUserResolver(Protocol):
    async def resolve_or_create(
        self,
        *,
        issuer: str,
        subject: str,
        profile: UserProfile,
    ) -> ApplicationUser:
        """Resolve the application user or create it atomically."""
        ...
```

```python
class SQLAlchemyApplicationUserResolver:
    async def resolve_or_create(
        self,
        *,
        issuer: str,
        subject: str,
        profile: UserProfile,
    ) -> ApplicationUser:
        ...
```

description/explanation:

Define replaceable dependencies as protocols in the core or application layer.
Implement those protocols in infrastructure without making the implementation
inherit from the protocol.

The protocol describes behavior, not the storage technology. Implementations
must preserve the same semantic guarantees, including atomicity, expiration,
locking, and error behavior.

The resolver name and behavior in this example demonstrate a port shape; they do
not authorize automatic user provisioning or define an OwnSIS membership
lifecycle. Those behaviors require validated domain requirements.

## title: service layer

```python
class AuthenticationService:
    def __init__(
        self,
        identity_provider: IdentityProvider,
        sessions: SessionRepository,
        users: ApplicationUserResolver,
    ) -> None:
        self._identity_provider = identity_provider
        self._sessions = sessions
        self._users = users
```

description/explanation:

Application services orchestrate use cases. Inject collaborators through the
constructor and store them in private attributes.

Services may depend on domain models and ports. They must not know about FastAPI
requests, HTTP responses, Redis command syntax, SQLAlchemy persistence models,
or vendor SDK response objects.

Keep business transactions and security-sensitive workflow decisions in the
service rather than in routers.

## title: dependency injection

```python
app = create_app(
    identity_provider=fake_provider,
    session_repository=sessions,
    user_resolver=users,
)
```

description/explanation:

Use constructor injection for application services and FastAPI dependency
injection at the HTTP boundary. `create_app` is the composition root: it creates
production adapters by default and accepts explicit replacements for tests.

Do not construct Redis clients, database engines, SDK clients, or repositories
inside route handlers. Do not hide dependencies in mutable module globals when
they require lifecycle management.

## title: FastAPI dependency aliases

```python
CurrentUserDep = Annotated[
    CurrentUser,
    Depends(require_current_user),
]
```

description/explanation:

Create meaningful `Annotated` aliases for dependencies repeated across routes.
Names describe the value received by the route and end in `Dep` when that makes
their dependency role clearer.

## title: application factory

```python
def create_app(
    *,
    identity_provider: IdentityProvider | None = None,
    session_repository: SessionRepository | None = None,
    user_resolver: ApplicationUserResolver | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
```

description/explanation:

Construct the FastAPI application through a factory. Keep a module-level
`app = create_app()` only as the ASGI server entry point.

Factory overrides are intentional test seams. Keep them typed by protocols and
avoid environment-specific branching in route modules.

Importing the module-level ASGI entry point must not perform hidden network I/O.
Defer resource connection and other startup effects to the application lifespan.

## title: resource ownership and lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own and close process-scoped application resources."""

    try:
        yield
    finally:
        await redis_client.aclose()
        await database_engine.dispose()
```

description/explanation:

Create process-scoped resources during application composition or startup and
close owned resources during lifespan shutdown. Track whether the application
created a resource; injected resources remain owned by their caller.

Make initialization idempotent when both the application factory and lifespan
may invoke the same configuration function.

## title: presentation layer

```python
@router.get("/me")
async def me(
    user: CurrentUserDep,
) -> Response:
    """Return the currently authenticated user."""

    return JSONResponse(content=_safe_user_payload(user))
```

description/explanation:

Keep routes thin. A route may:

- Parse and validate HTTP input.
- Call one or more application use cases.
- Translate application errors into stable HTTP responses.
- Set or clear cookies and headers.
- Serialize an explicit safe response payload.

A route must not contain database queries, Redis operations, vendor SDK calls,
or substantial business workflows.

Every feature presentation package exposes a module-level `router` created with
an explicit prefix and tags.

## title: configuration classes

```python
class OwnIDSettings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True)

    OWNID_SESSION_COOKIE_NAME: str = "ownsis_session"
    OWNID_COOKIE_SECURE: bool = True
```

description/explanation:

Create one settings class per concern. Environment-backed fields use uppercase
names that match environment variables. Provide safe defaults for local use and
secure defaults for production-sensitive behavior.

Expose parsed or derived forms through read-only properties such as `url`,
`scopes`, or `redirect_allowlist`. Validate incompatible settings as early as
possible and return actionable error messages without including secrets.

## title: settings exports

```python
ownid_settings: OwnIDSettings = OwnIDSettings()

__all__ = [
    "OwnIDSettings",
    "ownid_settings",
]
```

description/explanation:

Export both the settings type and its process-scoped instance. Use the type when
tests need isolated configuration and the singleton for normal application
composition.

The exported process-scoped instance is immutable and may be read by the
composition root. It is not a mutable global, a service locator, or permission
for feature code to hide dependencies. Pass settings or derived values through
explicit construction when a collaborator needs them.

Use double quotes consistently in new `__all__` declarations and other string
literals unless a different quote avoids escaping.

## title: factory functions

```python
def create_session_repository(
    *,
    backend: str | None = None,
    redis_client: Redis | None = None,
) -> tuple[SessionRepository, Redis | None]:
    """Build the configured session repository and report owned resources."""
```

description/explanation:

Use explicitly named `create_*` functions for adapter construction. A factory
may select an implementation from settings, but it returns objects typed by
their ports.

A factory may select only implementations already approved for OwnSIS. A
configuration option does not itself approve a new dependency, datastore, or
external service.

If construction creates a resource that must be closed, return or register its
ownership explicitly rather than relying on implicit cleanup.

## title: database model naming

```python
class ApplicationUserModel(TimestampMixin, UUIDBase):
    __tablename__ = "application_users"
```

description/explanation:

SQLAlchemy classes use singular `PascalCase` names ending in `Model`. Table names
use plural `snake_case`. Cross-cutting columns belong in focused mixins or an
abstract base.

Use SQLAlchemy 2 typed declarative mappings with `Mapped[T]` and
`mapped_column`. Python optionality and database nullability must agree.

## title: identifiers

```python
class UUIDBase(BaseModel):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        nullable=False,
    )
```

description/explanation:

Use UUIDv7 identifiers for persistent entities unless the domain requires a
different identifier. When a public readable identifier is needed, derive it
from a model-specific `UID_PREFIX`; do not introduce a second identity without
a domain reason.

## title: database constraints

```python
__table_args__ = (
    UniqueConstraint(
        "issuer",
        "subject",
        name="uq_application_users_issuer_subject",
    ),
)
```

description/explanation:

Enforce business uniqueness and integrity in the database, not only in Python.
Name constraints predictably using the table and columns. Application code must
still handle the expected integrity race safely.

The example demonstrates constraint naming and concurrency protection, not an
approved OwnSIS user schema. Tenant-owned uniqueness must include or otherwise
enforce the organization boundary required by the approved domain model.

## title: transaction handling

```python
try:
    await session.commit()
except IntegrityError:
    await session.rollback()
    model = await self._find(
        session,
        issuer=issuer,
        subject=subject,
    )
```

description/explanation:

Make commit, rollback, and refresh behavior explicit. Handle expected concurrent
creation through database constraints and a recovery path. Do not use a
check-then-insert sequence as the only uniqueness protection.

Dependency-managed sessions must roll back when an exception escapes.

## title: safe model serialization

```python
SERIALIZE_FIELDS = (
    "id",
    "issuer",
    "subject",
    "email",
    "name",
)
```

description/explanation:

Serialization is opt-in. Expose only fields listed in `SERIALIZE_FIELDS` or an
explicit response mapper. Never serialize every ORM column automatically.

Keep `__repr__` minimal and safe. It may include the class and identifier but
must not dump tokens, credentials, claims, personal data, or complete model
state.

## title: exception hierarchy

```python
class AppError(BaseError):
    """Base class for expected application failures."""


class AuthError(AppError):
    """Base class for authentication failures."""


class InvalidSessionError(AuthError):
    """Raised when an application session cannot be used."""
```

description/explanation:

Create a shallow hierarchy from general application failures to feature-level
and specific errors. Internal code raises precise exceptions. Presentation code
catches a stable parent when several internal failures share one public result.

Use `raise PublicError(...) from exc` when translating an exception so the
internal cause remains available for debugging.

## title: HTTP error translation

```python
try:
    user = await auth.get_current_user(session_id)
except AuthError as exc:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    ) from exc
```

description/explanation:

Domain and application layers do not raise `HTTPException`. Translate expected
application errors at the presentation boundary. Keep public messages stable and
avoid revealing sensitive failure details.

## title: security-sensitive comparison

```python
def _secure_equals(
    left: str,
    right: str,
) -> bool:
    """Compare secret values in constant time without propagating type errors."""

    try:
        return secrets.compare_digest(left, right)
    except (TypeError, ValueError):
        return False
```

description/explanation:

Use constant-time comparison for CSRF values, OAuth state, nonces, signatures,
and similar secret material. Reject malformed values instead of falling back to
ordinary equality.

## title: authentication security

```python
response.set_cookie(
    key=ownid_settings.OWNID_SESSION_COOKIE_NAME,
    value=session_id,
    httponly=True,
    secure=ownid_settings.OWNID_COOKIE_SECURE,
    samesite="lax",
    path="/",
)
```

description/explanation:

Preserve these security properties when implementing authentication:

- Store access, refresh, and ID tokens only in server-side sessions.
- Rotate the application session identifier after login.
- Use OAuth state, nonce, and PKCE and consume pending state once.
- Use explicit redirect allowlists and reject absolute or traversal paths.
- Protect state-changing cookie-authenticated requests with CSRF validation.
- Use HttpOnly cookies for session identifiers.
- Return `Cache-Control: no-store` for authentication responses.
- Serialize user responses explicitly and never expose stored token fields.
- Make logout and token revocation safe under partial provider failure.

Security behavior is part of the feature contract. Do not remove it merely to
simplify an implementation or test.

In OwnSIS production, the human identity adapter behind an
`IdentityProvider` port is OwnID and no other provider. The port exists to
isolate infrastructure and allow controlled test doubles; it is not a
configuration point for an alternative production identity provider. Before a
protected operation, the application must bind the verified OwnID subject to the
current OwnSIS organization membership and authorization context.

## title: repository concurrency

```python
async with self._sessions.refresh_lock(session_id):
    await self._identity_provider.refresh(session_id)
```

description/explanation:

Represent concurrency guarantees in repository ports. Every adapter must honor
the same semantics. Use in-process locks only for single-process adapters. Use a
distributed lock or atomic storage operation for multi-worker deployments.

Use transactions or Redis Lua scripts when multiple reads and writes must be one
atomic operation. Document lock timeout and ownership behavior.

## title: datetime handling

```python
def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""

    return datetime.now(UTC)
```

description/explanation:

Use timezone-aware UTC datetimes. Centralize the clock behind a small helper so
time handling is consistent and can be replaced in tests if needed. Do not use
naive `datetime.now()` or `datetime.utcnow()` values.

## title: model registry and migrations

```python
load_all_models()
target_metadata = BaseModel.metadata
```

description/explanation:

Put SQLAlchemy entities in modules named `models.py` so the registry can discover
them before Alembic reads metadata. Every schema change requires an Alembic
migration with working `upgrade` and `downgrade` functions.

Review generated migrations. Keep revision identifiers stable and give indexes,
foreign keys, and unique constraints deterministic names.

A downgrade must reverse every safely reversible schema effect. When reversal is
inherently unsafe or irreversible, the function must fail explicitly with an
actionable reason and direct operators to the approved forward-recovery or
restore procedure; it must never no-op or claim to restore discarded data. The
downgrade function does not substitute for the staged compatibility, backup, and
forward-recovery plan required by
[`docs/08_CODING_STANDARD.md`](08_CODING_STANDARD.md) for destructive or
irreversible changes.

## title: public module API

```python
__all__ = [
    "AuthenticationService",
]
```

description/explanation:

Declare the intended public API of production modules with `__all__`. Export
stable types, factories, and constants. Keep helpers private with leading
underscores and exclude them from `__all__`.

Package `__init__.py` files may re-export a small curated API. Do not turn them
into dumping grounds for every implementation class.

In this section, “public API” means the supported Python import surface of a
module. It does not define or authorize an external OwnSIS HTTP or integration
API. An `__all__` declaration alone also does not establish an approved
cross-module contract; module ownership and architecture rules still apply.

## title: test location and naming

```text
backend/tests/
└── auth/
    ├── conftest.py
    ├── test_auth_flows.py
    ├── test_redis_sessions.py
    └── test_settings_providers.py
```

```python
async def test_successful_callback_creates_session_without_token_leak(
    client: AsyncClient,
) -> None:
    ...
```

description/explanation:

Keep backend tests under `backend/tests`, grouped by feature. Name tests
`test_<observable_behavior>`. A reader should understand the requirement from
the test name without opening the implementation.

Test successful behavior, invalid input, error translation, concurrency,
expiration, replay prevention, configuration variants, and security invariants.
Do not test only the happy path.

## title: test doubles

```python
class FakeIdentityProvider:
    async def complete_authorization(
        self,
        session_id: str,
        code: str,
        state: str,
    ) -> AuthenticatedIdentity:
        ...
```

description/explanation:

Replace external systems at protocol boundaries. Prefer small functional fakes,
in-memory adapters, SQLite, and fakeredis over mocks of internal implementation
calls.

Use a fake when it implements meaningful behavior and records interactions. Use
a stub only for fixed responses. Mock a third-party boundary only when a fake or
test adapter would be disproportionately expensive.

SQLite and fakeredis are illustrative test adapters, not approved production
dependencies. Use SQLite only when the tested behavior is demonstrably
database-agnostic. Use fakeredis only when a Redis adapter has been separately
approved, and retain real-adapter coverage for semantics the fake cannot
reproduce. Tests of PostgreSQL constraints, transactions, locking, query
behavior, tenant isolation, or Alembic migrations must run against PostgreSQL
rather than assuming SQLite has equivalent semantics.

## title: HTTP testing

```python
transport = ASGITransport(app=app)

async with AsyncClient(
    transport=transport,
    base_url="http://test",
) as client:
    yield client
```

description/explanation:

Test FastAPI through its ASGI interface. This verifies routing, dependency
injection, cookies, headers, serialization, and error translation without opening
a real network port.

Inject fake ports through `create_app`; do not monkeypatch deep application
internals when an explicit injection point exists.

Tests that cover startup, shutdown, or process-scoped resources must enter the
FastAPI lifespan explicitly; an ASGI transport alone is not assumed to run
lifecycle hooks.

## title: test isolation

```python
@pytest.fixture
def sessions() -> InMemorySessionRepository:
    return InMemorySessionRepository()
```

description/explanation:

Create fresh mutable adapters for each test. Tests must not depend on execution
order or shared state. Close temporary engines and clients explicitly. Use
function-scoped async fixtures unless broader scope is required and documented.

## title: deployment style

```dockerfile
FROM python:3.14-slim-bookworm AS builder
...
FROM python:3.14-slim-bookworm AS runtime
...
USER appuser
```

description/explanation:

Development images include tests, development dependencies, and editable OwnSIS
workspace packages. Production images use multi-stage builds, locked runtime
dependencies, selected application files, and a non-root user.

Do not copy tests, local dotenv files, caches, build tools, or source checkouts
into the final runtime image. Keep local PostgreSQL and any separately approved
optional service behind Compose profiles so hosted providers can use the same
application image.

## title: dependency management

```toml
[dependency-groups]
dev = [
    "mypy",
    "pytest",
    "ruff",
]
```

description/explanation:

Use `uv` and keep the lockfile synchronized. Runtime packages belong in
`project.dependencies`; testing and analysis tools belong in the development
group. Local editable OwnSIS packages are development workspace conveniences
and must be published or otherwise made reproducible before deployment.

Do not introduce an additional package manager for the Python application.

## title: linting and formatting

```toml
[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

description/explanation:

New and modified code must pass Ruff. Do not manually fight Ruff's import order.
Prefer readable expressions over suppressions. When a suppression is unavoidable,
scope it to the smallest line and include the specific rule code.

## title: static typing

```toml
[tool.mypy]
python_version = "3.14"
strict = true
```

description/explanation:

New and modified production code must pass strict mypy. Do not weaken global
configuration to make one implementation pass. Isolate untyped third-party
libraries through narrow overrides or typed adapters.

## title: comments and docstrings

```python
# Consume state before exchanging the code so callback replay fails.
session.oauth_state = None
```

description/explanation:

Explain why a decision exists, especially around security, concurrency,
transactions, lifecycle, and external-provider behavior. Do not add comments
that merely restate the next line.

Use concise imperative comments. Keep docstrings focused on contracts,
side effects, ownership, raised errors, and limitations.

## title: agent implementation workflow

```text
1. Inspect the affected feature and its tests.
2. Identify the domain/application boundary and the required port.
3. Implement the smallest coherent change.
4. Add or update behavioral tests.
5. Run pytest, Ruff, and strict mypy.
6. Validate migrations or container configuration when affected.
7. Report changed behavior and any validation limitation.
```

description/explanation:

Agents must preserve existing behavior outside the requested scope. Do not make
unrelated architectural rewrites while fixing a local issue. Reuse existing
ports, factories, settings, and test fixtures before creating parallel
abstractions.

Before declaring work complete, verify the relevant behavior rather than relying
only on static inspection.

## title: agent completion checklist

```text
[ ] Feature code is in the correct architectural layer.
[ ] Dependency direction points inward.
[ ] Names communicate architectural responsibility.
[ ] Imports use one symbol per line.
[ ] Production functions and methods are fully typed.
[ ] Public contracts and non-obvious behavior are documented.
[ ] External systems are accessed through ports/adapters.
[ ] Routes remain thin.
[ ] Resources have explicit ownership and cleanup.
[ ] Errors are translated only at boundaries.
[ ] Sensitive data is not logged or serialized.
[ ] Database integrity is enforced with constraints and transactions.
[ ] Tests describe observable behavior and important failure cases.
[ ] pytest passes.
[ ] Ruff passes.
[ ] strict mypy passes.
[ ] Migrations and Compose/Docker configuration are validated when changed.
```

description/explanation:

An agent should use this checklist before handing work back. If a check cannot be
performed because an external service or local daemon is unavailable, report the
exact limitation instead of describing the work as fully verified.

## Assumptions

- Backend source remains rooted at `backend/src`, and backend tests remain
  rooted at `backend/tests`.
- Python 3.14, FastAPI, PostgreSQL, SQLAlchemy 2, Alembic, asynchronous I/O,
  `uv`, Ruff, and strict mypy remain the approved backend baseline.
- Feature modules use `domain`, `application`, `infrastructure`, and
  `presentation` boundaries inside the modular monolith.
- Architecture, domain, security, and tenancy decisions are established by their
  governing OwnSIS documents before implementation conventions are applied.
- Examples remain illustrative until a validated requirement and approved design
  give them product meaning.

## Future Evolution

This guide evolves when the company backend standard changes or production
evidence justifies a stricter OwnSIS convention. Revisions must preserve the
guide's security, testing, lifecycle, concurrency, migration, serialization,
typing, resource-ownership, and dependency-direction guarantees.

A revision that changes a system boundary, data authority, deployment topology,
or accepted architectural decision requires the corresponding architecture
documentation and ADR process. Backend implementation and engineering-convention
changes remain documented here and must be reflected in repository tooling so
Ruff, strict mypy, tests, migration checks, and container validation continue to
enforce the written standard.

This guide may be split into focused documents when its size creates real
navigation or maintenance problems. The frontend should receive its own
engineering guide when frontend implementation begins. Documentation should
grow in response to real implementation needs rather than speculative
structure. This note is non-binding and does not authorize empty documents or
directories.
