import os
import sys
import json
import requests

# GitHub environment variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')
PR_NUMBER = os.getenv('PR_NUMBER')
GITHUB_API_URL = 'https://api.github.com'
custom_service_cookie = os.getenv('CUSTOM_SERVICE_COOKIE')

# Philips OpenAI API URL
AZURE_OPENAI_API_URL = 'https://www.dex.inside.philips.com/philips-ai-chat/chat/api/user/SendImageMessage'

# Headers for GitHub API requests
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# Check if cookie is set, or exit
if not custom_service_cookie:
    print("Error: CUSTOM_SERVICE_COOKIE environment variable is not set")
    sys.exit(1)

# Custom headers for Philips API
philips_headers = {
    'Cookie': f'{custom_service_cookie}',  # Custom service authentication via cookie
    'Content-Type': 'application/json'
}

def get_changed_files():
    """Fetch the list of changed files in the PR."""
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}/files'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    files = response.json()
    return files

def filter_relevant_files(files):
    """Filter files based on extensions."""
    relevant_extensions = (
        '.py',
        '.js', '.jsx', '.ts', '.tsx',  # JavaScript/TypeScript
        '.java',
        '.cs',     # C#
        '.c', '.cpp', '.h', '.hpp',  # C/C++
        '.go',     # Go
        '.rb',     # Ruby
        '.php',    # PHP
        '.html', '.css',  # HTML/CSS
        '.kt',     # Kotlin
        '.swift',  # Swift
        '.scala',  # Scala
        '.rs',     # Rust
        '.sh',     # Shell Scripts
        '.dart',   # Dart
        '.sql'     # SQL
    )
    return [f for f in files if f['filename'].endswith(relevant_extensions)]

def fetch_diff(file):
    """Fetch the diff content for a file."""
    patch = file.get('patch', '')
    return patch

def send_diff_to_openai(diff, rules):
    """Send the diff to the Azure OpenAI API for code review with cookie-based authentication."""
    payload = {
        'diff': diff,
        'rules': rules
    }

    # Check if the diff or rules are empty and log them
    if not diff:
        print("Error: Diff is empty. Cannot send to API.")
        return None
    if not rules:
        print("Error: Rules are empty. Cannot send to API.")
        return None

    # Log the payload for debugging purposes before sending to API
    print("Payload being sent to OpenAI API:")
    print(json.dumps(payload, indent=2))  # Pretty-print the payload for easier reading

    try:
        response = requests.post(AZURE_OPENAI_API_URL, json=payload, headers=philips_headers)
        response.raise_for_status()  # Raise an error for bad HTTP status codes

        # Log the raw response for debugging
        print(f"API response status code: {response.status_code}")
        print(f"Raw response content: {response.text}")  # Log the raw content

        if response.status_code == 204:
            print("Received 204 No Content. No feedback available.")
            return None  # No feedback to process

        # Attempt to parse the response as JSON
        try:
            return response.json()  # Parse the JSON response
        except ValueError as json_error:
            print(f"Failed to parse JSON: {json_error}")
            return None  # Handle non-JSON responses gracefully
    except requests.exceptions.RequestException as e:
        print(f"Failed to get a response from OpenAI API: {e}")
        return None

def post_review(comments, commit_id, file, diff):
    """Post a review comment on the PR for specific lines in the diff."""
    review_comments = []

    for comment in comments:
        # Locate the line number in the diff where the comment should be placed
        diff_lines = diff.split('\n')
        position = 0
        for idx, line in enumerate(diff_lines):
            if line.startswith('+') and comment['line'] in line:
                position = idx + 1  # GitHub uses 1-based index

        review_comment = {
            'path': file['filename'],
            'position': position,  # Position in the diff, not the original file
            'body': comment['body']
        }
        review_comments.append(review_comment)

    if review_comments:
        url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}/reviews'
        review_data = {
            'commit_id': commit_id,
            'body': 'Automated Code Review by OpenAI Azure 4o',
            'event': 'COMMENT',
            'comments': review_comments
        }
        response = requests.post(url, headers=headers, data=json.dumps(review_data))
        if response.status_code != 200:
            print(f"Failed to post review: {response.content}")
        else:
            print("Review posted successfully.")

def main():
    files = get_changed_files()
    relevant_files = filter_relevant_files(files)
    if not relevant_files:
        print("No relevant files to analyze.")
        sys.exit(0)

    commit_id = os.getenv('GITHUB_SHA')

    # Define the rules from the document
    rules = """
    1. Code Quality Rules:
       - Naming Conventions
       - Comment Requirements
       - Avoid Magic Numbers
       - Method Length

    2. Performance Optimization Rules:
       - Avoid Unnecessary LINQ Queries
       - Avoid String Concatenation in Loops
       - Avoid Excessive Boxing/Unboxing

    3. Security Best Practices:
       - Validate Input
       - Check for Hard-Coded Secrets

    4. Maintainability Rules:
       - Dead Code Detection
       - Consistent Use of Exception Handling

    5. Code Style Enforcement:
       - Consistent Brace Style
    """

    for file in relevant_files:
        print(f"Analyzing {file['filename']}...")
        diff = fetch_diff(file)
        if diff:
            print("Sending diff to OpenAI API...")
            feedback = send_diff_to_openai(diff, rules)
            if feedback:
                post_review(feedback['comments'], commit_id, file, diff)
            else:
                print(f"No feedback received for {file['filename']}.")
        else:
            print(f"No diff found for {file['filename']}.")

if __name__ == '__main__':
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER]):
        print("Missing environment variables.")
        sys.exit(1)
    main()
