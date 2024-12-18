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
                            "Please review the code changes provided in the diff below based on the following criteria:\n\n"
                            + rules +
                            "\n\nIf the overall code appears to be 80% good or more and has no critical issues, respond with: 'Everything looks good.'"
                            " If there are critical issues that need attention, provide a brief summary (max 2 sentences) of the key areas needing improvement."
                            " Include a code snippet from the diff that illustrates the issue, without suggesting detailed solutions or minor improvements."
                            "\n\nKeep the response brief, as if it were from a human reviewer."
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

    # Define the rules with more detailed instructions and examples
    rules = """
    Please review the code changes provided in the diff below based on the following criteria:
    1. Code Quality: Ensure clear naming conventions, avoid magic numbers, and verify that functions have appropriate comments.
    2. Performance Optimization: Identify any unnecessary iterations or inefficient string concatenations.
    3. Security Best Practices: Check for proper input validation and the absence of hard-coded secrets.
    4. Maintainability: Look for dead code, proper exception handling, and ensure modularity.
    5. Code Style: Confirm consistent indentation, brace style, and identify any duplicated code.

    If the overall code appears to be 80% good or more and has no critical issues, simply respond with 'Everything looks good.' If there are critical issues, provide a brief summary (max 2 sentences) of the key areas needing improvement, and include a code snippet from the diff that illustrates the issue. Keep the tone brief and human-like.
    """

    # Process each relevant file to get the diff and send it for review
    for file in relevant_files:
        print(f"Analyzing {file['filename']}...")
        added_lines = fetch_added_lines_only(file)
        if added_lines:
            print(f"Sending added lines from {file['filename']} to DEX API for review...")
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


# import os
# import sys
# import json
# import requests

# # GitHub environment variables
# GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
# GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')
# PR_NUMBER = os.getenv('PR_NUMBER')
# GITHUB_API_URL = 'https://api.github.com'
# custom_service_cookie = os.getenv('CUSTOM_SERVICE_COOKIE')

# # Philips DEX API URL
# DEX_CHAT_API_URL = 'https://www.dex.inside.philips.com/philips-ai-chat/chat/api/user/SendImageMessage'

# # Headers for GitHub API requests
# headers = {
#     'Authorization': f'token {GITHUB_TOKEN}',
#     'Accept': 'application/vnd.github.v3+json'
# }

# # Custom headers for DEX API
# dex_headers = {
#     'Cookie': f'{custom_service_cookie}',
#     'Content-Type': 'application/json'
# }

# def create_dex_chat_session(pr_number):
#     """Create a DEX chat session for the PR discussion."""
#     payload = {
#         "messages": [
#             {
#                 "role": "system",
#                 "content": f"Chat session created for discussion on PR #{pr_number}. Feel free to ask questions or discuss the changes."
#             }
#         ]
#     }
#     try:
#         response = requests.post(DEX_CHAT_API_URL, json=payload, headers=dex_headers)
#         response.raise_for_status()
#         chat_data = response.json()
#         if "session_id" in chat_data:
#             return chat_data["session_id"]
#         else:
#             print("Failed to create chat session. Response:", chat_data)
#             return None
#     except requests.exceptions.RequestException as e:
#         print(f"Failed to create chat session: {e}")
#         return None

# def post_pr_comment_with_chat_link(pr_number, chat_session_url):
#     """Post a comment on the PR with the chat session link."""
#     url = f'{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/issues/{pr_number}/comments'
#     headers = {
#         'Authorization': f'token {GITHUB_TOKEN}',
#         'Accept': 'application/vnd.github.v3+json'
#     }
#     message = f"A live chat session has been created for this PR. Join the discussion here: {chat_session_url}"
#     payload = {
#         "body": message
#     }
#     response = requests.post(url, headers=headers, json=payload)
#     response.raise_for_status()

# def get_chat_session_url(session_id):
#     """Construct the DEX chat session URL using the session ID."""
#     return f"https://www.dex.inside.philips.com/philips-ai-chat/session/{session_id}"

# def main():
#     if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER, custom_service_cookie]):
#         print("Missing environment variables.")
#         sys.exit(1)
    
#     # Create a DEX chat session for the PR discussion
#     session_id = create_dex_chat_session(PR_NUMBER)
#     if session_id:
#         chat_session_url = get_chat_session_url(session_id)
        
#         # Post the chat session link as a comment in the PR
#         post_pr_comment_with_chat_link(PR_NUMBER, chat_session_url)
#         print(f"DEX chat session created and linked to PR #{PR_NUMBER}")
#     else:
#         print(f"Failed to create DEX chat session for PR #{PR_NUMBER}")

# if __name__ == '__main__':
#     main()
