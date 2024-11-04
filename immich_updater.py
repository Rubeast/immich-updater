#!/usr/bin/python3

"""Simple and dumb Immich server updater with console feedback."""

import re
import sys
from datetime import datetime, timezone
import requests
import sh


### CHANGE THESE VALUES ###

# Where do the Immich docker-compose.yml and .env files live?
IMMICH_DIR = '/opt/immich'

# How many days do you want to wait after the latest release before you
# update to it? (Allows the initial kinks to get worked out.)
DELAY_DAYS = 3

############################


def err(err_obj: sh.ErrorReturnCode):
    """Prints error messages and quits."""
    print('Error: Failed to run previous command with error code "'
          f'{err_obj.exit_code}". Error message:')
    print(err_obj.stderr.decode('utf-8'))
    sys.exit(1)


# Retrieve the currently installed version from the API.
print("Retrieving currently installed Immich server version...")
try:
    r = requests.get('http://localhost:2283/api/server/version', timeout=30)
    curr_vers = r.json()
    curr_vers_str = (f'v{curr_vers["major"]}.{curr_vers["minor"]}'
                     f'.{curr_vers["patch"]}')
    print(f"Current version: {curr_vers_str}")
except requests.RequestException as e:
    print("Error: Could not retrieve current version from the Immich API.")
    print(e)
    sys.exit(1)


# Retrieve the latest release info from GitHub.
print("Retrieving latest release info from GitHub...")
try:
    r = requests.get(
        "https://api.github.com/repos/immich-app/immich/releases/latest",
        allow_redirects=True, timeout=30)
    release_data = r.json()
    latest_version_str = release_data['tag_name']
    latest_version = latest_version_str.lstrip('v').split('.')
    print(f"Latest version on GitHub: {latest_version_str}")
except requests.RequestException as e:
    print("Error: Could not retrieve release info from GitHub.")
    print(e)
    sys.exit(1)


# Check for major version changes
print("Checking for major version changes...")
if int(latest_version[0]) != int(curr_vers['major']):
    print('Detected a major version change. Update will not proceed.')
    sys.exit(0)


# Check if no version change occurred
if (int(latest_version[1]) == int(curr_vers['minor'])
        and int(latest_version[2]) == int(curr_vers['patch'])):
    print("No update needed. The version is up-to-date.")
    sys.exit(0)


# Check release notes for "breaking change" if there's a minor update
if int(latest_version[1]) != int(curr_vers['minor']):
    print("Checking release notes for breaking changes...")
    if 'body' in release_data:
        for line in release_data['body'].splitlines():
            if re.search('breaking change', line, re.IGNORECASE):
                print("Breaking change detected. Update will not proceed.")
                sys.exit(0)
    else:
        print("No release notes found. Skipping 'breaking change' check.")


# Check delay before applying update
release_DT = datetime.fromisoformat(
    release_data['published_at'].replace('Z', '+00:00'))
days_since_release = (datetime.now(timezone.utc) - release_DT).days
print(f"Days since release: {days_since_release}, delay required: {DELAY_DAYS}")
if days_since_release < DELAY_DAYS:
    print(f"Update will not proceed; waiting period of {DELAY_DAYS} days not met.")
    sys.exit(0)


# Proceed with the update
print(f"Proceeding with update from {curr_vers_str} to {latest_version_str}.")
docker = sh.Command('docker').bake(_cwd=IMMICH_DIR)

try:
    print("Pulling new Docker image...")
    out = docker('compose', 'pull')
    print(out)
except sh.ErrorReturnCode as e:
    err(e)

try:
    print("Reloading server with new update...")
    out = docker('compose', 'up', '-d')
    print(out)
except sh.ErrorReturnCode as e:
    err(e)

print("Update completed successfully.")
sys.exit(0)
