# Tank API

Generic Flask API layer for Tank applications. This is a thin routing layer that uses `tank-lib` for business logic and delegates complex operations to handler Lambdas.

## What's Included

- **Flask Routes**: All API endpoints (auth, data, chat, docs, schd, etc.)
- **CORS Configuration**: Production and development CORS setup
- **Cognito Authentication**: AWS Cognito integration
- **Static File Serving**: Serves Tower frontend

## Installation

### From Git (For Handler Projects)
```bash
pip install tank-api @ git+https://github.com/yourorg/tank-api@v1.0.0
```

### Local Editable (For Core Developers)
```bash
cd tank-api
pip install -e .
```

### For Handler Development
```bash
# In your handler project
pip install -r requirements.txt  # Should include tank-api

# Run renglo-api locally
python run_renglo_api.py
```

## Usage

### As a Package (From Handler Projects)
```python
from renglo_api import run

if __name__ == "__main__":
    run(debug=True, port=5000)
```

### For Development
```bash
cd tank-api
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m renglo_api.app  # or flask run
```

### For Deployment (Core Team Only)
```bash
cd tank-api
source venv/bin/activate
zappa update production
```

## Configuration

Create `env_config.py` from `env_config.py.TEMPLATE`:
```python
TANK_BASE_URL = "https://api.yourorg.com"
TANK_FE_BASE_URL = "https://app.yourorg.com"
# ... other config
```

## Routes

- `/ping` - Health check
- `/time` - Get current time (requires auth)
- `/auth/*` - Authentication routes
- `/data/*` - Data CRUD routes
- `/chat/*` - Chat and messaging routes
- `/docs/*` - Document management routes
- `/schd/*` - Scheduler routes
- `/blueprint/*` - Blueprint routes

## Dependencies

- `tank-lib` - Core business logic
- `Flask` - Web framework
- `Flask-Cognito` - Authentication
- `boto3` - AWS SDK
- `zappa` - Lambda deployment

## Version

Current version: 1.0.0

