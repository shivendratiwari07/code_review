import os
import sys
import json
import requests
from requests.exceptions import Timeout, RequestException

# GitHub environment variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')
PR_NUMBER = os.getenv('PR_NUMBER')
GITHUB_API_URL = 'https://api.github.com'

# DEX API URLs and credentials
DEX_LOGIN_URL = 'https://www.dex.inside.philips.com/philips-ai-chat'
DEX_API_URL = 'https://www.dex.inside.philips.com/philips-ai-chat/chat/api/user/SendImageMessage'
DEX_USERNAME = os.getenv('DEX_USERNAME')
DEX_PASSWORD = os.getenv('DEX_PASSWORD')

# Headers for GitHub API requests
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}


def login_to_dex():
    """Authenticate with DEX API to retrieve cookies."""
    login_payload = {
        'username': DEX_USERNAME,
        'password': DEX_PASSWORD
    }
    
    print({f"printing the login_payload  :" + login_payload})
    session = requests.Session()
    try:
        headers = {'Content-Type': 'application/json'}
        response = session.post(DEX_LOGIN_URL, json=login_payload, headers=headers)
        
        # Print response details for troubleshooting
        print(f"Login Response Code: {response.status_code}")
        print(f"Login Response Text: {response.text}")
        
        response.raise_for_status()
        return session.cookies
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error during login: {err}")
        return None
    except Exception as err:
        print(f"Login error: {err}")
        return None


def get_latest_commit():
    """Fetch the latest commit SHA in the PR."""
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}/commits'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    commits = response.json()
    return commits[-1]['sha']


def get_latest_commit_files(commit_id):
    """Fetch the list of changed files in the latest commit."""
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/commits/{commit_id}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['files']


def filter_relevant_files(files):
    """Filter files based on extensions."""
    relevant_extensions = (
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cs', 
        '.c', '.cpp', '.h', '.hpp', '.go', '.rb', '.php', 
        '.html', '.css', '.kt', '.swift', '.scala', '.rs', 
        '.sh', '.dart', '.sql'
    )
    return [f for f in files if f['filename'].endswith(relevant_extensions)]


def fetch_added_lines_only(file):
    """Fetch only the added lines (lines starting with '+') from the diff."""
    patch = file.get('patch', '')
    added_lines = [line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
    return '\n'.join(added_lines)


def send_diff_to_dex(diff, rules, dex_cookies, max_retries=3):
    """Send the diff to Philips DEX API for code review with retries."""
    payload = {
        "messages": [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    "Please review the code changes provided in the diff below based on the following criteria:\n\n" +
                    rules + "\n\nIf the overall code appears to be 80% good or more and has no critical issues, " +
                    "respond with: 'Everything looks good.' If there are critical issues that need attention, " +
                    "provide a brief summary (max 2 sentences) of the key areas needing improvement. " +
                    "Include a code snippet from the diff that illustrates the issue, without suggesting " +
                    "detailed solutions or minor improvements.\n\nKeep the response brief, " +
                    "as if it were from a human reviewer.\n\nHere is the diff with only the added lines:\n\n" + diff)
            }]
        }]
    }

    attempts = 0
    while attempts < max_retries:
        try:
            response = requests.post(
                DEX_API_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                cookies=dex_cookies,
                timeout=60
            )
            response.raise_for_status()
            response_data = response.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"]
            else:
                print("Unexpected response format from DEX API.")
                return None
        except (Timeout, RequestException) as e:
            print(f"Attempt {attempts + 1} failed: {e}")
            attempts += 1
    print("Max retries reached, failing.")
    return None


def post_review(content, commit_id, file):
    """Post a review comment on the PR."""
    review_comments = [{
        'path': file['filename'],
        'position': 1,
        'body': content
    }]
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}/reviews'
    review_data = {
        'commit_id': commit_id,
        'body': 'Automated Code Review',
        'event': 'COMMENT',
        'comments': review_comments
    }

    try:
        response = requests.post(url, headers=headers, json=review_data)
        response.raise_for_status()
        print("Review posted successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to post review: {e}")


def main():
    dex_cookies = login_to_dex()
    if not dex_cookies:
        print("Failed to obtain cookies from DEX API.")
        sys.exit(1)

    latest_commit_id = get_latest_commit()
    latest_commit_files = get_latest_commit_files(latest_commit_id)
    relevant_files = filter_relevant_files(latest_commit_files)

    if not relevant_files:
        print("No relevant files to analyze.")
        sys.exit(0)

    rules = """
    Please review the code changes provided in the diff below based on the following criteria:
    1. Code Quality: Ensure clear naming conventions, avoid magic numbers, and verify that functions have appropriate comments.
    2. Performance Optimization: Identify any unnecessary iterations or inefficient string concatenations.
    3. Security Best Practices: Check for proper input validation and the absence of hard-coded secrets.
    4. Maintainability: Look for dead code, proper exception handling, and ensure modularity.
    5. Code Style: Confirm consistent indentation, brace style, and identify any duplicated code.
    
    If the overall code appears to be 80% good or more and has no critical issues, simply respond with 'Everything looks good.' 
    If there are critical issues, provide a brief summary (max 2 sentences) of the key areas needing improvement, 
    and include a code snippet from the diff that illustrates the issue. Keep the tone brief and human-like.
    """

    for file in relevant_files:
        added_lines = fetch_added_lines_only(file)
        if added_lines:
            feedback = send_diff_to_dex(added_lines, rules, dex_cookies)
            if feedback:
                post_review(feedback, latest_commit_id, file)


if __name__ == '__main__':
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER, DEX_USERNAME, DEX_PASSWORD]):
        print("Missing environment variables.")
        sys.exit(1)
    main()