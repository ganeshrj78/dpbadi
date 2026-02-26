# Database Schema Documentation

This file contains detailed database schema information for the BP Badminton application.

## Entity Relationship Diagram

```
┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│   PLAYERS    │          │   SESSIONS   │          │    COURTS    │
├──────────────┤          ├──────────────┤          ├──────────────┤
│ PK id        │          │ PK id        │◄────────┐│ PK id        │
│    name      │      ┌──►│    date      │         ││ FK session_id│──┐
│    category  │      │   │    birdie_   │         │└──────────────┘  │
│    email     │      │   │      cost    │         │                  │
│    phone     │      │   │    is_       │◄────────┼──────────────────┘
│    password_ │      │   │     archived │         │
│      hash    │      │   │    voting_   │         │
│    is_admin  │      │   │     frozen   │         │
│    is_active │      │   └──────────────┘         │
│ FK managed_by│──┐   │          ▲                 │
└──────────────┘  │   │          │                 │
       ▲          │   │   ┌──────┴───────┐         │
       │          ▼   │   │              │         │
       │   (self-ref) │   │              │         │
       │              │   ▼              ▼         │
┌──────┴───────┐      │ ┌──────────────┐ ┌──────────────┐
│  ATTENDANCES │      │ │   PAYMENTS   │ │DROPOUT_REFUNDS│
├──────────────┤      │ ├──────────────┤ ├──────────────┤
│ PK id        │      │ │ PK id        │ │ PK id        │
│ FK player_id │──────┤ │ FK player_id │─┤ FK player_id │
│ FK session_id│──────┘ │    amount    │ │ FK session_id│
│    status    │        │    method    │ │    refund_   │
│    category  │        │    date      │ │      amount  │
└──────────────┘        └──────────────┘ │    status    │
                                         └──────────────┘
┌──────────────┐
│  BIRDIE_BANK │
├──────────────┤
│ PK id        │
│    date      │
│    transaction_type│
│    quantity  │
│    cost      │
│ FK session_id│
└──────────────┘
```

## Relationship Summary

| Parent | Child | Relationship | Foreign Key |
|--------|-------|--------------|-------------|
| players | players | 1:N (self-ref) | managed_by |
| players | attendances | 1:N | player_id |
| players | payments | 1:N | player_id |
| players | dropout_refunds | 1:N | player_id |
| sessions | courts | 1:N (cascade) | session_id |
| sessions | attendances | 1:N (cascade) | session_id |
| sessions | dropout_refunds | 1:N | session_id |
| sessions | birdie_bank | 1:N | session_id |

## Table: `players`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `name` | VARCHAR(100) | NO | - | Player's full name |
| `category` | VARCHAR(20) | NO | 'regular' | `regular`, `adhoc`, `kid` |
| `phone` | VARCHAR(20) | YES | NULL | Phone number |
| `email` | VARCHAR(100) | YES | NULL | Email (login) |
| `password_hash` | VARCHAR(255) | YES | NULL | Hashed password |
| `zelle_preference` | VARCHAR(10) | YES | 'email' | `email` or `phone` |
| `profile_photo` | VARCHAR(255) | YES | NULL | Photo filename |
| `managed_by` | INTEGER | YES | NULL | FK to players.id |
| `is_admin` | BOOLEAN | YES | FALSE | Admin privileges |
| `is_active` | BOOLEAN | YES | TRUE | Account active |
| `is_approved` | BOOLEAN | YES | FALSE | Registration approved |

**Indexes:** name, category, email, is_active, is_approved

## Table: `sessions`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `date` | DATE | NO | - | Session date |
| `birdie_cost` | FLOAT | NO | 0 | Birdie cost per player |
| `notes` | TEXT | YES | NULL | Session notes |
| `is_archived` | BOOLEAN | YES | FALSE | Completed/archived |
| `voting_frozen` | BOOLEAN | YES | FALSE | Votes locked |

**Indexes:** date, is_archived

## Table: `courts`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `name` | VARCHAR(50) | YES | 'Court' | Court name |
| `start_time` | VARCHAR(20) | NO | - | e.g., "6:30 AM" |
| `end_time` | VARCHAR(20) | NO | - | e.g., "9:30 AM" |
| `cost` | FLOAT | NO | 0 | Court rental cost |
| `court_type` | VARCHAR(20) | YES | 'regular' | `regular` or `adhoc` |

**Foreign Keys:** session_id → sessions.id (CASCADE DELETE)

## Table: `attendances`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `status` | VARCHAR(20) | NO | 'NO' | `YES`, `NO`, `TENTATIVE`, `DROPOUT`, `FILLIN` |
| `category` | VARCHAR(20) | YES | 'regular' | Category for this session |

**Unique Constraint:** (player_id, session_id)
**Indexes:** player_id, session_id, status, category, composite(status, category)

## Table: `payments`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `amount` | FLOAT | NO | - | Amount (negative for refunds) |
| `method` | VARCHAR(20) | NO | - | `Zelle`, `Cash`, `Venmo`, `Refund` |
| `date` | DATETIME | YES | NOW | Payment date |
| `notes` | TEXT | YES | NULL | Payment notes |

**Indexes:** player_id, date

## Table: `dropout_refunds`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `player_id` | INTEGER | NO | - | FK to players.id |
| `session_id` | INTEGER | NO | - | FK to sessions.id |
| `refund_amount` | FLOAT | NO | 0 | Actual refund |
| `suggested_amount` | FLOAT | YES | 0 | System suggestion |
| `instructions` | TEXT | YES | NULL | Admin notes |
| `status` | VARCHAR(20) | YES | 'pending' | `pending`, `processed`, `cancelled` |
| `processed_date` | DATETIME | YES | NULL | When processed |

**Indexes:** player_id, session_id, status, composite(player_id, status)

## Table: `birdie_bank`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | Auto | Primary key |
| `date` | DATETIME | YES | NOW | Transaction date |
| `transaction_type` | VARCHAR(20) | NO | - | `purchase` or `usage` |
| `quantity` | INTEGER | NO | - | Number of birdies |
| `cost` | FLOAT | YES | 0 | Cost (purchases only) |
| `notes` | TEXT | YES | NULL | Notes |
| `session_id` | INTEGER | YES | NULL | FK to sessions.id |
