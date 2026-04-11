#!/usr/bin/python3
import argparse
import requests
import json
import os
import os.path
import sys
import re
import time
import random
import getpass
import gc
from msal import PublicClientApplication
from colorama import Back, Fore, Style
import datetime
from os.path import expanduser
import hashlib
import logging
from pathlib import Path
from dotenv import load_dotenv  # pip install python-dotenv

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# Load environment variables from .env file
load_dotenv()

# User agent rotation for stealth
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# Microsoft Azure App ID for Teams/Skype authentication
TEAMS_CLIENT_ID = "1fec8e78-bce4-4aaf-ab1b-5451cc387264"

# API Endpoints - Updated for 2026
class APIEndpoints:
    """Updated Microsoft Teams and Skype API endpoints"""
    OPENID_CONFIG = "https://login.microsoftonline.com/{domain}/.well-known/openid-configuration"
    AUTHORITY_BASE = "https://login.microsoftonline.com"
    SKYPE_TOKEN_ENDPOINT = "https://authsvc.teams.microsoft.com/v1.0/authz"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    TEAMS_API_EMEA = "https://teams.microsoft.com/api/mt/emea/beta"
    TEAMS_USERS_ENDPOINT = f"{TEAMS_API_EMEA}/users/tenants"
    TEAMS_USER_SEARCH = f"{TEAMS_API_EMEA}/users"
    TEAMS_EXTERNAL_SEARCH = f"{TEAMS_API_EMEA}/users"
    SHAREPOINT_BASE = "https://{tenant}-my.sharepoint.com"
    SCOPE_TEAMS = "https://api.spaces.skype.com/.default"
    SCOPE_SHAREPOINT = "https://{sharepoint_url}/.default"

# Configuration
CONFIG = {
    'request_timeout': 10,
    'verify_ssl': True,  
    'min_delay_seconds': 1.5,
    'max_delay_seconds': 3.5,
    'max_retries': 3,
    'retry_backoff_factor': 2,
    'output_file_permissions': 0o600, 
    'log_file_permissions': 0o600,
    'enable_proxy': False,
    'proxy_url': None,  
}


fd = None
stats = {
    'total_requests': 0,
    'successful_enums': 0,
    'failed_enums': 0,
    'start_time': datetime.datetime.now(),
}

# ============================================================================
# LOGGING & OUTPUT FUNCTIONS
# ============================================================================

def setup_logger(log_file=None):
    """Initialize logger with secure file handling"""
    global fd
    
    log_config = {
        'level': logging.INFO,
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'datefmt': '%Y-%m-%d %H:%M:%S'
    }
    
    if log_file:
        log_path = Path(log_file)
        log_path.touch(mode=CONFIG['log_file_permissions'], exist_ok=True)
        
        logging.basicConfig(
            filename=log_file,
            level=log_config['level'],
            format=log_config['format'],
            datefmt=log_config['datefmt']
        )
        fd = open(log_file, 'a')
    else:
        logging.basicConfig(
            level=log_config['level'],
            format=log_config['format'],
            datefmt=log_config['datefmt']
        )

def p_err(msg, exit_code=True):
    """Print error message"""
    output = Fore.RED + "[-] " + msg + Style.RESET_ALL
    print(output)
    logging.error(msg)
    if exit_code:
        sys.exit(-1)

def p_warn(msg):
    """Print warning message"""
    output = Fore.YELLOW + "[-] " + msg + Style.RESET_ALL
    print(output)
    logging.warning(msg)

def p_success(msg):
    """Print success message"""
    output = Fore.GREEN + "[+] " + msg + Style.RESET_ALL
    print(output)
    logging.info(msg)

def p_info(msg):
    """Print info message"""
    output = Fore.CYAN + msg + Style.RESET_ALL
    print(output)
    logging.info(msg)

def p_task(msg):
    """Print task status (no newline)"""
    bufferlen = max(0, 75 - len(msg))
    output = msg + "." * bufferlen
    print(output, end="", flush=True)

def write_result_safe(filename, content):
    """Write results to file with secure permissions"""
    try:
        with open(filename, 'a') as f:
            f.write(content + '\n')
        os.chmod(filename, CONFIG['output_file_permissions'])
    except IOError as e:
        p_warn(f"Could not write to results file: {str(e)}")

# ============================================================================
# ANTI-DETECTION FUNCTIONS
# ============================================================================

