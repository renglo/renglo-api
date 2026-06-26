# Renglo API

Renglo HTTP runtime host for `renglo-lib`.

## Architecture (Multiple repositories)

```text
Root
├── console/                    ← Frontend (React + Vite)
├── extensions/                 ← Pluggable extensions
└── dev/
    ├── renglo-api/             ← Flask runtime host + setup guide
    └── renglo-lib/             ← Core logic (controllers/models)
```

## Installation

### Step 0

Create a workspace folder:

```bash
mkdir <NAME-OF-PROJECT>
cd <NAME-OF-PROJECT>
```

### Step 1

Clone the repositories:

```bash
git clone https://github.com/renglo/console.git
mkdir dev
cd dev
git clone https://github.com/renglo/renglo-lib.git
git clone https://github.com/renglo/renglo-api.git
```

### Step 2

Create backend virtual environment and install dependencies:

```bash
cd renglo-api
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Step 3

Create local config from template in this repository:

```bash
cp env_config.py.TEMPLATE env_config.py
```

Edit `env_config.py` with your local values.

### Step 4

Run the backend:

```bash
source venv/bin/activate
export RENGLO_CONFIG_PATH=./env_config.py
renglo-serve --host 0.0.0.0 --port 5000 --debug
```

### Step 5

Run the frontend in another terminal:

```bash
cd ../../console
npm install
npm run dev
```

## Extensions

Install extension repositories in your workspace `extensions/` folder:

```bash
cd ..
mkdir -p extensions
cd extensions
git clone https://github.com/renglo/schd.git
git clone https://github.com/renglo/data.git
git clone https://github.com/renglo/pes.git
```

Install extension handlers into the same backend venv:

```bash
cd ../dev/renglo-api
source venv/bin/activate
pip install -e ../../extensions/schd/package
pip install -e ../../extensions/pes/package
```

Upload extension blueprints:

```bash
cd ../../extensions
python schd/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
python pes/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
```

For custom extension UI, clone extension repos into `extensions/` and update
console env files (`.env.development`, `.env.production`) to include them in
`VITE_EXTENSIONS`.

## Local Runtime Commands

Use config file:

```bash
export RENGLO_CONFIG_PATH=./env_config.py
renglo-serve --port 5000
```

Or pure env vars:

```bash
export DYNAMODB_RINGDATA_TABLE=...
export DYNAMODB_ENTITY_TABLE=...
renglo-serve --host 0.0.0.0 --port 5000 --debug
```

Alternative runner:

```bash
python -m renglo_api --port 5000
```

## Production Entrypoints

- WSGI app: `renglo_api.application:app`
- Lambda handler: `renglo_api.lambda_handler.lambda_handler`

## Available Routes

- `/_auth/*` authentication
- `/_data/*` data
- `/_search/*` search
- `/_graph/*` graph
- `/_blueprint/*` blueprint
- `/_docs/*` docs
- `/_schd/*` scheduler
- `/_chat/*` chat
- `/_state/*` state
- `/_session/*` session
- `/ping` health check

