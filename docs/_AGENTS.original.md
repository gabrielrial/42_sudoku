# AGENTS.md — Sudoku 42 School

## Project goal

Develop a production-quality web application for playing Sudoku exclusively for students of 42 School.

The application should provide one Sudoku per day in three difficulties:

- Easy
- Medium
- Hard

Users authenticate through the official 42 School API/OAuth system. Only authorized 42 users may play.

The project should be developed incrementally, with the AI acting as a development partner rather than generating the entire application at once.

---

## Core principles

1. Do not build the entire project in one step.
2. Work incrementally and explain important decisions.
3. Prefer simple, maintainable solutions over premature abstraction or overengineering.
4. Before making a significant architectural change, explain the change and its trade-offs.
5. Do not invent external APIs, especially the 42 School API. Consult official documentation when current information is required.
6. Keep responsibilities separated and code modular.
7. Write tests for important business logic.
8. Keep security considerations in mind from the beginning.
9. Do not introduce unnecessary dependencies.
10. Do not modify unrelated code.
11. When a requirement is ambiguous and the decision materially affects architecture or behavior, ask before implementing it.

---

# Product requirements

## Authentication

Authentication must use the official 42 School authentication/API system, preferably OAuth2 if appropriate.

The application must:

- redirect users to 42 for authentication
- never ask for or store the user's 42 password
- securely handle OAuth credentials
- obtain the required user information
- verify that the authenticated account belongs to 42
- create or retrieve the corresponding local user
- establish an application session
- protect authenticated endpoints

Never hard-code:

- client IDs
- client secrets
- OAuth tokens
- session secrets
- database credentials

Use environment variables or an appropriate secret-management mechanism.

When implementing 42 authentication, verify the current official API documentation instead of relying on assumptions.

---

# Sudoku

The application must generate valid Sudoku puzzles.

There must be exactly one daily puzzle for each difficulty:

- Easy
- Medium
- Hard

For a given date and difficulty, all users should receive the same puzzle.

The system must guarantee that puzzles are valid and have a unique solution.

The architecture should separate:

- Sudoku generation
- Sudoku validation
- solution checking
- difficulty evaluation
- daily puzzle selection
- game/session management

Do not expose the complete solution unnecessarily to the frontend.

The backend must remain authoritative for validation.

---

# Daily puzzle design

Consider a deterministic strategy based on:

    date + difficulty

For example:

    2026-09-08 + hard -> deterministic seed -> puzzle

This can allow the same puzzle to be reproduced for the same date/difficulty.

However, evaluate whether puzzles should also be persisted in PostgreSQL. Persistence is preferred when it provides advantages for:

- auditing
- statistics
- reproducibility
- avoiding regeneration
- future administration
- tracking puzzle metadata

The application must explicitly define how dates and time zones are handled. The primary application timezone is Europe/Berlin unless the requirements are changed.

---

# MVP

The first MVP should contain only:

1. User visits the application.
2. User authenticates with 42.
3. Backend verifies the user.
4. User sees today's three Sudoku difficulties.
5. User selects a puzzle.
6. User plays the puzzle.
7. Backend can validate the completed solution.
8. Completion and solving time are stored.

Do not implement rankings, social features, advanced statistics, notifications, or other nonessential functionality before the MVP is working.

---

# Suggested technology

## Backend

Preferred stack:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Pydantic
- Alembic
- pytest

Use Python type hints consistently.

## Frontend

Preferred initial candidate:

- React
- TypeScript

Before committing to the frontend stack, briefly evaluate whether another option would materially improve the project.

## Infrastructure

Use:

- Docker
- Docker Compose for local development
- Git
- GitHub
- CI/CD

Do not introduce Kubernetes or other infrastructure complexity unless the project actually requires it.

---

# Architecture

Start with a modular monolithic architecture rather than microservices.

Conceptually:

    Frontend
        |
        v
    FastAPI API
        |
        +---- Authentication / 42 OAuth
        |
        +---- User service
        |
        +---- Puzzle service
        |
        +---- Game service
        |
        +---- Statistics service
        |
        v
    PostgreSQL

The Sudoku generator should remain independent from the HTTP/API layer so that it can be tested independently.

Avoid unnecessary service boundaries.

---

# Data model

Likely entities include:

- User
- Puzzle
- GameSession
- GameMove
- Statistics

Do not assume this model is final.

Before implementation, analyze:

- relationships
- primary keys
- foreign keys
- indexes
- unique constraints
- timestamps
- required fields
- data that should not be persisted

The model should support:

- one 42 identity per local user
- daily puzzles
- difficulty
- puzzle solution
- game progress
- completion time
- completion status
- future statistics

---

# API

Design the API before implementing it.

Potential endpoints include:

    GET /api/puzzles/today
    GET /api/puzzles/{id}

    POST /api/games
    GET /api/games/{id}
    POST /api/games/{id}/moves
    POST /api/games/{id}/complete

    GET /api/me
    GET /api/me/statistics

These are examples, not requirements.

Evaluate:

- naming
- HTTP methods
- authentication requirements
- authorization
- request/response schemas
- error responses
- idempotency
- validation
- pagination where relevant

Keep the API RESTful and simple.

---

# Frontend