def get_random_delay():
    """Get random delay between requests for stealth"""
    return random.uniform(CONFIG['min_delay_seconds'], CONFIG['max_delay_seconds'])

def get_random_useragent():
    """Get random User-Agent for stealth"""
    return random.choice(USER_AGENTS)

def sanitize_error_message(msg):
    """Remove sensitive information from error messages"""
    # Remove tokens, IDs, email addresses
    msg = re.sub(r'(eyJ[A-Za-z0-9_-]+)', '[REDACTED_TOKEN]', msg)
    msg = re.sub(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', '[REDACTED_EMAIL]', msg)
    msg = re.sub(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', '[REDACTED_ID]', msg)
    return msg

# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def get_credentials(username=None, password=None):
    """Get credentials securely from user or environment"""
    
    # Get username
    if not username:
        username = input("Email/Username: ").strip()
    
    if not username:
        p_err("Username cannot be empty", True)
    
    # Validate email format
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', username):
        p_warn("Warning: Username does not appear to be valid email format")
    
    # Get password
    if not password:
        password = getpass.getpass("Password: ")
    
    if not password:
        p_err("Password cannot be empty", True)
    
    return username, password

def make_request(method, url, headers=None, data=None, retries=0):
    """Make HTTP request with retry logic and error handling"""
    
    if headers is None:
        headers = {}
    
    # Add random User-Agent
    headers['User-Agent'] = get_random_useragent()
    
    # Set up proxy if enabled
    proxies = None
    if CONFIG['enable_proxy'] and CONFIG['proxy_url']:
        proxies = {
            'http': CONFIG['proxy_url'],
            'https': CONFIG['proxy_url']
        }
    
    try:
        if method.upper() == 'GET':
            response = requests.get(
                url,
                headers=headers,
                timeout=CONFIG['request_timeout'],
                verify=CONFIG['verify_ssl'],
                proxies=proxies
            )
        elif method.upper() == 'POST':
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=CONFIG['request_timeout'],
                verify=CONFIG['verify_ssl'],
                proxies=proxies
            )
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        stats['total_requests'] += 1
        return response
        
    except requests.exceptions.ConnectTimeout:
        if retries < CONFIG['max_retries']:
            wait_time = CONFIG['retry_backoff_factor'] ** retries
            p_warn(f"Connection timeout. Retrying in {wait_time}s... (Attempt {retries + 1}/{CONFIG['max_retries']})")
            time.sleep(wait_time)
            return make_request(method, url, headers, data, retries + 1)
        else:
            raise
    
    except requests.exceptions.RequestException as e:
        error_msg = sanitize_error_message(str(e))
        p_warn(f"Request error: {error_msg}")
        raise

def get_tenant_id(username):
    """Retrieve Microsoft Tenant ID for the given username/email domain"""
    domain = username.split("@")[-1]
    p_task(f"Fetching tenant ID for domain {domain}...")
    
    try:
        response = make_request(
            'GET',
            APIEndpoints.OPENID_CONFIG.format(domain=domain)
        )
        
        if response.status_code != 200:
            p_err(f"Could not retrieve tenant ID (HTTP {response.status_code})", True)
        
        json_content = response.json()
        tenant_id = json_content['authorization_endpoint'].split("/")[3]
        p_success("SUCCESS!")
        return tenant_id
        
    except Exception as e:
        p_err(f"Error retrieving tenant ID: {sanitize_error_message(str(e))}", True)

def two_fa_login(username, scope):
    """Perform device code authentication flow (for 2FA-enabled accounts)"""
    tenant_id = get_tenant_id(username)
    
    app = PublicClientApplication(
        TEAMS_CLIENT_ID,
        authority=f"{APIEndpoints.AUTHORITY_BASE}/{tenant_id}"
    )
    
    try:
        flow = app.initiate_device_flow(scopes=[scope])
        
        if "user_code" not in flow:
            p_err("Could not retrieve user code in authentication flow", True)
        
        p_warn(flow.get("message"))
        
    except Exception as e:
        p_err(f"Device code authentication failed: {str(e)}", True)
    
    try:
        result = app.acquire_token_by_device_flow(flow)
        
        if "access_token" not in result:
            p_err(f"Failed to acquire token: {result.get('error_description', 'Unknown error')}", True)
        
        return result
        
    except Exception as e:
        p_err(f"Error during device flow authentication: {str(e)}", True)

def get_bearer_token(username, password, scope):
    """Get OAuth bearer token using username/password authentication"""
    
    if isinstance(scope, dict):
        p_task("Fetching Bearer token for SharePoint...")
        tenant_name = scope.get('tenantName', 'TenantName_')
        scope = f"https://{tenant_name}-my.sharepoint.com/.default"
    else:
        p_task("Fetching Bearer token for Teams...")
    
    tenant_id = get_tenant_id(username)
    
    app = PublicClientApplication(
        TEAMS_CLIENT_ID,
        authority=f"{APIEndpoints.AUTHORITY_BASE}/{tenant_id}"
    )
    
    try:
        result = app.acquire_token_by_username_password(
            username,
            password,
            scopes=[scope]
        )
        
    except ValueError as e:
        error_msg = str(e.args[0]) if e.args else str(e)
        if "MSA accounts" in error_msg:
            p_warn("2FA/MSA detected. Use device code flow.")
        p_err("Error acquiring token", True)
    
    if "access_token" not in result:
        error_desc = result.get("error_description", "Unknown error")
        
        if "Invalid username or password" in error_desc:
            p_err("Invalid credentials", True)
        elif "multi-factor authentication" in error_desc:
            p_warn("2FA required, initiating device code flow...")
            result = two_fa_login(username, scope)
        else:
            p_err(f"Authentication failed: {error_desc}", True)
    
    p_success("SUCCESS!")
    return result["access_token"]

def get_skype_token(bearer_token):
    """Retrieve Skype token from bearer token"""
    p_task("Fetching Skype token...")
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = make_request(
            'POST',
            APIEndpoints.SKYPE_TOKEN_ENDPOINT,
            headers=headers
        )
        
        if response.status_code != 200:
            p_err(f"Error fetching Skype token: HTTP {response.status_code}", True)
        
        json_content = response.json()
        
        if "tokens" not in json_content:
            p_err("Could not retrieve Skype token", True)
        
        skype_token = json_content.get("tokens", {}).get("skypeToken")
        
        if not skype_token:
            p_err("Skype token not found in response", True)
        
        p_success("SUCCESS!")
        return skype_token
        
    except Exception as e:
        p_err(f"Error fetching Skype token: {str(e)}", True)

def get_sender_info(bearer_token):
    """Retrieve authenticated user information"""
    p_task("Fetching sender info...")
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-Ms-Client-Version": "1415/1.0.0.2023031528"
    }
    
    sender_info = None
    
    try:
        response = make_request(
            'GET',
            APIEndpoints.TEAMS_USERS_ENDPOINT,
            headers=headers
        )
        
        if response.status_code != 200:
            p_err(f"Could not retrieve sender's user ID (HTTP {response.status_code})", True)
        
        users_data = response.json()
        if not users_data:
            p_err("No user data returned", True)
        
        user_id = users_data[0].get('userId')
        
        if not user_id:
            p_err("Could not extract user ID", True)
        
        # Find matching user by ID
        skip_token = None
        while True:
            url = APIEndpoints.TEAMS_USER_SEARCH
            if skip_token:
                url += f"?skipToken={skip_token}"
            
            response = make_request('GET', url, headers=headers)
            
            if response.status_code != 200:
                p_err(f"Could not retrieve user list (HTTP {response.status_code})", True)
            
            users_response = response.json()
            users = users_response.get('users', [])
            skip_token = users_response.get('skipToken')
            
            for user in users:
                if user.get('id') == user_id:
                    sender_info = user
                    break
            
            if sender_info or not skip_token:
                break
        
        if not sender_info:
            p_err("Could not find sender's user information", True)
        
        # Extract tenant name from UPN
        upn = sender_info.get('userPrincipalName', '')
        if '@' in upn:
            domain_part = upn.split('@')[-1]
            tenant_name = domain_part.split('.')[0]
            sender_info['tenantName'] = tenant_name
        
        p_success("SUCCESS!")
        return sender_info
        
    except Exception as e:
        p_err(f"Error retrieving sender info: {str(e)}", True)

