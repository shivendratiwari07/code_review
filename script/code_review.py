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
custom_service_cookie = os.getenv('CUSTOM_SERVICE_COOKIE')

# Philips OpenAI API URL
DEX_API_URL = 'https://www.dex.inside.philips.com/philips-ai-chat/chat/api/user/SendImageMessage'

# Headers for GitHub API requests
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# Check if cookie is set, or exit if not
if not custom_service_cookie:
    print("Error: CUSTOM_SERVICE_COOKIE environment variable is not set")
    sys.exit(1)

# Custom headers for Philips API
philips_headers = {
    'Cookie': f'{custom_service_cookie}',  # Custom service authentication via cookie
    'Content-Type': 'application/json'
}

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
    files = response.json()['files']
    return files

def filter_relevant_files(files):
    """Filter files based on extensions."""
    relevant_extensions = (
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cs', '.c', 
        '.cpp', '.h', '.hpp', '.go', '.rb', '.php', '.html', '.css', 
        '.kt', '.swift', '.scala', '.rs', '.sh', '.dart', '.sql'
    )
    return [f for f in files if f['filename'].endswith(relevant_extensions)]

def fetch_added_lines_only(file):
    """Fetch only the added lines (lines starting with '+') from the diff."""
    patch = file.get('patch', '')
    added_lines = [line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
    return '\n'.join(added_lines)

def send_diff_to_dex(diff, rules, max_retries=3):
    """Send the diff to Philips DEX API for code review with retries."""
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Please review the code changes provided in the diff below based on the following criteria:\n\n" +
                            rules +
                            "\n\nIf the overall code appears to be 80% good or more and has no critical issues, respond with: 'Everything looks good.'" +
                            " If there are critical issues that need attention, provide a brief summary (max 2 sentences) of the key areas needing improvement." +
                            " Include a code snippet from the diff that illustrates the issue, without suggesting detailed solutions or minor improvements." +
                            "\n\nKeep the response brief, as if it were from a human reviewer." +
                            "\n\nHere is the diff with only the added lines:\n\n" + diff
                        )
                    }
                ]
            }
        ]
    }
    print("Payload being sent to DEX API:")
    print(json.dumps(payload, indent=2))

    attempts = 0
    while attempts < max_retries:
        try:
            response = requests.post(DEX_API_URL, json=payload, headers=philips_headers, timeout=60)
            response.raise_for_status()
            print(f"API response status code: {response.status_code}")
            print(f"Raw response content: {response.text}")
            
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
        'position': 1,  # General comment at the start of the diff
        'body': content
    }]
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}/reviews'
    review_data = {
        'commit_id': commit_id,
        'body': 'Automated Code Review by OpenAI Azure 4o',
        'event': 'COMMENT',
        'comments': review_comments
    }
    try:
        response = requests.post(url, headers=headers, json=review_data)
        response.raise_for_status()
        print("Review posted successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to post review: {e}")
        print(f"Response content: {response.content}")

def main():
    # Get the latest commit SHA
    latest_commit_id = get_latest_commit()

    # Get the files changed in the latest commit
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
    
    # Review latest commit relevant files
    for file in relevant_files:
        print(f"Analyzing {file['filename']} from latest commit...")
        added_lines = fetch_added_lines_only(file)
        if added_lines:
            print(f"Sending added lines from {file['filename']} to DEX API for review...")
            feedback = send_diff_to_dex(added_lines, rules)
            if feedback:
                post_review(feedback, latest_commit_id, file)
            else:
                print(f"No feedback received for {file['filename']}.")
        else:
            print(f"No added lines found for {file['filename']}.")
            
if __name__ == '__main__':
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER]):
        print("Missing environment variables.")
        sys.exit(1)
    main()