The initial interface should be clean and minimal.

The home page should show:

    Sudoku of the Day

    Easy | Medium | Hard

The game interface should eventually support:

- selecting cells
- keyboard input
- number input
- deleting values
- visual feedback
- timer
- pause
- completion feedback

Do not prioritize visual polish before the core game works correctly.

---

# Security

Consider security from the beginning.

Relevant areas include:

- OAuth security
- session management
- CSRF where applicable
- CORS
- input validation
- SQL injection
- secret management
- authorization
- rate limiting
- abuse prevention
- server-side solution validation
- manipulation of frontend state
- HTTPS in production

Assume that users can inspect and modify all frontend JavaScript and network requests.

Never trust the frontend for authoritative game state or completion validation.

---

# Development workflow

Work in phases.

## Phase 1 — Requirements and architecture

Before writing application code:

1. Analyze requirements.
2. Identify ambiguities.
3. Define MVP.
4. Design architecture.
5. Design data model.
6. Design API.
7. Propose repository structure.
8. Create an implementation roadmap.

Stop and wait for approval before major implementation.

## Phase 2 — Project foundation

Set up:

- repository
- backend
- frontend
- Docker Compose
- PostgreSQL
- configuration
- environment variables
- linting/formatting if appropriate
- test infrastructure
- basic CI

## Phase 3 — 42 authentication

Implement and test:

- OAuth flow
- callback
- token handling
- user retrieval
- local user creation
- application session
- protected endpoint

Use official 42 documentation.

## Phase 4 — Sudoku engine

Implement independently:

- board representation
- puzzle generation
- solution generation
- uniqueness checking
- validation
- difficulty classification

Write comprehensive unit tests.

## Phase 5 — Daily puzzles

Implement:

- daily puzzle creation/retrieval
- difficulty selection
- date handling
- persistence
- deterministic behavior if selected

## Phase 6 — Game API

Implement:

- game creation
- retrieving game state
- moves
- completion
- validation
- solving time

## Phase 7 — Frontend

Implement:

- authentication flow
- daily puzzle selection
- Sudoku board
- controls
- timer
- completion state

## Phase 8 — Statistics

After MVP:

- games played
- games completed
- solving times
- personal history

## Phase 9 — Production

Add:

- production Docker setup
- CI/CD
- database migrations
- HTTPS
- logging
- monitoring
- backups
- deployment

---

# Code quality

Use:

- clear naming
- small functions
- explicit types
- single responsibility
- dependency injection where useful
- meaningful exceptions
- validation at system boundaries
- tests around business logic

Avoid:

- giant classes
- giant functions
- global mutable state
- unnecessary abstractions
- premature design patterns
- duplicated business logic
- hidden side effects

Do not add abstractions simply because they are theoretically reusable.

---

# Testing

Tests are part of the implementation, not an afterthought.

At minimum, test:

## Sudoku

- valid boards
- invalid boards
- generation
- uniqueness of solutions
- difficulty classification
- solution checking

## Authentication

- successful callback
- invalid OAuth state
- failed authentication
- unauthorized access

## Daily puzzles

- correct puzzle for date/difficulty
- same puzzle for all users
- different difficulty behavior
- timezone behavior

## Games

- valid moves
- invalid moves
- completion
- incorrect solutions
- duplicate requests where relevant
- authorization

Prefer unit tests for pure logic and integration tests for API/database behavior.

---

# Git workflow

Use Git throughout development.

Prefer small, focused commits.

Commit messages should describe the change clearly.

Do not make large unrelated commits.

Before committing:

- run tests
- run formatting/linting if configured
- inspect the diff
- verify that no secrets were added

Never commit:

- `.env`
- OAuth secrets
- passwords
- API tokens
- private keys

Provide an appropriate `.env.example`.

---

# AI development rules

The AI is a development partner.

For every significant implementation:

1. Explain what is being changed.
2. Explain why.
3. Identify important trade-offs.
4. Implement the smallest useful change.
5. Add/update tests.
6. Explain how to run the tests.
7. Check for regressions.
8. Only then proceed to the next step.

If a task can be solved without introducing a new dependency, prefer that.

If an external dependency is proposed, explain:

- why it is needed
- what problem it solves
- alternatives
- maintenance/security implications

When changing architecture, explicitly state:

    Why?
    Alternatives?
    Trade-offs?
    Impact on existing code?

Do not silently rewrite large portions of the project.

---

# Current task protocol

At the beginning of a new development session:

1. Inspect the existing repository.
2. Read the relevant documentation.
3. Check Git status.
4. Understand the current architecture.
5. Identify what has already been implemented.
6. Do not duplicate existing functionality.
7. Propose the next smallest logical step.

Do not assume the repository is empty unless inspection confirms it.

When working on an existing feature, preserve existing behavior unless the task explicitly requires changing it.

---

# Definition of Done

A feature is not considered complete merely because the code exists.

A feature is complete when:

- implementation exists
- tests exist where appropriate
- tests pass
- error cases are handled
- security implications are considered
- documentation is updated when needed
- no unrelated code was changed
- the developer understands how it works

For the MVP, the application should allow a real 42 user to authenticate, obtain today's puzzle, play it, submit it, and have the result persisted correctly.
