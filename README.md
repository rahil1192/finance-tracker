# Finance App Backend

FastAPI backend for the finance tracking application with Plaid integration.

## Features

- Transaction management and categorization
- Plaid bank account integration
- Net worth tracking
- PDF statement parsing
- Recurring transaction detection
- RESTful API for mobile app

## Quick Start

### Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set up environment variables**:
```bash
cp env.example .env
# Edit .env with your Plaid credentials
```

3. **Run the server**:
```bash
python run.py
```

The API will be available at `http://localhost:8000`

### Production Deployment

See `DEPLOYMENT.md` for detailed deployment instructions.

## API Endpoints

### Transactions
- `GET /api/transactions` - Get all transactions
- `POST /api/transactions` - Create new transaction
- `PUT /api/transactions/{id}` - Update transaction
- `DELETE /api/transactions/{id}` - Delete transaction

### Accounts
- `GET /api/accounts` - Get all accounts
- `POST /api/plaid/create_link_token` - Create Plaid link token
- `POST /api/plaid/exchange_public_token` - Exchange Plaid token

### Net Worth
- `GET /api/networth/history` - Get net worth history

### Categories
- `GET /api/category_mappings` - Get category mappings
- `POST /api/category_mappings` - Add category mapping

## Environment Variables

- `PLAID_CLIENT_ID` - Your Plaid client ID
- `PLAID_SECRET` - Your Plaid secret
- `PLAID_ENV` - Plaid environment (sandbox/development/production)
- `SECRET_KEY` - Secret key for JWT tokens
- `DATABASE_URL` - Database connection string

## Database

The app uses SQLite for local development and PostgreSQL for production.

## License

MIT
