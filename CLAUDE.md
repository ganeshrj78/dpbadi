# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BP Badminton is a Flask web application for managing a badminton club. It tracks players, court sessions, attendance, and payments with automatic cost splitting among attendees.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (localhost:5000, debug mode)
python app.py

# Seed database with player data
python seed.py
```

## Architecture

**Stack:** Flask 3.0, Flask-SQLAlchemy, SQLite, Tailwind CSS (CDN), Alpine.js

**Core Files:**
- `app.py` - All routes and application logic (single-file Flask app)
- `models.py` - SQLAlchemy models: Player, Session, Attendance, Payment
- `config.py` - Configuration via environment variables or defaults
- `templates/` - Jinja2 templates with Wimbledon-inspired purple/green theme

**Data Model:**
- **Player** has category (regular/adhoc/kid), tracks balance via charges minus payments
- **Session** represents a court booking with date, time, courts, court_cost, birdie_cost
- **Attendance** links players to sessions with status (YES/NO/TENTATIVE)
- **Payment** records player payments with amount and method (Zelle/Cash/Venmo)

**Cost Calculation Logic:**
- Total session cost = `courts * court_cost`
- Per-player cost = `(total_session_cost / attendee_count) + birdie_cost`
- Player balance = total charges from attended sessions - total payments

**Key Routes:**
- `/` - Dashboard with KPIs
- `/players`, `/sessions`, `/payments` - CRUD for each entity
- `/api/attendance` - AJAX endpoint for updating attendance status

**Authentication:** Simple password-based auth stored in `APP_PASSWORD` env var (default: `bpbadi2024`)

**Database:** SQLite at `instance/bpbadi.db` (configurable via `DATABASE_URL` env var)
