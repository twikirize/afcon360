Here is a comprehensive, production-ready `README.md` tailored specifically for your project. It maps cleanly to the Flask, Celery, Redis, and Alembic-managed multi-tier architecture evident in your directory footprint.

---

# AFCON360 Application Platform

Welcome to the **AFCON360** application repository. This platform serves as a multi-tiered, modular ecosystem designed to handle event registration, accommodation bookings, transport logistics, financial wallet infrastructure, and content moderation across distinct user tiers (Fans, Organizations, and Administrators).

---

## 🗺️ Project Architecture Overview

The system is constructed as a modular **Flask** application backed by **Celery** for asynchronous background operations, **Redis** for state tracking/caching, and **SQLAlchemy (via Alembic)** for robust structural database migrations.

### Key Modules & Directories

* **`app/auth/` & `app/identity/**`: Manages granular role-based user management, multi-factor authentication (MFA), KyC/KyB tier compliance, and organizational delegation.
* **`app/accommodation/`**: Houses the state machine for processing room availability, property checkouts, and booking workflows.
* **`app/transport/`**: Controls vehicle tracking, incident reporting, driver onboarding, and fleet management modules.
* **`app/events/`**: Manages public/private event life cycles, attendee registrations, and secure ticket parsing.
* **`app/wallet/`**: Core financial engine executing double-entry ledger bookkeeping, fraud detection routines, currency fx services, and payment gateway hook integrations (Flutterwave, Mobile Money, Paystack, etc.).
* **`app/admin/`**: High-privilege interfaces handling platform moderation pipelines, aml verification queues, and system-wide setting overrides.

---

## 🛠️ Technological Prerequisites

Ensure your host machine features the following runtimes:

* **Python 3.13+** (Optimized with `.pyc` targets matched to compilation environments)
* **Redis Server** (Utilized for Flask-Session data storage and Celery task brokerage)
* **Database engine** (PostgreSQL / MySQL / SQLite relative to configurations inside `app/config.py`)
* **Nginx** (Reverse proxy configs are included natively under `docker/nginx/`)

---

## 🚀 Quick Start & Environment Local Setup

### 1. Repository Setup & Dependencies

Clone the system to your local stack environment, configure a virtual workspace, and sync your packages:

```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install essential project requirements
pip install -r requirements.txt

```

### 2. Database Initializations & Structural Migrations

Structural models utilize Alembic history records. Initialize or catch up the schema using the following operations:

```bash
# Upgrade database context to the latest migration structural node
flask db upgrade

# Seed required system permissions and standard structural roles
python scripts/seed_roles.py
python scripts/init_settings.py

```

### 3. Activating Asynchronous Process Worker Tasks

To process non-blocking registrations, wallet ledger transactions, and webhook processing queues, boot up your Celery worker daemon:

```bash
celery -A app.celery_app.celery worker --loglevel=info

```

### 4. Running the Development Server

Execute the application entry layer directly using standard Python routines:

```bash
python -m app.cli
# Or alternatively leverage the native CLI footprint:
flask run --debug

```

---

## 🔒 Routing & Template Conventions

When designing or updating view components, notice the core parameter handling configuration:

> ⚠️ **Routing Standard Note**: All HTML routing parameter signatures within template configurations mapping across the `/templates/` directory follow strict verification criteria. Ensure context anchors process explicitly using `identifier=` arguments rather than old `event_slug=` constructs to prevent target tracking breaking across view models.

---

## 📋 Useful CLI & Verification Scripts

The repository comes packaged with helper scripts under `/scripts/` designed to make administrative tasks straightforward:

* **`python scripts/db_audit.py`**: Runs diagnostics checks over current schemas to locate non-conforming table layouts.
* **`python scripts/reset_test_db.py`**: Wipes local testing frameworks safely for localized sanity evaluations.
* **`python scripts/check_id_usage.py`**: Scans codebase architecture definitions to avoid unexpected ID compilation issues.

---

