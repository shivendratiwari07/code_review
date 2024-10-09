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

def fetch_diff(file):
    """Fetch the diff content for a file."""
    patch = file.get('patch', '')
    return patch

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
        'diff': diff,
        'rules': rules
    }

    # Log the payload for debugging purposes before sending to API
    print("Payload being sent to DEX API:")
    print(json.dumps(payload, indent=2))

    try:
        response = requests.post(AZURE_OPENAI_API_URL, json=payload, headers=philips_headers)

        # Check for a 204 No Content response and interpret it as "Everything looks good."
        if response.status_code == 204:
            print("Confirmation: 204 No Content received, treating as 'Everything looks good.'")
            return "Everything looks good."

        response.raise_for_status()  # Raise an error for other bad HTTP status codes

        # Log the raw response for debugging
        print(f"API response status code: {response.status_code}")
        print(f"Raw response content: {response.text}")

        # Parse the response as JSON
        try:
            response_data = response.json()
        except ValueError as json_error:
            print(f"Failed to parse JSON: {json_error}")
            return None

        # Check if the response contains feedback in the expected format.
        if 'comments' in response_data and response_data['comments']:
            return response_data['comments']

        # If the response contains a message like "Everything looks good.", return it.
        if isinstance(response_data, dict) and 'message' in response_data:
            return response_data['message']

        # If the response contains no comments but isn't empty, assume it means "Everything looks good."
        return response_data

    except requests.exceptions.RequestException as e:
        print(f"Failed to get a response from DEX API: {e}")
        return None

def post_review(comments, commit_id, file, diff):
    """Post a review comment on the PR for specific lines in the diff or a general comment if everything is good."""
    review_comments = []

    # If the comments contain a string indicating "Everything looks good.", post a general comment.
    if isinstance(comments, str) and comments == "Everything looks good.":
        review_comments.append({
            'path': file['filename'],
            'position': 1,  # Position in the diff, not the original file
            'body': comments
        })
    else:
        # Otherwise, iterate through each comment received from the API.
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

    # Fetch the correct commit ID from the PR
    commit_id = get_pull_request_commit_id()

    # Define the rules with more detailed instructions and examples
    rules = """
    Please review the code changes provided in the diff below based on the following criteria:

    1. **Code Quality Rules**:
       - **Naming Conventions**: Ensure that variable and function names are clear and descriptive. Flag any instances where single-letter variable names or abbreviations are used without context.
         - Example: Instead of using `a` or `tmp`, suggest using `user_age` or `temporary_value` for clarity.
       - **Avoid Magic Numbers**: Identify any instances where numbers are used directly in the code without being assigned to a named constant.
         - Example: Instead of using `for i in range(10)`, suggest `MAX_ITERATIONS = 10` and `for i in range(MAX_ITERATIONS)`.
       - **Comment Requirements**: Check that each function has a docstring or comment explaining its purpose.

    2. **Performance Optimization Rules**:
       - **Unnecessary Iterations**: Identify any nested loops that could be optimized or simplified.
       - **String Concatenation in Loops**: Recommend using string interpolation or `join` instead of `+` for concatenating strings inside loops.
         - Example: Instead of `result += str(i)`, suggest `result = ''.join([str(i) for i in range(100)])`.

    3. **Security Best Practices**:
       - **Validate Input**: Ensure that functions accepting user input include input validation.
       - **Hard-Coded Secrets**: Flag any instances of API keys, passwords, or tokens being used directly in the code.

    4. **Maintainability Rules**:
       - **Dead Code**: Identify any commented-out code that should be removed for cleanliness.
       - **Exception Handling**: Ensure that try-catch blocks are used where needed and that error messages are clear.

    5. **Code Style Enforcement**:
       - **Brace Style**: Ensure that opening braces are on the same line as function definitions and control structures.
       - **Consistent Indentation**: Verify that the code uses consistent indentation (e.g., 4 spaces per indentation level).
    6. **Code Duplication**:
       - Identify sections where the same logic or code block is repeated.
       - Suggest refactoring such duplicated code into reusable functions or constants.
       - Example: If similar payloads or requests are repeated, suggest extracting them into a function.

    Please provide specific comments on each point and suggest improvements where applicable.
    """

    for file in relevant_files:
        print(f"Analyzing {file['filename']}...")
        diff = fetch_diff(file)
        if diff:
            print("Sending diff to DEX API...")
            feedback = send_diff_to_openai(diff, rules)
            if feedback:
                post_review(feedback, commit_id, file, diff)
            else:
                print(f"No feedback received for {file['filename']}.")
        else:
            print(f"No diff found for {file['filename']}.")

if __name__ == '__main__':
    if not all([GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER]):
        print("Missing environment variables.")
        sys.exit(1)
    main()



####################$$$$$$$$$$$$$$$

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
                            "\n\nIf the code meets all the standards, respond with: 'Everything looks good.'"
                            " If there are issues, provide a brief summary (1-2 sentences) about the key areas of improvement."
                            "\n\nKeep your response short, like a human reviewer might provide."
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

    1. Code Quality Rules: Check for clear naming conventions, avoid magic numbers, and ensure functions have comments.
    2. Performance Optimization: Look for unnecessary iterations and inefficient string concatenations.
    3. Security Best Practices: Check for input validation and avoid hard-coded secrets.
    4. Maintainability: Remove dead code and ensure proper exception handling.
    5. Code Style: Check brace style, consistent indentation, and look out for duplicated code.

    If everything looks good, respond with 'Everything looks good.' Otherwise, provide a brief 1-2 sentence summary of what needs to be improved.
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



###############working ##############


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
