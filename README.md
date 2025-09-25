# The Prepared Investor - Automated Trading System

This project is a Django-based automated trading application designed to interact with the Korea Investment & Securities (KIS) API. It uses a combination of AI-driven analysis, Celery for task scheduling, and Django Channels for real-time updates to automate the process of stock screening, analysis, and trade execution.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Setup and Installation](#setup-and-installation)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Running with Docker](#running-with-docker)
- [Usage](#usage)
  - [Admin Interface](#admin-interface)
  - [System Management](#system-management)
- [Key Components Explained](#key-components-explained)
  - [Trading App](#trading-app)
  - [Celery Tasks](#celery-tasks)
  - [AI Analysis Service](#ai-analysis-service)

## Architecture Overview

The application is built on the following core technologies:

-   **Django:** The web framework for the user interface, API, and business logic.
-   **Celery:** A distributed task queue used to run background processes for stock analysis, trade execution, and monitoring.
-   **Redis:** Serves as the message broker for Celery and as a caching backend for Django.
-   **PostgreSQL:** The primary database for storing user data, trading accounts, trade logs, and analysis results.
-   **Django Channels:** Enables WebSocket support for real-time updates on the dashboard.
-   **Docker & Docker Compose:** Used to containerize the application and its services for consistent development and deployment.

## Features

-   **Multi-Account Management:** Securely store and manage credentials for multiple KIS trading accounts.
-   **Automated Stock Analysis:** A multi-stage analysis pipeline using Celery:
    1.  **Screening:** Identifies potential investment candidates from a predefined list of stocks.
    2.  **AI Analysis:** Uses `pandas-ta` and `prophet` to analyze historical data, determine an investment horizon, and set risk management levels (stop-loss/target price).
-   **Automated Trading:** Places buy and sell orders based on the results of the AI analysis.
-   **Real-Time Monitoring:**
    -   A WebSocket-based dashboard provides real-time updates on account balances, portfolio value, and trade executions.
    -   A periodic Celery task monitors open positions and executes sell orders if stop-loss or target prices are hit.
-   **System Management Interface:** A UI to trigger analysis tasks manually, view results, and manage the schedule of automated jobs.

## Project Structure

```
invest-app/
├── invest/                 # Main Django project configuration
│   ├── settings.py         # Django settings
│   ├── urls.py             # Root URL configuration
│   ├── celery.py           # Celery application setup
│   └── ...
├── trading/                # The core application
│   ├── models.py           # Database models
│   ├── views.py            # Page-rendering views
│   ├── api_views.py        # DRF API views
│   ├── tasks.py            # Celery background tasks
│   ├── consumers.py        # Django Channels WebSocket consumers
│   ├── admin.py            # Django admin configurations
│   ├── kis_client.py       # Client for the KIS API
│   ├── ai_analysis_service.py # AI-driven stock analysis logic
│   └── ...
├── templates/              # Django templates
└── static/                 # Static files (CSS, JS)
```

## Setup and Installation

### Prerequisites

-   Docker
-   Docker Compose

### Environment Variables

The application is configured using environment variables. Create a `.env` file in the root directory of the project with the following variables:

```env
# Django Settings
DJANGO_SECRET_KEY=your-django-secret-key
DJANGO_DEBUG=True

# Database Settings
POSTGRES_DB_I=invest_db
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
```

### Running with Docker

1.  **Build and start the services:**

    ```bash
    docker-compose up --build
    ```

2.  **Apply database migrations:**
    In a separate terminal, run the following command to apply the initial database migrations:

    ```bash
    docker-compose exec web python manage.py migrate
    ```

3.  **Create a superuser:**
    To access the Django admin interface, create a superuser account:
    ```bash
    docker-compose exec web python manage.py createsuperuser
    ```

4.  **Access the application:**
    -   **Web Application:** `http://localhost:8000`
    -   **Django Admin:** `http://localhost:8000/admin/`

## Usage

### Admin Interface

The Django admin interface is the primary way to manage core data.

1.  **Log in** with the superuser credentials you created.
2.  **Add a Trading Account:**
    -   Navigate to "Trading Accounts" and click "Add trading account".
    -   Fill in your KIS account details, including the API Key and Secret.
    -   Ensure the "Is active" checkbox is ticked if you want the system to use this account for automated trading.
3.  **Configure Strategy Settings:**
    -   Navigate to "AI Strategy Settings".
    -   The system allows only one settings instance. If one doesn't exist, create it.
    -   Define the percentage of your capital you wish to allocate to short, mid, and long-term strategies. The total must equal 100%.

### System Management

The "System" page in the application provides controls for the automated trading pipeline.

-   **Run Stock Screening:** Manually triggers the Celery task to screen stocks.
-   **Run AI Analysis:** Manually triggers the AI analysis of the screened stocks.
-   **Periodic Tasks:** View the status of all scheduled tasks and enable/disable them as needed.

## Key Components Explained

### Trading App

This is the heart of the application. It contains all the models, views, and business logic related to trading. Key files include:

-   `models.py`: Defines the database structure for accounts, portfolios, trade logs, and analysis results.
-   `kis_client.py`: A dedicated client for interacting with the KIS API. It handles authentication, token management, and provides methods for all required API calls.
-   `views.py` and `api_views.py`: Handle user-facing pages and the REST API for programmatic interactions.

### Celery Tasks

Located in `trading/tasks.py`, these are the background jobs that drive the automated system:

-   `run_daily_morning_routine`: Kicks off the process by screening for potential stocks.
-   `analyze_stocks_task`: Runs the AI analysis on the screened stocks.
-   `execute_ai_trades_task`: Places buy orders based on the analysis.
-   `monitor_open_positions_task`: Periodically checks open positions against their stop-loss and target prices.
-   `stream_kis_data_task`: A long-running task that connects to the KIS WebSocket for real-time trade execution data.

### AI Analysis Service

The logic in `trading/ai_analysis_service.py` is responsible for all stock analysis. It uses a combination of technical indicators from `pandas-ta` and time-series forecasting with `prophet` to classify stocks and determine appropriate risk levels.