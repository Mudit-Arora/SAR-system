#!/usr/bin/env python3
"""
Voice Agent Setup Wizard

Configures Twilio and optionally deploys to Fly.io in one guided flow.
No Twilio web console or manual webhook configuration needed.

Usage:
  python setup.py                    # Full setup: Twilio + Fly.io deploy
  python setup.py --twilio-only      # Just Twilio config (bring your own URL)
  python setup.py --update-url URL   # Quick webhook URL update
  python setup.py --status           # Show current configuration
  python setup.py --teardown         # Destroy Fly.io app (keep Twilio number)

Prerequisites:
  - Deepgram API key in .env
  - Twilio Account SID and Auth Token (from https://console.twilio.com)
  - flyctl installed and authenticated (for Fly.io deploy, not needed for --twilio-only)
"""
import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATE_FILE = ".setup_state.json"
ENV_FILE = ".env"
ENV_EXAMPLE_FILE = ".env.example"

# ---------------------------------------------------------------------------
# Utility: console output
# ---------------------------------------------------------------------------

def print_header(text: str):
    print(f"\n  {text}")
    print(f"  {'=' * len(text)}")

def print_section(text: str):
    print(f"\n  ─── {text} {'─' * max(0, 43 - len(text))}")

def print_step(text: str):
    print(f"\n  {text}")
    print(f"  {'-' * len(text)}")

def print_ok(text: str):
    print(f"  {text}")

def print_error(text: str):
    print(f"\n  Error: {text}", file=sys.stderr)

def print_warn(text: str):
    print(f"  Note: {text}")


# ---------------------------------------------------------------------------
# Utility: user input
# ---------------------------------------------------------------------------

def prompt(label: str, default: str = "") -> str:
    """Prompt the user for input with an optional default."""
    if default:
        raw = input(f"  {label} [{default}]: ").strip()
        return raw if raw else default
    return input(f"  {label}: ").strip()


def prompt_secret(label: str) -> str:
    """Prompt for sensitive input (not echoed)."""
    return getpass.getpass(f"  {label}: ")


def prompt_choice(options: list[str], default: int = 1) -> int:
    """Display numbered options and return the chosen index (1-based)."""
    print()
    for i, option in enumerate(options, 1):
        print(f"    {i}. {option}")
    print()
    while True:
        raw = input(f"  Choice [{default}]: ").strip()
        if not raw:
            return default
        try:
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}.")


