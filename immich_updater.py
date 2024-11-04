#!/usr/bin/python3

"""Simple and dumb Immich server updater.

Compares the current server version with the version of the latest release on
Github. If there has been a major version update -OR- the release notes say
"breaking change" (case-insensitive) anywhere, then it aborts. Otherwise, if
there has been a version change, will do `docker pull`, `docker compose up -d`.

Limitations:
This script is DUMB. It's literally looking for a string in the release notes.
Also, this script only looks at the notes of the LATEST release. That means
that it needs to be run often (daily? weekly?) to make sure that it does not
miss a "breaking change" release between runs.
"""

"""With error handling, console feedback and logging"""

import re
import sys
from datetime import datetime, timezone
import requests
import sh


### CHANGE THESE VALUES ###

# Where do the Immich docker-compose.yml and .env files live?
IMMICH_DIR = '/docker/compose/immich'

# How many days do you want to wait after the latest release before you
# update to it? (Allows the initial kinks to get worked out.)
DELAY_DAYS = 3

############################


def err(err_obj: sh.ErrorReturnCode):
    """Prints error messages and quits."""
    print('Error: Failed to run previous command with error code "'
          f'{err_obj.exit_code}". Error message:')
    print(err_obj.stderr.decode('utf-8'))
    log_update(f"Failed to run previous command with error code.")
    sys.exit(1)


def log_update(message):
    """Logs the update message to a log file in IMMICH_DIR."""
    log_file_path = f"{IMMICH_DIR}/update_log.txt"  # Specify the log file path
    with open(log_file_path, 'a') as log_file:
        log_file.write(f"{datetime.now()}: {message}\n")
    print("Update logged.")


# Retrieve the currently installed version from the API.
# JSON dictionary object with 'major', 'minor', and 'patch' keys.
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
    log_update(f"Could not retrieve current version from the Immich API.")
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
    log_update(f"Could not retrieve release info from GitHub.")
    sys.exit(1)


# If major version has changed, assume there will be breaking changes.
print("Checking for major version changes...")
if int(latest_version[0]) != int(curr_vers['major']):
    print('Immich-Updater: Detected a major version change.'
          ' Will not proceed with the update. Currently-installed version:'
          f' {curr_vers_str} / latest release: {latest_version_str}.')
    log_update(f"Major version change detected. Current version: {curr_vers_str}, Latest version: {latest_version_str}. Aborting update.")
    sys.exit(0)


# Check if no version change occurred
if (int(latest_version[1]) == int(curr_vers['minor'])
        and int(latest_version[2]) == int(curr_vers['patch'])):
    print("No update needed. The version is up-to-date.")
    log_update(f"No changes detected. Current version: {curr_vers_str}.")
    sys.exit(0)


# If there has been a minor version change, then need to check the release
# notes for a breaking changes.
# Do not do this for a patch update only, because the "breaking..." warning is
# repeated in patch updates if there was one in the minor update.
if int(latest_version[1]) != int(curr_vers['minor']):
    print("Checking release notes for breaking changes...")
    if 'body' in release_data:
        for line in release_data['body'].splitlines():
            if re.search('breaking change', line, re.IGNORECASE):
                # Line found
                print('Immich-Updater: A breaking change has been detected when'
                      ' comparing the currently-installed version'
                      f' ({curr_vers_str}) to the latest release'
                      f' ({release_data["tag_name"]}). Will not proceed with the'
                      ' update.')
                log_update(f"Breaking change detected in release notes. Current version: {curr_vers_str}, Latest version: {latest_version_str}. Aborting update.")
                sys.exit(0)
    else:
        print("No release notes found. Skipping 'breaking change' check.")
        
        
# One last check is the delay setting

# Grab the release publish date, and convert to a datetime object.
# Versions < 3.11 do not support TZ 'Z', so replace it with '+00:00'.
release_DT = datetime.fromisoformat(
    release_data['published_at'].replace('Z', '+00:00'))

# Has enough time elapsed?
days_since_release = (datetime.now(timezone.utc) - release_DT).days
print(f"Days since release: {days_since_release}, delay required: {DELAY_DAYS}")
if days_since_release < DELAY_DAYS:
    print(f"Update will not proceed; waiting period of {DELAY_DAYS} days not met.")
    log_update(f"Update deferred. Released {release_DT} which is within the delay period of {DELAY_DAYS} days.")
    sys.exit(0)

# If we made it this far, then there has been an update and no breaking
# changes have been detected. Ok to proceed with update.
print(f"Proceeding with update from {curr_vers_str} to {latest_version_str}.")

# Build a docker SH command
docker = sh.Command('docker')
docker = docker.bake(_cwd=IMMICH_DIR)

# Pull
try:
    print("Pulling new Docker image...")
    out = docker('compose', 'pull')
    print(out)
except sh.ErrorReturnCode as e:
    err(e)

# Reload
try:
    print("Reloading server with new update...")
    out = docker('compose', 'up', '-d')
    print(out)
    # Log the update
    log_update(f"Immich server updated from {curr_vers_str} to {latest_version_str}.")
except sh.ErrorReturnCode as e:
    err(e)

print("Update completed successfully.")
sys.exit(0)
