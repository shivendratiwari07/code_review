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
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cs', '.c', '.cpp', '.h', '.hpp',  
        '.go', '.rb', '.php', '.html', '.css', '.kt', '.swift', '.scala', '.rs', '.sh', 
        '.dart', '.sql'
    )
    return [f for f in files if f['filename'].endswith(relevant_extensions)]

def fetch_added_lines_only(file):
    """Fetch only the added lines (lines starting with '+') from the diff."""
    patch = file.get('patch', '')
    added_lines = [line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
    return '\n'.join(added_lines)

def get_pull_request_commit_id():
    """Fetch the head commit ID of the pull request."""
    url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    pr_data = response.json()
    return pr_data['head']['sha']

def send_diff_to_openai(diff, rules):
    """Send the diff to the Azure OpenAI API for code review with cookie-based authentication."""
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Act as a senior code reviewer. Focus only on critical and blocker issues in the provided code changes.\n\n"
                            + rules +
                            "\n\nYour feedback should highlight only critical or blocker issues, such as security vulnerabilities, significant bugs, or performance bottlenecks."
                            " If everything looks fine, respond with: 'Everything looks good.'"
                            " If there are critical issues, provide a brief summary (max 2 sentences) of the key areas needing improvement."
                            " Keep your tone human-like, direct, and to the point. Ignore minor issues or non-critical feedback."
                            "\n\nHere is the diff with only the added lines:\n\n"
                            + diff
                        )
                    }
                ]
            }
        ]
    }

    print("Payload being sent to DEX API:")
    print(json.dumps(payload, indent=2))

    try:
        response = requests.post(AZURE_OPENAI_API_URL, json=payload, headers=philips_headers)
        response.raise_for_status()

        print(f"API response status code: {response.status_code}")
        print(f"Raw response content: {response.text}")

        # Parse the response content as JSON
        response_data = response.json()

        # Extract the content from the API's response
        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"]
        else:
            print("Unexpected response format from DEX API.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Failed to get a response from DEX API: {e}")
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
    files = get_changed_files()
    relevant_files = filter_relevant_files(files)
    if not relevant_files:
        print("No relevant files to analyze.")
        sys.exit(0)

    # Fetch the correct commit ID from the PR
    commit_id = get_pull_request_commit_id()

    # Define the rules with detailed instructions for a focused review
    rules = """
    1. Code Quality:
       - Naming conventions, comments, avoid magic numbers, and keep methods concise.
    2. Performance:
       - Optimize unnecessary queries, avoid string concatenation in loops, and minimize excessive conversions.
    3. Security:
       - Validate inputs and ensure no hard-coded secrets.
    4. Maintainability:
       - Remove dead code and apply consistent exception handling.
    5. Style:
       - Follow consistent brace style.
    """

    for file in relevant_files:
        print(f"Analyzing {file['filename']}...")
        added_lines = fetch_added_lines_only(file)
        if added_lines:
            print("Sending added lines to DEX API for review...")
            feedback = send_diff_to_openai(added_lines, rules)
            if feedback:
                post_review(feedback, commit_id, file)
            else:
                print(f"No feedback received for {file['filename']}.")
        else:
            print(f"No added lines found for {file['filename']}.")

if __name__ == '__main__':
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER]):
        print("Missing environment variables.")
        sys.exit(1)
    main()
