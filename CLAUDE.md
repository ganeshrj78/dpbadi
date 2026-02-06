# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BP Badminton (Bullet Pandi Badminton Club) is a Flask web application for managing a badminton club. It tracks players, court sessions, attendance, payments, and shuttlecock inventory with automatic cost splitting among attendees.

## Technology Stack

### Backend
- **Flask 3.0** - Python web framework
- **Flask-SQLAlchemy** - ORM for database operations
- **Werkzeug** - Password hashing and security utilities
- **python-dotenv** - Environment variable management

### Database
- **SQLite** - Local development database (`instance/bpbadi.db`)
- **PostgreSQL** - Production database (Render deployment)
- Database URL configured via `DATABASE_URL` environment variable

### Frontend
- **Jinja2** - Server-side templating engine
- **Tailwind CSS (CDN)** - Utility-first CSS framework
- **Alpine.js** - Lightweight JavaScript framework for interactivity
- **Wimbledon-inspired theme** - Purple (#44005C) and green (#006633) color scheme with gold accents

### Deployment
- **Render** - Cloud hosting platform for production
- Auto-deployment via Git push

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (localhost:5000, debug mode)
python app.py

# Seed database with player data
python seed.py

# Run database migrations (local SQLite)
python migrate_db.py

# Run database migrations (PostgreSQL)
DATABASE_URL="postgresql://..." python migrate_db.py
```

## Project Structure

```
dpbadi/
├── app.py                 # Main application routes and logic
├── models.py              # SQLAlchemy data models
├── config.py              # Configuration management
├── migrate_db.py          # Database migration script
├── seed.py                # Sample data seeder
├── requirements.txt       # Python dependencies
├── instance/
│   └── bpbadi.db          # SQLite database (local)
├── static/
│   ├── logo.png           # Club logo
│   └── uploads/           # Profile photo uploads
└── templates/
    ├── base.html          # Base layout with navigation
    ├── login.html         # Login page
    ├── dashboard.html     # Admin dashboard
    ├── players.html       # Player list
    ├── player_form.html   # Add/edit player
    ├── player_detail.html # Player details
    ├── player_profile.html    # Player self-service profile
    ├── player_sessions.html   # Player session voting
    ├── player_payments.html   # Player payment recording
    ├── sessions.html      # Session list
    ├── session_form.html  # Add/edit session
    ├── session_detail.html    # Session details with attendance
    ├── session_refunds.html   # Dropout refund management
    ├── payments.html      # Payment list
    ├── payment_form.html  # Add payment
    ├── birdie_bank.html   # Shuttlecock inventory
    └── reset_admin_password.html  # Admin password reset
```

## Database Schema

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                   ER DIAGRAM                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
    │   PLAYERS    │          │   SESSIONS   │          │    COURTS    │
    ├──────────────┤          ├──────────────┤          ├──────────────┤
    │ PK id        │          │ PK id        │◄────────┐│ PK id        │
    │    name      │      ┌──►│    date      │         ││ FK session_id│──┐
    │    category  │      │   │    birdie_   │         │└──────────────┘  │
    │    email     │      │   │      cost    │         │                  │
    │    phone     │      │   │    notes     │◄────────┼──────────────────┘
    │    password_ │      │   │    is_       │         │
    │      hash    │      │   │     archived │         │
    │    zelle_    │      │   │    voting_   │         │
    │     preference      │   │     frozen   │         │
    │    profile_  │      │   └──────────────┘         │
    │      photo   │      │          ▲                 │
    │ FK managed_by│──┐   │          │                 │
    │    is_admin  │  │   │          │                 │
    │    is_active │  │   │   ┌──────┴───────┐         │
    └──────────────┘  │   │   │              │         │
           ▲          │   │   │              │         │
           │          ▼   │   │              │         │
           │   (self-ref) │   │              │         │
           │              │   │              │         │
           │              │   ▼              ▼         │
    ┌──────┴───────┐      │ ┌──────────────┐ ┌──────────────┐
    │  ATTENDANCES │      │ │   PAYMENTS   │ │DROPOUT_REFUNDS│
    ├──────────────┤      │ ├──────────────┤ ├──────────────┤
    │ PK id        │      │ │ PK id        │ │ PK id        │
    │ FK player_id │──────┤ │ FK player_id │─┤ FK player_id │───┐
    │ FK session_id│──────┘ │    amount    │ │ FK session_id│───┤
    │    status    │        │    method    │ │    refund_   │   │
    │    category  │        │    date      │ │      amount  │   │
    └──────────────┘        │    notes     │ │    suggested_│   │
                            └──────────────┘ │      amount  │   │
                                             │    instruct- │   │
    ┌──────────────┐                         │      ions    │   │
    │  BIRDIE_BANK │                         │    status    │   │
    ├──────────────┤                         │    processed_│   │
    │ PK id        │                         │      date    │   │
    │    date      │                         └──────────────┘   │
    │    transact- │                                            │
    │      ion_type│                                            │
    │    quantity  │                                            │
    │    cost      │◄───────────────────────────────────────────┘
    │    notes     │         (FK references to players
    │ FK session_id│──────►   for audit fields omitted
    └──────────────┘          for clarity)


    RELATIONSHIP LEGEND:
    ────────►  One-to-Many (FK on many side)
    ◄────────  Referenced by
    ──┐ ┌──    Self-referential
```

### Relationship Summary

| Parent Table | Child Table | Relationship | Foreign Key |
|--------------|-------------|--------------|-------------|
| players | players | 1:N (self-ref) | managed_by |
| players | attendances | 1:N | player_id |
| players | payments | 1:N | player_id |
| players | dropout_refunds | 1:N | player_id |
| sessions | courts | 1:N | session_id |
| sessions | attendances | 1:N | session_id |
| sessions | dropout_refunds | 1:N | session_id |
| sessions | birdie_bank | 1:N | session_id |

---

## Table Definitions

### Table: `players`
Stores player/member information including authentication and preferences.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `name` | VARCHAR(100) | NO | - | Player's full name |
| `category` | VARCHAR(20) | NO | 'regular' | Player type: `regular`, `adhoc`, `kid` |
| `phone` | VARCHAR(20) | YES | NULL | Phone number |
| `email` | VARCHAR(100) | YES | NULL | Email address (used for login) |
| `password_hash` | VARCHAR(255) | YES | NULL | Hashed password (pbkdf2:sha256) |
| `zelle_preference` | VARCHAR(10) | YES | 'email' | Preferred Zelle contact: `email` or `phone` |
| `profile_photo` | VARCHAR(255) | YES | NULL | Uploaded photo filename |
| `managed_by` | INTEGER | YES | NULL | FK to players.id - parent who manages this player |
| `is_admin` | BOOLEAN | YES | FALSE | Player has admin privileges |
| `is_active` | BOOLEAN | YES | TRUE | Account is active |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`

---

### Table: `sessions`
Represents a badminton session/booking with one or more courts.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `date` | DATE | NO | - | Session date |
| `birdie_cost` | FLOAT | NO | 0 | Birdie cost per player |
| `notes` | TEXT | YES | NULL | Session notes |
| `is_archived` | BOOLEAN | YES | FALSE | Session is completed/archived |
| `voting_frozen` | BOOLEAN | YES | FALSE | Players cannot change votes |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`

---

### Table: `courts`
Individual court reservations within a session.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `name` | VARCHAR(50) | YES | 'Court' | Court name (e.g., "Court 1") |
| `start_time` | VARCHAR(20) | NO | - | Start time (e.g., "6:30 AM") |
| `end_time` | VARCHAR(20) | NO | - | End time (e.g., "9:30 AM") |
| `cost` | FLOAT | NO | 0 | Court rental cost |
| `court_type` | VARCHAR(20) | YES | 'regular' | Type: `regular` or `adhoc` |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`
**Foreign Keys:** `session_id` → `sessions.id` (CASCADE DELETE)

---

### Table: `attendances`
Player attendance/voting for sessions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `status` | VARCHAR(20) | NO | 'NO' | Vote: `YES`, `NO`, `TENTATIVE`, `DROPOUT`, `FILLIN` |
| `category` | VARCHAR(20) | YES | 'regular' | Player category for this session |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`
**Unique Constraint:** `unique_player_session` on (`player_id`, `session_id`)
**Foreign Keys:**
- `player_id` → `players.id` (CASCADE DELETE)
- `session_id` → `sessions.id` (CASCADE DELETE)

---

### Table: `payments`
Payment records for players.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `amount` | FLOAT | NO | - | Payment amount (negative for refunds) |
| `method` | VARCHAR(20) | NO | - | Payment method: `Zelle`, `Cash`, `Venmo`, `Check`, `Other`, `Refund` |
| `date` | DATETIME | YES | NOW | Payment date |
| `notes` | TEXT | YES | NULL | Payment notes |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`
**Foreign Keys:** `player_id` → `players.id` (CASCADE DELETE)

---

### Table: `dropout_refunds`
Tracks refunds for players who drop out of sessions.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `refund_amount` | FLOAT | NO | 0 | Actual refund amount |
| `suggested_amount` | FLOAT | YES | 0 | System-calculated suggestion |
| `instructions` | TEXT | YES | NULL | Admin instructions/notes |
| `status` | VARCHAR(20) | YES | 'pending' | Status: `pending`, `processed`, `cancelled` |
| `processed_date` | DATETIME | YES | NULL | When refund was processed |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`
**Foreign Keys:**
- `player_id` → `players.id`
- `session_id` → `sessions.id`

---

### Table: `birdie_bank`
Tracks shuttlecock inventory (purchases and usage).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `date` | DATETIME | YES | NOW | Transaction date |
| `transaction_type` | VARCHAR(20) | NO | - | Type: `purchase` or `usage` |
| `quantity` | INTEGER | NO | - | Number of birdies |
| `cost` | FLOAT | YES | 0 | Cost (for purchases only) |
| `notes` | TEXT | YES | NULL | Transaction notes |
| `session_id` | INTEGER | YES | NULL | FK to sessions.id (for usage) |
| `created_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `created_at` | DATETIME | YES | NOW | Creation timestamp |
| `updated_by` | INTEGER | YES | NULL | FK to players.id - audit field |
| `updated_at` | DATETIME | YES | NOW | Last update timestamp |

**Indexes:** Primary key on `id`
**Foreign Keys:** `session_id` → `sessions.id`

## Authentication & Authorization

### User Types
1. **Master Admin** - Password-based login (`APP_PASSWORD` env var, default: `bpbadi2024`)
2. **Player Admin** - Player with `is_admin=True`, has admin access
3. **Player** - Regular player with limited access

### Access Control
- **Admin routes** - Dashboard, player management, session management, payments, birdie bank
- **Player routes** - Profile, session voting, payment recording (self and managed players)

## Key Features

### Cost Calculation
- Kids pay flat $11 per session
- Regular/adhoc players: `(total_court_cost / attendee_count) + birdie_cost`
- Player balance = total charges - total payments

### Session Management
- Multiple courts per session (regular or adhoc type)
- Voting freeze to lock player responses
- Archive completed sessions
- Financial summary with breakdown

### Dropout Refunds
- Track refunds for players who drop out
- Suggested refund based on fill-ins
- Process refund creates credit on player balance

### Family Management
- Players can manage spouse/kids
- Vote and pay on behalf of managed players

### Birdie Bank
- Track shuttlecock inventory
- Record purchases and usage
- Link usage to sessions

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key-change-in-production` |
| `DATABASE_URL` | Database connection URL | `sqlite:///bpbadi.db` |
| `APP_PASSWORD` | Master admin password | `bpbadi2024` |
| `RENDER` | Set to `true` in production | - |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/attendance` | POST | Update player attendance (admin) |
| `/api/player/attendance` | POST | Update own/managed attendance (player) |
| `/api/attendance/category` | POST | Update attendance category |
| `/api/players/<id>/category` | POST | Update player category |
