#!/usr/bin/python3


import argparse
import requests
import json
import os
import os.path
import sys
import re
import time
from msal import PublicClientApplication
from colorama import Back, Fore, Style
import datetime
from os.path import expanduser
import hashlib
import logging

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# User agent string for web requests
USERAGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"

# Microsoft Azure App ID for Teams/Skype authentication
# NOTE: This is the standard Office 365 app ID
TEAMS_CLIENT_ID = "1fec8e78-bce4-4aaf-ab1b-5451cc387264"

# API Endpoints - Updated for 2025
class APIEndpoints:
    """Updated Microsoft Teams and Skype API endpoints"""
    
    # Authentication endpoints
    OPENID_CONFIG = "https://login.microsoftonline.com/{domain}/.well-known/openid-configuration"
    AUTHORITY_BASE = "https://login.microsoftonline.com"
    
    # Token endpoints - Updated
    SKYPE_TOKEN_ENDPOINT = "https://authsvc.teams.microsoft.com/v1.0/authz"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    
    # Teams API endpoints - Updated
    TEAMS_API_EMEA = "https://teams.microsoft.com/api/mt/emea/beta"
    TEAMS_USERS_ENDPOINT = f"{TEAMS_API_EMEA}/users/tenants"
    TEAMS_USER_SEARCH = f"{TEAMS_API_EMEA}/users"
    TEAMS_EXTERNAL_SEARCH = f"{TEAMS_API_EMEA}/users"
    
    # SharePoint endpoints
    SHAREPOINT_BASE = "https://{tenant}-my.sharepoint.com"
    
    # Scope definitions
    SCOPE_TEAMS = "https://api.spaces.skype.com/.default"
    SCOPE_SHAREPOINT = "https://{sharepoint_url}/.default"

# File descriptor for logging
fd = None

# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

def setup_logger(log_file=None):
    """Initialize logger with optional file output"""
    global fd
    if log_file:
        fd = open(log_file, 'a')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def p_err(msg, exit_code=True):
    """Print error message"""
    output = Fore.RED + "[-] " + msg + Style.RESET_ALL
    print(output)
    if fd:
        p_file(output, True)
    if exit_code:
        sys.exit(-1)

def p_warn(msg):
    """Print warning message"""
    output = Fore.YELLOW + "[-] " + msg + Style.RESET_ALL
    print(output)
    if fd:
        p_file(output, True)

def p_success(msg):
    """Print success message"""
    output = Fore.GREEN + "[+] " + msg + Style.RESET_ALL
    print(output)
    if fd:
        p_file(output, True)

def p_info(msg):
    """Print info message"""
    output = Fore.CYAN + msg + Style.RESET_ALL
    print(output)
    if fd:
        p_file(output, True)

def p_task(msg):
    """Print task status (no newline)"""
    bufferlen = 75 - len(msg)
    output = msg + "." * bufferlen
    print(output, end="", flush=True)
    if fd:
        p_file(output, False)

def p_file(msg, newline):
    """Write message to log file"""
    if fd:
        fd.write(msg)
        if newline:
            fd.write("\n")
        fd.flush()

# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def get_tenant_id(username):
    """
    Retrieve Microsoft Tenant ID for the given username/email domain
    
    Args:
        username: Email address to extract domain from
        
    Returns:
        Tenant ID string
    """
    domain = username.split("@")[-1]
    p_task(f"Fetching tenant ID for domain {domain}...")
    
    try:
        response = requests.get(
            APIEndpoints.OPENID_CONFIG.format(domain=domain),
            timeout=10
        )
        
        if response.status_code != 200:
            p_err(f"Could not retrieve tenant ID for domain {domain} (HTTP {response.status_code})", True)
        
        json_content = response.json()
        tenant_id = json_content['authorization_endpoint'].split("/")[3]
        p_success("SUCCESS!")
        return tenant_id
        
    except requests.exceptions.RequestException as e:
        p_err(f"Network error retrieving tenant ID: {str(e)}", True)
    except (KeyError, IndexError) as e:
        p_err(f"Invalid response format when retrieving tenant ID: {str(e)}", True)