def authenticate(username, password):
    """Perform full authentication flow"""
    
    try:
        bearer_token = get_bearer_token(
            username,
            password,
            APIEndpoints.SCOPE_TEAMS
        )
        
        skype_token = get_skype_token(bearer_token)
        sender_info = get_sender_info(bearer_token)
        
        sharepoint_scope = {
            'tenantName': sender_info.get('tenantName', 'TenantName_')
        }
        sharepoint_token = get_bearer_token(username, password, sharepoint_scope)
        
        # CRITICAL: Clear password from memory
        password = None
        gc.collect()
        
        return bearer_token, skype_token, sharepoint_token, sender_info
        
    except Exception as e:
        p_err(f"Authentication failed: {str(e)}", True)

# ============================================================================
# USER ENUMERATION FUNCTIONS
# ============================================================================

def enum_user(bearer_token, email, verbose=False):
    """Enumerate target user information with rate limiting"""
    
    # Apply stealth delay
    time.sleep(get_random_delay())
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-Ms-Client-Version": "1415/1.0.0.2023031528"
    }
    
    try:
        url = f"{APIEndpoints.TEAMS_EXTERNAL_SEARCH}/{email}/externalsearchv3?includeTFLUsers=true"
        
        response = make_request('GET', url, headers=headers)
        
        if response.status_code == 401:
            p_err("Access token is invalid", True)
        
        if response.status_code == 403:
            # User found but communication restricted
            if verbose:
                print(f"\033[93m [-] BLOCKED\033[00m {email} (external domain disabled)")
            logging.warning(f"Access denied for {email} - external domain communication disabled")
            return None
        
        if response.status_code != 200 or len(response.text) < 3:
            # User not found or invalid
            if verbose:
                print(f"\033[94m [ ] INVALID\033[00m {email}")
            logging.debug(f"User {email} not found (HTTP {response.status_code})")
            stats['failed_enums'] += 1
            return None
        
        response_content = response.text
        
        try:
            user_data = json.loads(response_content)
            
            if isinstance(user_data, list):
                if not user_data:
                    return None
                user_data = user_data[0]
            
            user_info = {
                'email': email,
                'displayName': user_data.get('displayName', 'Unknown'),
                'objectId': user_data.get('objectId'),
                'userPrincipalName': user_data.get('userPrincipalName')
            }
            
            stats['successful_enums'] += 1
            return user_info
            
        except json.JSONDecodeError:
            logging.debug(f"Could not parse response for {email}")
            
            try:
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                matches = re.findall(json_pattern, response_content)
                
                if matches:
                    user_data = json.loads(matches[0])
                    user_info = {
                        'email': email,
                        'displayName': user_data.get('displayName', 'Unknown'),
                        'objectId': user_data.get('objectId'),
                        'userPrincipalName': user_data.get('userPrincipalName')
                    }
                    stats['successful_enums'] += 1
                    return user_info
            except:
                pass
            
            return None
        
    except requests.exceptions.RequestException as e:
        logging.warning(f"Network error for {email}: {sanitize_error_message(str(e))}")
        stats['failed_enums'] += 1
        return None

