# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

BP Badminton is a Flask web application for managing a badminton club. It tracks players, court sessions, attendance, payments, and shuttlecock inventory with automatic cost splitting.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (localhost:5000, debug mode)
python app.py

# Seed database with player data
python seed.py
```

## Technology Stack

- **Backend:** Flask 3.0, Flask-SQLAlchemy, Werkzeug
- **Database:** SQLite (local), PostgreSQL (production on Render)
- **Frontend:** Jinja2, Tailwind CSS (CDN), Alpine.js
- **Theme:** Wimbledon-inspired - Purple (#44005C), Green (#006633), Gold accents

## Project Structure

```
dpbadi/
├── app.py              # Main routes and application logic
├── models.py           # SQLAlchemy data models
├── config.py           # Configuration management
├── templates/          # Jinja2 templates
├── static/uploads/     # Profile photo uploads
└── instance/bpbadi.db  # SQLite database (local)
```

## Key Models

| Model | Purpose |
|-------|---------|
| `Player` | Members with auth, categories (regular/adhoc/kid) |
| `Session` | Court bookings with date, courts, birdie cost |
| `Attendance` | Player votes: YES, NO, TENTATIVE, DROPOUT, FILLIN |
| `Payment` | Payment records (Zelle, Cash, Venmo, Refund) |
| `Court` | Individual court reservations within sessions |
| `DropoutRefund` | Refunds for players who drop out |
| `BirdieBank` | Shuttlecock inventory tracking |

## Cost Calculation

- **Kids:** Flat $11 per session
- **Regular/Adhoc:** `(court_cost / attendee_count) + birdie_cost`
- **Balance:** Total charges - total payments

## Authentication

- **Master Admin:** Password via `APP_PASSWORD` env var (default: `bpbadi2024`)
- **Player Admin:** Player with `is_admin=True`
- **Player:** Regular player with limited access

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key...` |
| `DATABASE_URL` | Database connection URL | `sqlite:///bpbadi.db` |
| `APP_PASSWORD` | Master admin password | `bpbadi2024` |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/attendance` | POST | Update attendance (admin) |
| `/api/player/attendance` | POST | Update own attendance (player) |
| `/health` | GET | Health check for uptime monitoring |

## Additional Documentation

- Database schema details: See `docs/CLAUDE.md`
- Template conventions: See `templates/CLAUDE.md`
