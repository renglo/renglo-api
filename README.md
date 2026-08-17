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
git clone https://github.com/renglo/wss.git
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

```bash
cp run.sh.TEMPLATE run.sh
```

Enter  and  in run.sh (you just need to do this once)

```
export RENGLO_CONFIG_PATH=./env_config.py
export AWS_PROFILE=<your_profile>
export AWS_DEFAULT_REGION=<your_region>
renglo-serve --host 127.0.0.1 --port 5001 --debug
```

Every time you want to run the server just activate the virtual environment and run run.sh

```bash
source venv/bin/activate
source run.sh
```



### Step 5

Create console env files, logos, and Cognito settings — see [Console configuration and branding](#console-configuration-and-branding) — then run the frontend:

```bash
cd console
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
pip install -e ../../extensions/data/package
pip install -e ../../extensions/pes/package
```

Upload extension blueprints:

```bash
cd ../../extensions
python schd/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
python pes/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
```



## Console configuration and branding

**After bootstrap:** follow [bootstrap §7 Path B](../../ops/bootstrap/README.md#path-b--local-development-default--no-cicd) for local development (no CI/CD). Cloud production is optional later ([Path A](../../ops/bootstrap/README.md#path-a--cloud-go-live-optional-later) + [§8](../../ops/bootstrap/README.md#8-cicd-contract-optional--cloud-production-only)).

**Local dev config:** operators generate `bootstrap/output/<env>/local-dev/` with `python bootstrap/install.py write-local-config` (bootstrap §7.3). Copy `env_config.py`, `run.sh`, and `.env.development` from that folder — do not hand-edit SSM values unless merging an update.

### 1. Copy templates to real config files

**Backend** (if you have not already — see [Step 3](#step-3)):

```bash
cd dev/renglo-api
cp env_config.py.TEMPLATE env_config.py
cp run.sh.TEMPLATE run.sh
```

**Console:**

```bash
cd console
cp .env.development.TEMPLATE .env.development
cp .env.production.TEMPLATE .env.production
```

These files are gitignored. Keep the `.TEMPLATE` files unchanged in the repo.

### 2. Fill configuration from AWS

Pull bootstrap vars written to SSM , profile, and region):

```bash
export ENV=<your-env>
export AWS_PROFILE=<your-profile>
export AWS_REGION=<your-region>

aws ssm get-parameter \
  --name "/${ENV}/bootstrap/platform-vars/production" \
  --query Parameter.Value \
  --output text \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" | jq .
```

Copy values from the `VARS` object into your config files:


| SSM `VARS` key           | `dev/renglo-api/env_config.py` | `console/.env.development`   | `console/.env.production`    |
| ------------------------ | ------------------------------ | ---------------------------- | ---------------------------- |
| (env name)               | `WL_NAME`                      | —                            | —                            |
| `BASE_URL`               | `BASE_URL`                     | —                            | `VITE_API_URL`               |
| `FE_BASE_URL`            | `FE_BASE_URL` (cloud Amplify)  | —                            | —                            |
| —                        | `INVITE_FE_BASE_URL` (local console for invite links, e.g. `http://127.0.0.1:5174`) | — | —                            |
| `FROM_EMAIL`             | `FROM_EMAIL` (SES from)        | —                            | —                            |
| `COGNITO_REGION`         | `COGNITO_REGION`               | `VITE_COGNITO_REGION`        | `VITE_COGNITO_REGION`        |
| `COGNITO_USERPOOL_ID`    | `COGNITO_USERPOOL_ID`          | `VITE_COGNITO_USERPOOL_ID`   | `VITE_COGNITO_USERPOOL_ID`   |
| `COGNITO_APP_CLIENT_ID`  | `COGNITO_APP_CLIENT_ID`        | `VITE_COGNITO_APP_CLIENT_ID` | `VITE_COGNITO_APP_CLIENT_ID` |
| `S3_BUCKET_NAME`         | `S3_BUCKET_NAME`               | —                            | —                            |
| `DYNAMODB_*` tables      | matching `DYNAMODB_*` keys     | —                            | —                            |
| `ROLE_ARN` / tenant role | `ROLE_ARN`                     | —                            | —                            |
| `VITE_WEBSOCKET_URL`     | `WEBSOCKET_CONNECTIONS`        | `VITE_WEBSOCKET_URL`         | `VITE_WEBSOCKET_URL`         |


**Local development defaults** (leave these in `.env.development`):

- `VITE_API_URL='http://127.0.0.1:5001'` — points at your local `renglo-api` server ([Step 5](#step-5)).
- `VITE_DEV_MODE=true`

**Team invites:** set `FROM_EMAIL` from SSM. For **local API** (default Path B), set `INVITE_FE_BASE_URL` to your Vite URL (`http://127.0.0.1:5174` by default). For **cloud Lambda** later, leave `INVITE_FE_BASE_URL` unset and use `FE_BASE_URL` (Amplify). Cognito self-signup stays disabled. See [bootstrap §7](../../ops/bootstrap/README.md#7-after-bootstrap--make-the-app-usable).

In `run.sh`, set `AWS_PROFILE` and `AWS_DEFAULT_REGION` to the same profile/region you used for bootstrap.

Generate local secrets in `env_config.py` (not in SSM): set `SECRET_KEY`, `CSRF_SESSION_KEY`, and optional `OPENAI_API_KEY`.

### 3. Console logos

Create two branding images and place them in `console/public/`:


| File             | Size         | Max size | Used on     |
| ---------------- | ------------ | -------- | ----------- |
| `small_logo.jpg` | 500×500 px   | 100 KB   | Menu header |
| `large_logo.jpg` | 1000×1000 px | 500 KB   | Login page  |


```bash
# From workspace root — copy your image files into:
console/public/small_logo.jpg
console/public/large_logo.jpg
```

The env templates already reference these paths:

```bash
VITE_WL_LOGO='/small_logo.jpg'
VITE_WL_LOGIN='/large_logo.jpg'
```

No change needed in `.env.development` / `.env.production` unless you use different filenames.

### 4. Extension UI (optional)

For custom extension UI, clone extension repos into `extensions/` and add their folder names to `VITE_EXTENSIONS` in `.env.development` and `.env.production` (comma-separated, e.g. `schd,data,pes`).

See [console/EXTENSIONS_README.md](../../console/EXTENSIONS_README.md) for extension setup details.

## Production Entrypoints

- WSGI app: `renglo_api.application:app`
- Lambda handler: `renglo_api.lambda_handler.lambda_handler`



## Available Routes

- `/_auth/*` authentication
- `/_data/*` data
- `/_search/*` search
- `/_graph/*` graph
- `/_blueprint/*` blueprint
- `/_files/*` files
- `/_schd/*` scheduler
- `/_chat/*` chat
- `/_state/*` state
- `/_session/*` session
- `/ping` health check



## License

This project is licensed under the MIT License. See [LICENSE.txt](LICENSE.txt) for details.