# ============================================================================
# BANNER & MAIN
# ============================================================================

BANNER = Fore.CYAN + r"""
██╗   ██╗████████╗███████╗ █████╗ ███╗   ███╗███████╗
██║   ██║╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██╔════╝
██║   ██║   ██║   █████╗  ███████║██╔████╔██║███████║
╚██╗ ██╔╝   ██║   ██╔══╝  ██╔══██║██║╚██╔╝██║╚════██║
 ╚████╔╝    ██║   ███████╗██║  ██║██║ ╚═╝ ██║███████║
  ╚═══╝     ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝
""" + Style.RESET_ALL + Fore.GREEN + f"""

        Microsoft Teams User Enumeration

        [ Tenant Discovery | Teams Enumeration ]

        Author : H0lmmes
        Target : Microsoft 365 / Teams
        Mode   : External User Enumeration (Stealth)

""" + Style.RESET_ALL

def main():
    """Main application flow"""
    print(BANNER)
    
    parser = argparse.ArgumentParser(
        description='vteams_userenum - Microsoft Teams User Enumeration Tool (Hardened)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""        
        Examples:

        Interactive (secure):
          python3 vteams_userenum.py -e target@company.com

        Single email with env vars:
          export TEAMS_USERNAME=user@corp.com
          export TEAMS_PASSWORD=password123
          python3 vteams_userenum.py -e target@company.com

        Email list:
          python3 vteams_userenum.py -L targets.txt

        With proxy:
          python3 vteams_userenum.py -e target@company.com --proxy socks5://127.0.0.1:9050

        With logging:
          python3 vteams_userenum.py -e target@company.com --log results.log
        """
    )
    
    parser.add_argument(
        '-u', '--username',
        dest='username',
        type=str,
        required=False,
        help='Username/email (or use TEAMS_USERNAME env var)'
    )
    
    parser.add_argument(
        '-p', '--password',
        dest='password',
        type=str,
        required=False,
        help='Password (or use TEAMS_PASSWORD env var) - WARNING: visible in process list!'
    )
    
    parser.add_argument(
        '-e', '--email',
        dest='email',
        type=str,
        required=False,
        help='Single target email address'
    )
    
    parser.add_argument(
        '-L', '--list',
        dest='list',
        type=str,
        required=False,
        help='File with target emails (one per line)'
    )
    
    parser.add_argument(
        '--log',
        dest='logfile',
        type=str,
        required=False,
        help='Log file path'
    )
    
    parser.add_argument(
        '--proxy',
        dest='proxy',
        type=str,
        required=False,
        help='Proxy URL (e.g., socks5://127.0.0.1:9050)'
    )
    
    parser.add_argument(
        '--no-verify-ssl',
        dest='no_verify_ssl',
        action='store_true',
        default=False,
        help='Disable SSL verification (NOT recommended)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_true',
        default=False,
        help='Show invalid users too (not just valid ones)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    if args.logfile:
        setup_logger(args.logfile)

    # Update SSL verification setting
    if args.no_verify_ssl:
        p_warn("SSL verification is DISABLED - vulnerable to MITM attacks!")
        CONFIG['verify_ssl'] = False
    
    # Update proxy settings
    if args.proxy:
        CONFIG['enable_proxy'] = True
        CONFIG['proxy_url'] = args.proxy
        p_info(f"Proxy enabled: {args.proxy}")
    
    # Get credentials (from args, env vars, or interactive prompt)
    username = args.username or os.getenv('TEAMS_USERNAME')
    password = args.password or os.getenv('TEAMS_PASSWORD')
    
    if args.password:
        p_warn("WARNING: Password in command line is visible to other processes!")
    
    username, password = get_credentials(username, password)
    
    # Build target list
    targets = []
    if args.email:
        targets = [args.email]
    elif args.list:
        p_task("Reading target email list...")
        try:
            with open(args.list) as f:
                targets = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            p_success(f"Loaded {len(targets)} targets")
        except IOError as e:
            p_err(f"Could not read email list: {str(e)}", True)
    else:
        p_err("You must specify either -e (email) or -L (list)", True)
    
    # Authenticate
    p_info("Initiating authentication flow...")
    bearer_token, skype_token, sharepoint_token, sender_info = authenticate(username, password)
    
    # Clear credentials from memory
    username = None
    password = None
    gc.collect()
    
    p_info(f"Authenticated as: {sender_info.get('displayName')}")
    
    # Enumerate targets
    p_info(f"Enumerating {len(targets)} target(s)...")
    
    valid_users = []
    
    for i, target in enumerate(targets, 1):
        if "@" not in target:
            p_warn(f"[{i}/{len(targets)}] Invalid email format: {target}")
            continue
        
        user_info = enum_user(bearer_token, target, verbose=args.verbose)
        
        if user_info:
            result = f"{target} -- {user_info.get('displayName', 'Unknown')}"
            print(f"\033[92m [+] VALID\033[00m {result}")
            valid_users.append(user_info)
            
            # Write result with secure permissions
            write_result_safe("USERS_VALID_TEAMS.txt", result)
            
            if args.logfile:
                logging.info(f"VALID USER: {result}")
    
    # Summary
    elapsed_time = datetime.datetime.now() - stats['start_time']
    p_info(f"\n{'='*60}")
    p_info(f"Enumeration Summary:")
    p_info(f"  Total Requests: {stats['total_requests']}")
    p_info(f"  Valid Users Found: {stats['successful_enums']}")
    p_info(f"  Failed Enumerations: {stats['failed_enums']}")
    p_info(f"  Elapsed Time: {elapsed_time.total_seconds():.2f}s")
    p_info(f"{'='*60}")
    
    if fd:
        fd.close()

if __name__ == "__main__":
    main()