def two_fa_login(username, scope):
    """
    Perform device code authentication flow (for 2FA-enabled accounts)
    
    Args:
        username: User email address
        scope: OAuth scope to request
        
    Returns:
        Authentication result containing access token
    """
    tenant_id = get_tenant_id(username)
    
    app = PublicClientApplication(
        TEAMS_CLIENT_ID,
        authority=f"{APIEndpoints.AUTHORITY_BASE}/{tenant_id}"
    )
    
    try:
        # Initiate device code flow
        flow = app.initiate_device_flow(scopes=[scope])
        
        if "user_code" not in flow:
            p_err("Could not retrieve user code in authentication flow", True)
        
        p_warn(flow.get("message"))
        
    except Exception as e:
        p_err(f"Could not initiate device code authentication flow: {str(e)}", True)
    
    # Acquire token using device flow
    try:
        result = app.acquire_token_by_device_flow(flow)
        
        if "access_token" not in result:
            p_err(f"Failed to acquire token: {result.get('error_description', 'Unknown error')}", True)
        
        return result
        
    except Exception as e:
        p_err(f"Error during device flow authentication: {str(e)}", True)

def get_bearer_token(username, password, scope):
    """
    Get OAuth bearer token using username/password authentication
    
    Args:
        username: User email address
        password: User password
        scope: OAuth scope (string or dict for SharePoint)
        
    Returns:
        Access token string
    """
    # Handle SharePoint scope format
    if isinstance(scope, dict):
        p_task("Fetching Bearer token for SharePoint...")
        # Construct SharePoint scope from tenant name
        tenant_name = scope.get('tenantName')
        scope = f"https://{tenant_name}-my.sharepoint.com/.default"
    else:
        p_task("Fetching Bearer token for Teams...")
    
    tenant_id = get_tenant_id(username)
    
    app = PublicClientApplication(
        TEAMS_CLIENT_ID,
        authority=f"{APIEndpoints.AUTHORITY_BASE}/{tenant_id}"
    )
    
    try:
        # Attempt username/password authentication
        result = app.acquire_token_by_username_password(
            username,
            password,
            scopes=[scope]
        )
        
    except ValueError as e:
        error_msg = str(e.args[0]) if e.args else str(e)
        if "MSA accounts" in error_msg:
            p_warn("Username/Password authentication not supported for Microsoft accounts. Use device code flow.")
        p_err("Error acquiring token", True)
    
    # Check for token in response
    if "access_token" not in result:
        error_desc = result.get("error_description", "Unknown error")
        
        if "Invalid username or password" in error_desc:
            p_err("Invalid credentials entered", True)
        elif "device code has expired" in error_desc:
            p_err("The device code has expired. Please try again", True)
        elif "multi-factor authentication" in error_desc:
            p_warn("2FA required, initiating device code flow...")
            result = two_fa_login(username, scope)
        else:
            p_err(f"Authentication failed: {error_desc}", True)
    
    p_success("SUCCESS!")
    return result["access_token"]

def get_skype_token(bearer_token):
    """
    Retrieve Skype token from bearer token
    Updated endpoint: https://authsvc.teams.microsoft.com/v1.0/authz
    
    Args:
        bearer_token: Bearer token from get_bearer_token()
        
    Returns:
        Skype token string
    """
    p_task("Fetching Skype token...")
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": USERAGENT,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            APIEndpoints.SKYPE_TOKEN_ENDPOINT,
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            p_err(f"Error fetching Skype token: HTTP {response.status_code}", True)
        
        json_content = response.json()
        
        if "tokens" not in json_content:
            p_err("Could not retrieve Skype token from response", True)
        
        tokens = json_content.get("tokens", {})
        skype_token = tokens.get("skypeToken")
        
        if not skype_token:
            p_err("Skype token not found in response", True)
        
        p_success("SUCCESS!")
        
        # Also extract and store other useful data if available
        if "middleTier" in json_content:
            logging.info(f"Middle tier URL: {json_content['middleTier']}")
        
        return skype_token
        
    except requests.exceptions.RequestException as e:
        p_err(f"Network error fetching Skype token: {str(e)}", True)
    except json.JSONDecodeError as e:
        p_err(f"Invalid JSON in Skype token response: {str(e)}", True)