def prompt_confirm(text: str, default_yes: bool = False) -> bool:
    """Ask a yes/no question. Returns True for yes."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    raw = input(f"  {text} {suffix}: ").strip().lower()
    if not raw:
        return default_yes
    return raw in ("y", "yes")


# ---------------------------------------------------------------------------
# Utility: phone number formatting
# ---------------------------------------------------------------------------

def format_phone(number: str) -> str:
    """Format E.164 number as readable: +14155550123 → +1 (415) 555-0123"""
    if number.startswith("+1") and len(number) == 12:
        return f"+1 ({number[2:5]}) {number[5:8]}-{number[8:]}"
    return number


# ---------------------------------------------------------------------------
# State management (.setup_state.json)
# ---------------------------------------------------------------------------

def load_state() -> dict | None:
    """Load wizard state from disk, or None if not configured."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_state(state: dict):
    """Write wizard state to disk."""
    state["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    if "created_at" not in state:
        state["created_at"] = state["last_updated_at"]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# .env file management
# ---------------------------------------------------------------------------

def read_env_file() -> str:
    """Read .env contents, creating from .env.example if needed."""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            return f.read()
    if os.path.exists(ENV_EXAMPLE_FILE):
        with open(ENV_EXAMPLE_FILE) as f:
            content = f.read()
        with open(ENV_FILE, "w") as f:
            f.write(content)
        return content
    # Create a minimal .env
    content = "# Created by setup.py\n"
    with open(ENV_FILE, "w") as f:
        f.write(content)
    return content


def get_env_value(key: str) -> str | None:
    """Read a specific value from the .env file (not os.environ)."""
    content = read_env_file()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


def update_env_file(updates: dict[str, str]):
    """Update key=value pairs in .env. In-place for existing keys, append for new."""
    content = read_env_file()
    lines = content.splitlines()
    updated_keys = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            updated_keys.add(key)

    # Append any keys that weren't already in the file
    new_keys = set(updates.keys()) - updated_keys
    if new_keys:
        if lines and lines[-1].strip():
            lines.append("")  # blank separator
        for key in sorted(new_keys):
            lines.append(f"{key}={updates[key]}")

    with open(ENV_FILE, "w") as f:
        f.write("\n".join(lines))
        if not lines[-1].endswith("\n"):
            f.write("\n")


# ---------------------------------------------------------------------------
# Twilio: credential handling
# ---------------------------------------------------------------------------

def get_twilio_client():
    """Get or prompt for Twilio credentials, validate them, return a Client.

    Returns (client, account_sid, auth_token, account_type).
    """
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException

    # Check for existing credentials in .env
    existing_sid = get_env_value("TWILIO_ACCOUNT_SID")
    existing_token = get_env_value("TWILIO_AUTH_TOKEN")

    account_sid = None
    auth_token = None

    if existing_sid and existing_token:
        print_ok(f"Found Twilio credentials in .env (Account: {existing_sid[:8]}...)")
        if prompt_confirm("Use existing credentials?", default_yes=True):
            account_sid = existing_sid
            auth_token = existing_token

    if not account_sid:
        print()
        print_ok("You'll need your Account SID and Auth Token from:")
        print_ok("https://console.twilio.com")
        print()
        account_sid = prompt("Account SID")
        auth_token = prompt_secret("Auth Token")

    if not account_sid or not auth_token:
        print_error("Account SID and Auth Token are required.")
        sys.exit(1)

    # Validate
    print()
    sys.stdout.write("  Validating credentials... ")
    sys.stdout.flush()
    try:
        client = Client(account_sid, auth_token)
        account = client.api.accounts(account_sid).fetch()
        account_type = getattr(account, "type", "Unknown")
        friendly_name = getattr(account, "friendly_name", "")
        print(f'OK ("{friendly_name}", {account_type})')

        if account_type == "Trial":
            print_warn("Trial accounts play a Twilio disclaimer before connecting callers.")
            print_ok("  Upgrade at https://console.twilio.com to remove it.")

        return client, account_sid, auth_token, account_type

    except TwilioRestException:
        print("FAILED")
        print_error("Could not authenticate. Check your Account SID and Auth Token.")
        print_ok("  Find them at https://console.twilio.com")
        sys.exit(1)
    except Exception as e:
        print("FAILED")
        print_error(f"Could not reach Twilio API: {e}")
        print_ok("  Check your internet connection.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Twilio: phone number selection
# ---------------------------------------------------------------------------

def select_phone_number(client) -> tuple[str, str, bool]:
    """List voice-capable numbers and let the user pick one, or purchase new.

    Returns (phone_number, phone_number_sid, provisioned_by_wizard).
    """
    from twilio.base.exceptions import TwilioRestException

    print_step("Phone Number") if not hasattr(select_phone_number, '_called') else None

    sys.stdout.write("  Fetching your phone numbers... ")
    sys.stdout.flush()
    numbers = client.incoming_phone_numbers.list()
    voice_numbers = [n for n in numbers if getattr(n, "capabilities", {}).get("voice", False)]
    print("OK")

    options = []
    for n in voice_numbers:
        label = format_phone(n.phone_number)
        if n.friendly_name and n.friendly_name != n.phone_number:
            label += f'  "{n.friendly_name}"'
        options.append(label)

    options.append("Search for a new number to purchase")

    if voice_numbers:
        print()
        print_ok("Your Twilio account has these voice-capable numbers:")
    else:
        print()
        print_ok("Your Twilio account has no voice-capable numbers.")

    choice = prompt_choice(options, default=1)

    if choice <= len(voice_numbers):
        selected = voice_numbers[choice - 1]
        print_ok(f"  Selected: {format_phone(selected.phone_number)}")
        return selected.phone_number, selected.sid, False
    else:
        number, sid = search_and_purchase(client)
        return number, sid, True


def search_and_purchase(client) -> tuple[str, str]:
    """Search for available numbers and purchase one.

    Returns (phone_number, phone_number_sid).
    """
    from twilio.base.exceptions import TwilioRestException

    area_code = prompt("Search by area code (or press Enter to skip)")

    sys.stdout.write("  Searching... ")
    sys.stdout.flush()

    kwargs = {"limit": 5}
    if area_code:
        kwargs["area_code"] = area_code

    try:
        available = client.available_phone_numbers("US").local.list(**kwargs)
    except TwilioRestException as e:
        print("FAILED")
        print_error(f"Could not search for numbers: {e}")
        sys.exit(1)

    if not available:
        print("no results")
        print_error("No numbers found. Try a different area code.")
        sys.exit(1)

    print(f"found {len(available)}")
    print()
    print_ok("  Available numbers:")

    options = []
    for n in available:
        label = format_phone(n.phone_number)
        locality = getattr(n, "locality", "")
        region = getattr(n, "region", "")
        if locality and region:
            label += f"  {locality}, {region}"
        options.append(label)

    choice = prompt_choice(options, default=1)
    selected = available[choice - 1]

    print()
    if not prompt_confirm(
        f"Purchase {format_phone(selected.phone_number)}?",
        default_yes=False,
    ):
        print_ok("  Purchase cancelled.")
        sys.exit(0)

    sys.stdout.write("  Purchasing... ")
    sys.stdout.flush()
    try:
        purchased = client.incoming_phone_numbers.create(
            phone_number=selected.phone_number
        )
        print("OK")
        print_ok(f"  Number {format_phone(purchased.phone_number)} is now yours.")
        return purchased.phone_number, purchased.sid
    except TwilioRestException as e:
        print("FAILED")
        error_msg = str(e)
        if "balance" in error_msg.lower() or "fund" in error_msg.lower():
            print_error("Your Twilio account balance is too low to purchase a number.")
            print_ok("  Add funds at https://console.twilio.com")
        else:
            print_error(f"Could not purchase number: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Twilio: webhook configuration
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """Validate and normalize a server URL. Returns the cleaned URL or exits."""
    url = url.strip().rstrip("/")

    if url.startswith("http://localhost") or url.startswith("http://127."):
        print_error("Twilio can't reach localhost. Use a tunnel URL or deployed server URL.")
        sys.exit(1)

    if not url.startswith("https://"):
        print_error("Twilio requires HTTPS. Your URL should start with https://")
        sys.exit(1)

    # Remove any path - we'll append /incoming-call ourselves
    parsed_host = url.split("//", 1)[1].split("/")[0]
    return f"https://{parsed_host}"


def configure_webhook(client, phone_number_sid: str, server_url: str, webhook_secret: str | None = None):
    """Set the voice webhook URL on a Twilio phone number."""
    from twilio.base.exceptions import TwilioRestException

    # Build the webhook URL
    webhook_path = "/incoming-call"
    if webhook_secret:
        webhook_path = f"/incoming-call/{webhook_secret}"
    webhook_url = f"{server_url}{webhook_path}"

    sys.stdout.write("  Configuring webhook... ")
    sys.stdout.flush()
    try:
        client.incoming_phone_numbers(phone_number_sid).update(
            voice_url=webhook_url,
            voice_method="POST",
        )

        # Verify it stuck
        updated = client.incoming_phone_numbers(phone_number_sid).fetch()
        if updated.voice_url == webhook_url:
            print("OK")
            print_ok(f"  Webhook set: {webhook_url}")
        else:
            print("OK (set, but verify manually)")

        return webhook_url

    except TwilioRestException as e:
        print("FAILED")
        print_error(f"Could not configure webhook: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Fly.io: prerequisite checks
# ---------------------------------------------------------------------------

def check_flyctl() -> str | None:
    """Check if flyctl is installed. Returns version string or None."""
    flyctl = shutil.which("flyctl") or shutil.which("fly")
    if not flyctl:
        return None
    try:
        result = subprocess.run(
            [flyctl, "version"],
            capture_output=True, text=True, timeout=10,
        )
        # Extract version from output like "flyctl v0.3.45 ..."
        version = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
        return version
    except (subprocess.TimeoutExpired, OSError):
        return None


def check_fly_auth() -> str | None:
    """Check if the user is authenticated with Fly.io. Returns email or None."""
    flyctl = shutil.which("flyctl") or shutil.which("fly")
    if not flyctl:
        return None
    try:
        result = subprocess.run(
            [flyctl, "auth", "whoami"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def get_flyctl() -> str:
    """Get the flyctl binary name. Exits if not found."""
    flyctl = shutil.which("flyctl") or shutil.which("fly")
    if not flyctl:
        print_error("flyctl is not installed.")
        print_ok("  Install it: https://fly.io/docs/flyctl/install/")
        print_ok("  Or run with --twilio-only to skip Fly.io deployment.")
        sys.exit(1)
    return flyctl


# ---------------------------------------------------------------------------
# Fly.io: deployment
# ---------------------------------------------------------------------------

def fly_launch(flyctl: str) -> str:
    """Create a new Fly.io app (auto-named). Returns the app name."""
    sys.stdout.write("  Creating app... ")
    sys.stdout.flush()
    try:
        result = subprocess.run(
            [
                flyctl, "launch",
                "--no-deploy",
                "--copy-config",
                "--yes",
                "--generate-name",
                "--region", "iad",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print("FAILED")
            print_error(f"flyctl launch failed:\n{result.stderr}")
            sys.exit(1)

        # Parse app name from fly.toml that flyctl just updated
        app_name = _read_app_from_fly_toml()
        if not app_name:
            # Try parsing from output
            for line in result.stdout.splitlines():
                if "app" in line.lower() and "created" in line.lower():
                    # e.g. "Created app 'wispy-fog-1234' in organization 'personal'"
                    match = re.search(r"'([^']+)'", line)
                    if match:
                        app_name = match.group(1)
                        break

        if not app_name:
            print("FAILED")
            print_error("Could not determine the app name. Check flyctl output.")
            sys.exit(1)

        print(f"OK ({app_name})")
        return app_name

    except subprocess.TimeoutExpired:
        print("FAILED")
        print_error("flyctl launch timed out.")
        sys.exit(1)


def _read_app_from_fly_toml() -> str | None:
    """Read the app name from fly.toml (set by fly launch)."""
    if not os.path.exists("fly.toml"):
        return None
    with open("fly.toml") as f:
        for line in f:
            line = line.strip()
            if line.startswith("app"):
                # app = "wispy-fog-1234" or app = 'wispy-fog-1234'
                match = re.search(r'''['"]([^'"]+)['"]''', line)
                if match:
                    return match.group(1)
    return None


def fly_set_secrets(flyctl: str, app_name: str, secrets_dict: dict[str, str]):
    """Set secrets on the Fly.io app."""
    sys.stdout.write("  Setting secrets... ")
    sys.stdout.flush()

    args = [flyctl, "secrets", "set", "--app", app_name, "--stage"]
    for key, value in secrets_dict.items():
        args.append(f"{key}={value}")

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print("FAILED")
            print_error(f"Could not set secrets:\n{result.stderr}")
            sys.exit(1)
        print("OK")
    except subprocess.TimeoutExpired:
        print("FAILED")
        print_error("flyctl secrets set timed out.")
        sys.exit(1)


def fly_deploy(flyctl: str, app_name: str):
    """Deploy the app to Fly.io, streaming progress to the terminal."""
    print("  Deploying to Fly.io...")
    print()

    # Milestone keywords from flyctl deploy output -> friendly labels
    _milestones = [
        ("Building image",           "  Building Docker image..."),
        ("pushing image",            "  Pushing image..."),
        ("Updating machines",        "  Updating machines..."),
        ("Waiting for",              "  Waiting for health checks..."),
        ("finished deploying",       None),  # handled by success message
    ]
    seen = set()

    try:
        proc = subprocess.Popen(
            [flyctl, "deploy", "--app", app_name, "--yes"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        for line in proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            # Print milestone lines as friendly progress
            for keyword, label in _milestones:
                if keyword.lower() in stripped.lower() and keyword not in seen:
                    seen.add(keyword)
                    if label:
                        print(label)
                    break

        proc.wait(timeout=600)

        if proc.returncode != 0:
            print()
            print_error(f"Deployment failed (exit code {proc.returncode}).")
            print_error("Run `flyctl logs` or `flyctl deploy` manually for details.")
            sys.exit(1)
        print("  Deploy complete!")
        print()
    except subprocess.TimeoutExpired:
        proc.kill()
        print()
        print_error("Deployment timed out (>10 min). Check status with: flyctl status")
        sys.exit(1)


def fly_destroy(flyctl: str, app_name: str):
    """Destroy a Fly.io app."""
    sys.stdout.write("  Destroying Fly.io app... ")
    sys.stdout.flush()
    try:
        result = subprocess.run(
            [flyctl, "apps", "destroy", app_name, "--yes"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print("FAILED")
            print_error(f"Could not destroy app:\n{result.stderr}")
            return False
        print("OK")
        return True
    except subprocess.TimeoutExpired:
        print("FAILED")
        print_error("flyctl destroy timed out.")
        return False


# ---------------------------------------------------------------------------
# Modes: first-time full setup
# ---------------------------------------------------------------------------

def run_full_setup(twilio_only: bool = False):
    """Run the full first-time setup wizard."""
    print_header("Voice Agent Setup" + (" (Twilio Only)" if twilio_only else ""))

    print()
    print_ok("This will configure Twilio" + ("." if twilio_only else " and deploy your voice agent."))

    # Check DEEPGRAM_API_KEY
    dg_key = get_env_value("DEEPGRAM_API_KEY")
    has_dg = bool(dg_key and dg_key != "your_key_here" and dg_key.strip())

    if not has_dg:
        print()
        print_ok("You'll need a Deepgram API key.")
        print_ok("Get a free key at https://console.deepgram.com")
        print()
        dg_key = prompt_secret("Deepgram API Key")
        if not dg_key or not dg_key.strip():
            print_error("Deepgram API key is required.")
            sys.exit(1)
        dg_key = dg_key.strip()
        update_env_file({"DEEPGRAM_API_KEY": dg_key})
        has_dg = True

    # --- Twilio ---
    print_section("Twilio")

    client, account_sid, auth_token, account_type = get_twilio_client()
    phone_number, phone_number_sid, provisioned_by_wizard = select_phone_number(client)

    # --- Deploy or manual URL ---
    webhook_secret = None
    server_url = None
    app_name = None
    flyio_state = None

    if twilio_only:
        # Prompt for server URL
        print_step("Server URL")
        print_ok("Enter the public URL where your server is reachable.")
        print_ok("This is your tunnel URL (e.g. https://xyz.ngrok.io) or")
        print_ok("production domain (e.g. https://voice.example.com).")
        print()
        raw_url = prompt("Server URL")
        server_url = validate_url(raw_url)
    else:
        # Fly.io deploy
        print_section("Deploy")

        flyctl = get_flyctl()

        version = check_flyctl()
        print_ok(f"Checking flyctl... OK ({version})")

        auth_email = check_fly_auth()
        if not auth_email:
            print_error("Not logged into Fly.io. Run: flyctl auth login")
            sys.exit(1)
        print_ok(f"Checking auth... OK ({auth_email})")

        # Generate webhook secret
        webhook_secret = secrets.token_urlsafe(16)

        # Create app
        app_name = fly_launch(flyctl)
        server_url = f"https://{app_name}.fly.dev"

        # Set secrets
        fly_secrets = {
            "DEEPGRAM_API_KEY": dg_key,
            "TWILIO_ACCOUNT_SID": account_sid,
            "TWILIO_AUTH_TOKEN": auth_token,
            "TWILIO_PHONE_NUMBER": phone_number,
            "WEBHOOK_SECRET": webhook_secret,
            "SERVER_EXTERNAL_URL": server_url,
        }
        fly_set_secrets(flyctl, app_name, fly_secrets)

        # Deploy
        fly_deploy(flyctl, app_name)

        flyio_state = {
            "app_name": app_name,
            "app_url": server_url,
            "region": "iad",
            "webhook_secret": webhook_secret,
        }

    # --- Configure webhook ---
    print_section("Webhook")
    webhook_url = configure_webhook(client, phone_number_sid, server_url, webhook_secret)

    # --- Save state ---
    state = {
        "twilio": {
            "account_sid": account_sid,
            "phone_number": phone_number,
            "phone_number_sid": phone_number_sid,
            "webhook_url": webhook_url,
            "provisioned_by_wizard": provisioned_by_wizard,
        },
    }
    if flyio_state:
        state["flyio"] = flyio_state
    save_state(state)

    # --- Update .env ---
    env_updates = {
        "TWILIO_ACCOUNT_SID": account_sid,
        "TWILIO_AUTH_TOKEN": auth_token,
        "TWILIO_PHONE_NUMBER": phone_number,
        "SERVER_EXTERNAL_URL": server_url,
    }
    if webhook_secret:
        env_updates["WEBHOOK_SECRET"] = webhook_secret
    update_env_file(env_updates)

    # --- Done! ---
    print_section("Done!")
    print()
    print_ok(f"Phone number:  {format_phone(phone_number)}")
    if app_name:
        print_ok(f"Deployed to:   {server_url}")
    print_ok(f"Webhook URL:   {webhook_url}")
    print()

    if twilio_only:
        print_ok("Start your server with: python main.py")
        print_ok(f"Then call {format_phone(phone_number)} to talk to your agent!")
    else:
        print_ok(f"Call {format_phone(phone_number)} to talk to your agent!")
        print_ok(f"View logs:     flyctl logs --app {app_name}")
    print()


# ---------------------------------------------------------------------------
# Modes: re-run menu
# ---------------------------------------------------------------------------

def _validate_state(state: dict) -> dict:
    """Run lightweight health checks on stored state. Returns a dict of warnings."""
    warnings = {}

    twilio_state = state.get("twilio", {})
    flyio_state = state.get("flyio", {})

    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    phone_number_sid = twilio_state.get("phone_number_sid")

    # Check Twilio credentials and phone number
    if account_sid and auth_token and phone_number_sid:
        try:
            from twilio.rest import Client
            from twilio.base.exceptions import TwilioRestException
            client = Client(account_sid, auth_token)
            client.incoming_phone_numbers(phone_number_sid).fetch()
        except TwilioRestException:
            warnings["twilio_number"] = (
                f"Phone number {format_phone(twilio_state.get('phone_number', 'unknown'))} "
                f"may no longer be active on your Twilio account."
            )
        except Exception:
            warnings["twilio_auth"] = "Could not reach Twilio API to verify configuration."
    elif not account_sid or not auth_token:
        warnings["twilio_creds"] = "Twilio credentials not found in .env."

    # Check Fly.io app
    if flyio_state:
        app_name = flyio_state.get("app_name")
        if app_name:
            flyctl = shutil.which("flyctl") or shutil.which("fly")
            if flyctl:
                try:
                    result = subprocess.run(
                        [flyctl, "status", "--app", app_name],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode != 0:
                        warnings["flyio_app"] = (
                            f"Fly.io app '{app_name}' may no longer exist. "
                            f"Consider starting fresh."
                        )
                except (subprocess.TimeoutExpired, OSError):
                    pass  # Can't check - not a hard failure

    return warnings


def run_rerun_menu(state: dict):
    """Show the re-run menu when existing config is detected."""
    print_header("Voice Agent Setup")

    # Run health checks
    sys.stdout.write("\n  Verifying configuration... ")
    sys.stdout.flush()
    warnings = _validate_state(state)
    if warnings:
        print("issues found")
        for warning in warnings.values():
            print_warn(warning)
    else:
        print("OK")

    twilio_state = state.get("twilio", {})
    flyio_state = state.get("flyio", {})

    print()
    print_ok("Current configuration:")
    print_ok(f"  Phone number:  {format_phone(twilio_state.get('phone_number', 'unknown'))}")
    if flyio_state:
        print_ok(f"  Deployed to:   {flyio_state.get('app_url', 'unknown')}")
    print_ok(f"  Webhook:       {twilio_state.get('webhook_url', 'unknown')}")

    options = []
    if flyio_state:
        options.append("Redeploy (push latest code to Fly.io)")
    options.append("Update the webhook URL (e.g., tunnel URL changed)")
    options.append("Switch to a different phone number")
    options.append("Start fresh (reconfigure everything)")
    options.append("Exit (no changes)")

    choice = prompt_choice(options, default=1)
    chosen_label = options[choice - 1]

    if "Redeploy" in chosen_label:
        handle_redeploy(state)
    elif "Update the webhook" in chosen_label:
        handle_update_url_interactive(state)
    elif "Switch" in chosen_label:
        handle_switch_number(state)
    elif "Start fresh" in chosen_label:
        run_full_setup(twilio_only=not bool(flyio_state))
    else:
        print()
        print_ok("No changes made.")


def handle_redeploy(state: dict):
    """Redeploy current code to Fly.io."""
    flyio_state = state.get("flyio", {})
    app_name = flyio_state.get("app_name")
    if not app_name:
        print_error("No Fly.io app found in state.")
        return

    flyctl = get_flyctl()
    print()
    fly_deploy(flyctl, app_name)
    print()
    print_ok("Done! Your agent is updated.")
    print_ok(f"View logs: flyctl logs --app {app_name}")


def handle_update_url_interactive(state: dict):
    """Prompt for a new URL and update the webhook."""
    twilio_state = state.get("twilio", {})
    phone_number_sid = twilio_state.get("phone_number_sid")
    if not phone_number_sid:
        print_error("No phone number SID in state. Run setup again.")
        return

    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        print_error("Twilio credentials not found in .env. Run setup again.")
        return

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    print()
    raw_url = prompt("New server URL")
    server_url = validate_url(raw_url)
    print()

    webhook_url = configure_webhook(client, phone_number_sid, server_url)

    # Update state
    state["twilio"]["webhook_url"] = webhook_url
    save_state(state)

    # Update .env
    update_env_file({"SERVER_EXTERNAL_URL": server_url})

    print()
    print_ok(f"Updated .env and {STATE_FILE}.")


def handle_switch_number(state: dict):
    """Switch to a different phone number."""
    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        print_error("Twilio credentials not found in .env. Run setup again.")
        return

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    phone_number, phone_number_sid, provisioned_by_wizard = select_phone_number(client)

    flyio_state = state.get("flyio", {})
    webhook_secret = flyio_state.get("webhook_secret")

    # Determine server URL
    if flyio_state:
        server_url = flyio_state.get("app_url")
    else:
        server_url = get_env_value("SERVER_EXTERNAL_URL")

    if not server_url:
        print()
        raw_url = prompt("Server URL")
        server_url = validate_url(raw_url)

    print()
    webhook_url = configure_webhook(client, phone_number_sid, server_url, webhook_secret)

    # Update state
    state["twilio"]["phone_number"] = phone_number
    state["twilio"]["phone_number_sid"] = phone_number_sid
    state["twilio"]["webhook_url"] = webhook_url
    state["twilio"]["provisioned_by_wizard"] = provisioned_by_wizard
    save_state(state)

    # Update .env
    update_env_file({"TWILIO_PHONE_NUMBER": phone_number})

    print()
    print_ok(f"Updated .env and {STATE_FILE}.")


# ---------------------------------------------------------------------------
# Modes: quick URL update (--update-url)
# ---------------------------------------------------------------------------

def quick_update_url(new_url: str):
    """Quick webhook URL update without the TUI."""
    state = load_state()
    if not state:
        print_error(f"No existing configuration found ({STATE_FILE} missing).")
        print_ok("  Run `python setup.py` first for initial setup.")
        sys.exit(1)

    twilio_state = state.get("twilio", {})
    phone_number = twilio_state.get("phone_number", "unknown")
    phone_number_sid = twilio_state.get("phone_number_sid")

    if not phone_number_sid:
        print_error("No phone number SID in state. Run `python setup.py` to reconfigure.")
        sys.exit(1)

    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        print_error("Twilio credentials not found in .env.")
        sys.exit(1)

    server_url = validate_url(new_url)

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    print()
    sys.stdout.write(f"  Updating webhook for {format_phone(phone_number)}... ")
    sys.stdout.flush()

    webhook_url = configure_webhook(client, phone_number_sid, server_url)

    state["twilio"]["webhook_url"] = webhook_url
    save_state(state)
    update_env_file({"SERVER_EXTERNAL_URL": server_url})

    print_ok(f"  Updated .env and {STATE_FILE}.")


# ---------------------------------------------------------------------------
# Modes: status
# ---------------------------------------------------------------------------

def show_status():
    """Show current configuration with health checks."""
    state = load_state()
    if not state:
        print()
        print_ok("No configuration found. Run `python setup.py` to get started.")
        return

    print_header("Voice Agent Status")

    twilio_state = state.get("twilio", {})
    flyio_state = state.get("flyio", {})

    print()
    print_ok(f"Phone number:  {format_phone(twilio_state.get('phone_number', 'not set'))}")
    print_ok(f"Webhook URL:   {twilio_state.get('webhook_url', 'not set')}")
    print_ok(f"Account SID:   {twilio_state.get('account_sid', 'not set')}")

    if flyio_state:
        print()
        print_ok(f"Fly.io app:    {flyio_state.get('app_name', 'not set')}")
        print_ok(f"Fly.io URL:    {flyio_state.get('app_url', 'not set')}")
        print_ok(f"Region:        {flyio_state.get('region', 'not set')}")

    print()
    print_ok(f"Last updated:  {state.get('last_updated_at', 'unknown')}")

    # Health checks
    sys.stdout.write("\n  Verifying... ")
    sys.stdout.flush()
    warnings = _validate_state(state)
    if warnings:
        print("issues found")
        for warning in warnings.values():
            print_warn(warning)
    else:
        print("OK")
    print()


# ---------------------------------------------------------------------------
# Modes: teardown
# ---------------------------------------------------------------------------

def run_teardown():
    """Tear down deployment: destroy Fly.io app (if any), clear webhook, optionally release number."""
    state = load_state()
    if not state:
        print_error(f"No configuration found ({STATE_FILE} missing). Nothing to tear down.")
        sys.exit(1)

    flyio_state = state.get("flyio", {})
    twilio_state = state.get("twilio", {})
    phone_number = twilio_state.get("phone_number", "unknown")
    provisioned_by_wizard = twilio_state.get("provisioned_by_wizard", False)

    print()
    print_ok("Current configuration:")
    print_ok(f"  Phone:  {format_phone(phone_number)}")
    if flyio_state:
        print_ok(f"  App:    {flyio_state.get('app_name', 'unknown')}")
        print_ok(f"  URL:    {flyio_state.get('app_url', 'unknown')}")
    else:
        server_url = get_env_value("SERVER_EXTERNAL_URL")
        if server_url:
            print_ok(f"  URL:    {server_url} (tunnel / manual)")
    print()

    if not prompt_confirm("Proceed with teardown?", default_yes=False):
        print()
        print_ok("Cancelled.")
        return

    # --- Destroy Fly.io app (if deployed) ---
    if flyio_state:
        app_name = flyio_state.get("app_name")
        if app_name:
            flyctl = get_flyctl()
            print()
            fly_destroy(flyctl, app_name)
            _clean_fly_toml_app_name()

    # --- Clear webhook on Twilio ---
    phone_number_sid = twilio_state.get("phone_number_sid")
    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")

    if phone_number_sid and account_sid and auth_token:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        try:
            client = Client(account_sid, auth_token)
            sys.stdout.write("  Clearing Twilio webhook... ")
            sys.stdout.flush()
            client.incoming_phone_numbers(phone_number_sid).update(
                voice_url="",
            )
            print("OK")
        except TwilioRestException as e:
            print(f"FAILED ({e})")
            client = None  # Can't release number if we can't reach Twilio

    # --- Optionally release the phone number ---
    if provisioned_by_wizard and phone_number_sid and account_sid and auth_token:
        print()
        print_ok(f"  The number {format_phone(phone_number)} was provisioned by this wizard.")
        if prompt_confirm(
            f"Release {format_phone(phone_number)}? This cannot be easily undone.",
            default_yes=False,
        ):
            try:
                if not client:
                    client = Client(account_sid, auth_token)
                sys.stdout.write("  Releasing phone number... ")
                sys.stdout.flush()
                client.incoming_phone_numbers(phone_number_sid).delete()
                print("OK")
            except TwilioRestException as e:
                print(f"FAILED ({e})")
                print_ok(f"  Release it manually at https://console.twilio.com")
        else:
            print_ok(f"  Number kept. See https://www.twilio.com/en-us/pricing for costs.")
            print_ok(f"  Release it anytime at https://console.twilio.com")
    elif phone_number != "unknown":
        print()
        print_ok(f"  Your Twilio number {format_phone(phone_number)} is still active.")
        print_ok(f"  Manage it at https://console.twilio.com")

    # --- Clean up state file ---
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print_ok("  Removed deployment state.")

    print()


def _clean_fly_toml_app_name():
    """Remove the `app = ...` line from fly.toml (restore to checked-in state)."""
    if not os.path.exists("fly.toml"):
        return
    with open("fly.toml") as f:
        lines = f.readlines()
    with open("fly.toml", "w") as f:
        for line in lines:
            if not line.strip().startswith("app"):
                f.write(line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Voice Agent Setup Wizard - configure Twilio and deploy to Fly.io",
    )
    parser.add_argument(
        "--twilio-only",
        action="store_true",
        help="Configure Twilio only (bring your own server URL)",
    )
    parser.add_argument(
        "--update-url",
        metavar="URL",
        help="Quick webhook URL update (e.g., new tunnel URL)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current configuration",
    )
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="Destroy Fly.io app (keeps Twilio number)",
    )

    args = parser.parse_args()

    # Handle shortcut modes
    if args.status:
        show_status()
        return

    if args.update_url:
        quick_update_url(args.update_url)
        return

    if args.teardown:
        run_teardown()
        return

    # Check for existing state
    state = load_state()
    if state:
        run_rerun_menu(state)
    else:
        run_full_setup(twilio_only=args.twilio_only)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.\n")
        sys.exit(0)
