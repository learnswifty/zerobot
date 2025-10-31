#!/usr/bin/env python3
"""
Kite Connect Authentication Helper
==================================
This script helps you authenticate with Zerodha Kite Connect API
and generate the access token needed for trading.

The authentication process:
1. Create an app on Kite Connect developer portal
2. Get API Key and API Secret
3. Run this script to complete the authentication flow
4. Copy the access token to your .env file
"""

import os
import hashlib
import webbrowser
from urllib.parse import urlparse, parse_qs
from kiteconnect import KiteConnect
from dotenv import load_dotenv, set_key

# Load environment variables
load_dotenv()

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print a colored header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def get_setup_instructions():
    """Display setup instructions"""
    print_header("Kite Connect Setup Instructions")

    print(f"{Colors.BOLD}Step 1: Create a Kite Connect App{Colors.ENDC}")
    print("1. Visit: https://developers.kite.trade/")
    print("2. Sign in with your Zerodha credentials")
    print("3. Click 'Create new app' or use an existing app")
    print("4. Fill in the app details:")
    print("   - App name: Your choice (e.g., 'My Trading Bot')")
    print("   - Redirect URL: http://127.0.0.1:5000 (or any URL)")
    print("5. Click 'Create' to generate your credentials\n")

    print(f"{Colors.BOLD}Step 2: Get API Credentials{Colors.ENDC}")
    print("1. After creating the app, you'll see:")
    print("   - API Key (public)")
    print("   - API Secret (keep this secret!)")
    print("2. Copy both values\n")

    print(f"{Colors.BOLD}Step 3: Configure This Script{Colors.ENDC}")
    print("1. Create a .env file in this directory")
    print("2. Add your credentials:")
    print("   ZERODHA_API_KEY=your_api_key_here")
    print("   ZERODHA_API_SECRET=your_api_secret_here")
    print("   ZERODHA_REDIRECT_URL=http://127.0.0.1:5000")
    print("3. Run this script again\n")


def authenticate_kite_connect(api_key, api_secret, redirect_url):
    """
    Complete the Kite Connect authentication flow

    Args:
        api_key: Your Kite Connect API key
        api_secret: Your Kite Connect API secret
        redirect_url: Your registered redirect URL

    Returns:
        access_token or None
    """
    try:
        # Initialize Kite Connect
        kite = KiteConnect(api_key=api_key)

        # Generate login URL
        login_url = kite.login_url()

        print_info("Opening login page in your browser...")
        print(f"\n{Colors.BOLD}Login URL:{Colors.ENDC}")
        print(f"{login_url}\n")

        # Try to open browser automatically
        try:
            webbrowser.open(login_url)
            print_success("Browser opened successfully")
        except:
            print_warning("Could not open browser automatically")
            print("Please copy the URL above and open it manually")

        print(f"\n{Colors.BOLD}Instructions:{Colors.ENDC}")
        print("1. Complete the login in your browser")
        print("2. You'll be redirected to your redirect URL")
        print("3. Copy the ENTIRE URL from the browser's address bar")
        print("4. Paste it below\n")

        print_warning("Note: The URL will look like:")
        print(f"{redirect_url}?request_token=XXXXXX&action=login&status=success\n")

        # Get the redirect URL with request token
        redirect_response = input(f"{Colors.BOLD}Paste the redirect URL here:{Colors.ENDC} ").strip()

        # Parse the URL to extract request_token
        parsed_url = urlparse(redirect_response)
        params = parse_qs(parsed_url.query)

        if 'request_token' not in params:
            print_error("request_token not found in URL!")
            print("Make sure you copied the complete URL after login")
            return None

        request_token = params['request_token'][0]
        print_success(f"Request token extracted: {request_token[:20]}...")

        # Generate session
        print_info("Generating session...")
        data = kite.generate_session(request_token, api_secret=api_secret)

        access_token = data['access_token']
        user_name = data.get('user_name', 'User')
        user_id = data.get('user_id', '')

        print_success(f"Authentication successful!")
        print(f"\n{Colors.BOLD}User Details:{Colors.ENDC}")
        print(f"Name: {user_name}")
        print(f"User ID: {user_id}")
        print(f"\n{Colors.BOLD}Access Token:{Colors.ENDC}")
        print(f"{access_token}\n")

        # Save to .env file
        print_info("Saving access token to .env file...")
        env_file = '.env'
        set_key(env_file, 'ZERODHA_ACCESS_TOKEN', access_token)
        print_success("Access token saved to .env file")

        print_warning("\nIMPORTANT: Access tokens expire at the end of each trading day!")
        print_warning("You'll need to re-authenticate daily to get a new token.")

        return access_token

    except Exception as e:
        print_error(f"Authentication failed: {e}")
        return None


def verify_token(api_key, access_token):
    """Verify if the access token is valid"""
    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        print_info("Verifying access token...")
        profile = kite.profile()

        print_success("Token is valid!")
        print(f"\n{Colors.BOLD}Profile Information:{Colors.ENDC}")
        print(f"User: {profile['user_name']} ({profile['user_id']})")
        print(f"Email: {profile['email']}")
        print(f"Broker: {profile['broker']}")
        print(f"Exchanges: {', '.join(profile['exchanges'])}")
        print(f"Products: {', '.join(profile['products'])}")

        return True
    except Exception as e:
        print_error(f"Token verification failed: {e}")
        return False


def main():
    """Main function"""
    print_header("Kite Connect Authentication Helper")

    # Check if credentials exist
    api_key = os.getenv('ZERODHA_API_KEY')
    api_secret = os.getenv('ZERODHA_API_SECRET')
    access_token = os.getenv('ZERODHA_ACCESS_TOKEN')
    redirect_url = os.getenv('ZERODHA_REDIRECT_URL', 'http://127.0.0.1:5000')

    # If no API key, show setup instructions
    if not api_key or not api_secret:
        print_warning("API credentials not found!")
        get_setup_instructions()
        return

    print_success("API credentials found")
    print(f"API Key: {api_key[:10]}...")

    # Menu
    print(f"\n{Colors.BOLD}What would you like to do?{Colors.ENDC}")
    print("1. Generate new access token (authenticate)")
    print("2. Verify existing access token")
    print("3. View setup instructions")
    print("4. Exit")

    choice = input(f"\n{Colors.BOLD}Enter your choice (1-4):{Colors.ENDC} ").strip()

    if choice == '1':
        # Generate new token
        print_header("Generate New Access Token")
        token = authenticate_kite_connect(api_key, api_secret, redirect_url)

        if token:
            print_success("\n✓ Authentication complete!")
            print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
            print("1. Your access token is saved in .env file")
            print("2. You can now run the trading bot: python zerodha_auto_trader.py")
            print("3. Remember to re-authenticate daily (tokens expire)")

    elif choice == '2':
        # Verify existing token
        if not access_token:
            print_error("No access token found in .env file")
            print("Please generate a new token first (Option 1)")
        else:
            print_header("Verify Access Token")
            verify_token(api_key, access_token)

    elif choice == '3':
        # Show instructions
        get_setup_instructions()

    elif choice == '4':
        print_info("Goodbye!")

    else:
        print_error("Invalid choice")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Operation cancelled by user{Colors.ENDC}")
    except Exception as e:
        print_error(f"An error occurred: {e}")