def get_sender_info(bearer_token):
    """
    Retrieve authenticated user information (sender info)
    
    Args:
        bearer_token: Bearer token for authenticated user
        
    Returns:
        Dictionary containing user information (displayName, userId, tenantName, etc.)
    """
    p_task("Fetching sender info...")
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": USERAGENT,
        "X-Ms-Client-Version": "1415/1.0.0.2023031528"
    }
    
    sender_info = None
    
    try:
        # Step 1: Get user ID and tenant name
        response = requests.get(
            APIEndpoints.TEAMS_USERS_ENDPOINT,
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            p_err(f"Could not retrieve sender's user ID (HTTP {response.status_code})", True)
        
        users_data = response.json()
        if not users_data or len(users_data) == 0:
            p_err("No user data returned from Teams API", True)
        
        user_id = users_data[0].get('userId')
        tenant_name = users_data[0].get('tenantName')
        
        if not user_id:
            p_err("Could not extract user ID from response", True)
        
        # Step 2: Find matching user by ID and get display name
        skip_token = None
        while True:
            url = APIEndpoints.TEAMS_USER_SEARCH
            if skip_token:
                url += f"?skipToken={skip_token}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                p_err(f"Could not retrieve user list (HTTP {response.status_code})", True)
            
            users_response = response.json()
            users = users_response.get('users', [])
            skip_token = users_response.get('skipToken')
            
            # Find matching user
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
        
    except requests.exceptions.RequestException as e:
        p_err(f"Network error retrieving sender info: {str(e)}", True)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        p_err(f"Error parsing sender info response: {str(e)}", True)

def authenticate(args):
    """
    Perform full authentication flow and retrieve all necessary tokens
    
    Args:
        args: Command line arguments containing username and password
        
    Returns:
        Tuple of (bearer_token, skype_token, sharepoint_token, sender_info)
    """
    if not args.username or not args.password:
        p_err("You must provide both username AND password!", True)
    
    try:
        # Get Teams bearer token
        bearer_token = get_bearer_token(
            args.username,
            args.password,
            APIEndpoints.SCOPE_TEAMS
        )
        
        # Get Skype token
        skype_token = get_skype_token(bearer_token)
        
        # Get sender information
        sender_info = get_sender_info(bearer_token)
        
        # Get SharePoint bearer token (construct scope with tenant name)
        sharepoint_scope = {
            'tenantName': sender_info.get('tenantName')
        }
        sharepoint_token = get_bearer_token(
            args.username,
            args.password,
            sharepoint_scope
        )
        
        return bearer_token, skype_token, sharepoint_token, sender_info
        
    except Exception as e:
        p_err(f"Authentication flow failed: {str(e)}", True)

# ============================================================================
# USER ENUMERATION FUNCTIONS
# ============================================================================

def enum_user(bearer_token, email):
    """
    Enumerate target user information
    
    Args:
        bearer_token: Bearer token for authenticated requests
        email: Target email to enumerate
        
    Returns:
        Dictionary with user info if found, None otherwise
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-Ms-Client-Version": "1415/1.0.0.2023031528",
        "User-Agent": USERAGENT
    }
    
    try:
        # Use external search endpoint
        url = f"{APIEndpoints.TEAMS_EXTERNAL_SEARCH}/{email}/externalsearchv3?includeTFLUsers=true"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 401:
            p_err("Unable to enumerate user. Access token is invalid", True)
        
        if response.status_code == 403:
            # User found but communication restricted
            p_warn(f"User exists but communication to external domain is disabled")
            return None
        
        if response.status_code != 200 or len(response.text) < 3:
            p_warn(f"User {email} not enumerated (does not exist or not Teams-enrolled)")
            return None
        
        # Parse response
        try:
            response_content = response.text
            # Remove JSON array brackets if present
            clean_content = response_content.strip('[]')
            user_data = json.loads(clean_content)
            
            # Extract user information
            user_info = {
                'email': email,
                'displayName': user_data.get('displayName', 'Unknown'),
                'objectId': user_data.get('objectId'),
                'userPrincipalName': user_data.get('userPrincipalName')
            }
            
            return user_info
            
        except json.JSONDecodeError:
            p_warn(f"Could not parse response for {email}")
            return None
        
    except requests.exceptions.RequestException as e:
        p_warn(f"Network error enumerating user {email}: {str(e)}")
        return None

# ============================================================================
# BANNER & MAIN
# ============================================================================
BANNER = Fore.CYAN + r"""
██╗   ██╗████████╗███████╗ █████╗ ███╗   ███╗███████╗
██║   ██║╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██╔════╝
██║   ██║   ██║   █████╗  ███████║██╔████╔██║███████╗
╚██╗ ██╔╝   ██║   ██╔══╝  ██╔══██║██║╚██╔╝██║╚════██║
 ╚████╔╝    ██║   ███████╗██║  ██║██║ ╚═╝ ██║███████║
  ╚═══╝     ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝
""" + Style.RESET_ALL + Fore.GREEN + f"""

        Microsoft Teams User Enumeration

        [ Tenant Discovery | Teams Enumeration ]

        Author : H0lmmes
        Target : Microsoft 365 / Teams
        Mode   : External User Enumeration

""" + Style.RESET_ALL

def main():
    """Main application flow"""
    print(BANNER)
    parser = argparse.ArgumentParser(
            description='vteams_userenum - Microsoft Teams User Enumeration Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:

        Single email:
          python3 vteams_userenum.py -u user@corp.com -p password -e target@company.com

        Email list:
          python3 vteams_userenum.py -u user@corp.com -p password -L targets.txt

        Specify tenant manually:
          python3 vteams_userenum.py -u user@corp.com -p password -e target@company.com -t contoso
        """
        )
    
    parser.add_argument(
        '-u', '--username',
        dest='username',
        type=str,
        required=True,
        help='Username/email for authentication'
    )
    
    parser.add_argument(
        '-p', '--password',
        dest='password',
        type=str,
        required=True,
        help='Password for authentication'
    )



    parser.add_argument(
        '-l', '--log',
        dest='logfile',
        type=str,
        required=False,
        help='Log file path (optional)'
    )
    
    # Target selection group
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        '-e', '--email',
        dest='email',
        type=str,
        help='Single target email address'
    )
    target_group.add_argument(
    '-L', '--list',
    dest='list',
    type=str,
    help='File with target emails (one per line)'
)

    
    args = parser.parse_args()
    
    # Setup logging
    if args.logfile:
        setup_logger(args.logfile)
    
    # Build target list
    targets = []
    if args.email:
        targets = [args.email]
    else:
        p_task("Reading target email list...")
        try:
            with open(args.list) as f:
                targets = [line.strip() for line in f if line.strip()]
            p_success(f"Loaded {len(targets)} targets")
        except IOError as e:
            p_err(f"Could not read email list: {str(e)}", True)
    
    # Authenticate
    p_info("Initiating authentication flow...")
    bearer_token, skype_token, sharepoint_token, sender_info = authenticate(args)
    
    p_info(f"Authenticated as: {sender_info.get('displayName')} ({sender_info.get('userPrincipalName')})")
    
    # Enumerate targets
    p_info(f"Enumerating {len(targets)} target(s)...")
    
    valid_users = []
    
    for target in targets:
        if "@" not in target:
            p_warn(f"Invalid email format: {target}")
            continue
        
        user_info = enum_user(bearer_token, target)
        
        if user_info:
            result = f"{target} -- {user_info.get('displayName', 'Unknown')}"
            print(f"\033[92m [+] VALID\033[00m {result}")
            
            valid_users.append(user_info)
            
            # Log to file if specified
            if args.logfile:
                with open("USERS_VALID_TEAMS.txt", 'a') as f:
                    f.write(result + '\n')
    
    # Summary
    p_info(f"Enumeration complete. Found {len(valid_users)} valid users out of {len(targets)} targets")
    
    if fd:
        fd.close()

if __name__ == "__main__":
    main()
