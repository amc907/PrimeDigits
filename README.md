# PrimeDigits

PrimeDigits is a complete virtual phone number reseller system built for Nigerian and Ghanaian freelancers. It includes a Customer Telegram Bot, an Admin Telegram Bot, and a FastAPI webhook server.

## Features

- **Customer Bot**: Buy US/Canada/UK numbers, manage SMS credits, view history, referrals
- **Admin Bot**: Dashboard, user management, broadcast, support agents
- **Payments**: Flutterwave integration (mocked for development)
- **Providers**: Twilio (US/Canada), Telnyx mock (UK)
- **Scheduling**: Automatic expiry warnings and number release

## Tech Stack

- Python 3.11+
- aiogram 3.x
- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy 2.0 + Alembic
- APScheduler
- Twilio SDK

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```
CUSTOMER_BOT_TOKEN=...
ADMIN_BOT_TOKEN=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
ADMIN_TELEGRAM_IDS=123456789,987654321
WEBHOOK_BASE_URL=https://your-app.up.railway.app
```

## Running Locally

```bash
pip install -r requirements.txt
# Start API
uvicorn api.main:app --reload
# Start Customer Bot
python -m customer_bot.main
# Start Admin Bot
python -m admin_bot.main
```

## Deployment (Railway)

1. Push to GitHub
2. Create Railway project from repo
3. Add PostgreSQL plugin
4. Set environment variables
5. Deploy

## Project Structure

```
PrimeDigits/
├── customer_bot/      # Customer Telegram bot
├── admin_bot/         # Admin Telegram bot
├── api/               # FastAPI app + webhooks
├── database/          # SQLAlchemy models + CRUD
├── providers/         # Twilio + Telnyx providers
├── utils/             # Notifications, scheduler, exchange rates
├── .env               # Environment variables
├── requirements.txt   # Python dependencies
├── Procfile           # Railway process definitions
└── README.md          # This file
```

## License

Proprietary — PrimeDigits Team.
