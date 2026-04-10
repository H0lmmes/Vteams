# Vteams

User enumeration via Microsoft Teams endpoints.

## 📸 Demo

![demo](./Demo.png)

> ⚠️ For educational purposes and authorized testing only.

---

## 🚀 Quick Start

```bash
pip install -r requirements.txt
```

```bash
python3 vteams_userenum.py \
  -u user@domain.com \
  -p password \
  -e target@domain.com
```

```bash
cat USERS_VALID_TEAMS.txt
```

---

## ⚙️ Usage

### Single target
```bash
python3 vteams_userenum.py -u user@domain.com -p pass -e target@domain.com
```

### List
```bash
python3 vteams_userenum.py -u user@domain.com -p pass -L targets.txt
```

---

## ⚙️ Options

```bash
-u, --username       Username/email
-p, --password       Password (not recommended via CLI)
-e, --email          Single target
-L, --list           File with targets
--proxy              Use proxy (e.g. socks5://127.0.0.1:9050)
--log                Output log file
-v, --verbose        Show invalid users
--no-verify-ssl      Disable SSL verification
```

---

## 🔐 Authentication

You can also use environment variables:

```bash
export TEAMS_USERNAME=user@domain.com
export TEAMS_PASSWORD=password

python3 vteams_userenum.py -e target@domain.com
```

---

## 📦 Requirements

- Python 3.8+
- requests
- msal
- colorama

---

## 🧠 How it works

The script authenticates with a valid Microsoft 365 account and uses Teams endpoints to query external users.

Based on the API response, it is possible to distinguish between:
- valid users
- non-existent users

This behavior is due to differences in how Microsoft Teams handles  
identity resolution and external user lookup across tenants.

---

## 📌 When it works

- Target tenant allows external Teams communication
- User is discoverable via Teams APIs
- Endpoints are not restricted or patched

## ❌ Limitations

- Rate limiting may occur
- API behavior may change anytime
- Some tenants restrict external enumeration

---

## ⚠️ Legal Disclaimer

This project is intended for:

- Authorized research  
- Testing in owned environments  
- Educational purposes  

Unauthorized use may be illegal.
