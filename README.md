# Vteams

Microsoft Teams user enumeration via authentication-based API interaction.

![demo](./Demo.png)

> ⚠️ For educational purposes and authorized testing only.

---

## 🚀 Quick Start

```bash
pip install -r requirements.txt
```

### Single target (interactive credentials)
```bash
python3 vteams_userenum.py -e target@domain.com
```

### With credentials (CLI)
```bash
python3 vteams_userenum.py \
  -u user@domain.com \
  -p password \
  -e target@domain.com
```

### Environment variables (recommended)
```bash
export TEAMS_USERNAME=user@domain.com
export TEAMS_PASSWORD=password

python3 vteams_userenum.py -e target@domain.com
```

---

## Input Modes

### Single email
```bash
python3 vteams_userenum.py -e target@domain.com
```

### Email list
```bash
python3 vteams_userenum.py -L targets.txt
```

---

## ⚙️ Options

```bash
-u, --username     Username/email for authentication
-p, --password     Password (or use env vars TEAMS_PASSWORD)
-e, --email        Single target email
-L, --list         File with target emails (one per line)
--log              Log file output
--proxy            Proxy URL (e.g. socks5://127.0.0.1:9050)
--no-verify-ssl    Disable SSL verification (not recommended)
-v, --verbose      Show invalid/blocked users as well
```

---

## Requirements

- Python 3.8+
- requests
- msal
- colorama
- python-dotenv (optional)

---

## 🧠 How it works

The tool authenticates against Microsoft 365 using MSAL and obtains access tokens for Teams APIs.

It then queries external Teams endpoints and analyzes response behavior to determine whether a target user exists or is reachable.

Differences in API responses allow classification of:
- valid users
- non-existent users
- blocked or restricted accounts

---

## 📌 When it works

- Valid Microsoft 365 credentials
- Teams enabled in tenant
- External communication allowed (or partially allowed)
- Accessible Microsoft endpoints

May not work if:
- rate limiting is enforced
- tenant has strict security policies
- API behavior changes
- MFA / conditional access blocks authentication flow

---


## Output

Valid users are stored in:

```bash
USERS_VALID_TEAMS.txt
```

If logging is enabled:

```bash
--log results.log
```

---

## ⚠️ Legal Disclaimer

This project is intended for:

- Authorized security research  
- Testing in controlled environments  
- Educational purposes  

Unauthorized use may be illegal.
