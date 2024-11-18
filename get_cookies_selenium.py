import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyotp  # Import pyotp for TOTP code generation
import time
import sys
import subprocess

# Get credentials from environment variables
dex_username = os.getenv('DEX_USERNAME')
dex_password = os.getenv('DEX_PASSWORD')


if not dex_username or not dex_password:
    print("Error: DEX_USERNAME or DEX_PASSWORD not set in the environment variables.")
    sys.exit(1)

# Set up Edge options and service
options = webdriver.EdgeOptions()
options.add_argument("--headless")  # Run in headless mode
options.add_argument("--disable-gpu")  # Disable GPU acceleration
options.add_argument("--no-sandbox")  # Required for headless environments
options.add_argument("--disable-dev-shm-usage")  # Overcome limited resources
options.binary_location = "/usr/bin/microsoft-edge"  # Explicitly set Edge binary path

edge_service = Service(EdgeChromiumDriverManager().install())

# Initialize Edge WebDriver with the Service
for attempt in range(3):
    try:
        driver = webdriver.Edge(service=edge_service, options=options)
        print("WebDriver initialized successfully.")
        break
    except Exception as e:
        print(f"WebDriver initialization failed on attempt {attempt + 1}: {e}")
        time.sleep(5)
else:
    print("Failed to initialize WebDriver after 3 attempts.")
    sys.exit(1)

# Navigate to the login page
url = "https://www.dex.inside.philips.com/philips-ai-chat"
driver.get(url)

# Perform login and MFA handling
try:
    # Enter username
    username_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='email' and @placeholder='someone@example.com']"))
    )
    username_field.send_keys(dex_username)
    print("Username entered.")

    # Click "Next"
    next_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
    )
    next_button.click()
    print("Next button clicked.")

    # Enter password
    password_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='password' and @name='passwd']"))
    )
    password_field.send_keys(dex_password)
    print("Password entered.")

    # Click "Sign In"
    sign_in_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
    )
    sign_in_button.click()
    print("Sign In button clicked.")

    # Handle alternative authentication
    alternative_signin_link = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.ID, "signInAnotherWay"))
    )
    alternative_signin_link.click()
    print("Clicked on 'I can't use my Microsoft Authenticator app right now' link.")

    verification_code_option = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//div[text()='Use a verification code']"))
    )
    verification_code_option.click()
    print("Clicked on 'Use a verification code' option.")

    # Generate and enter TOTP
    totp = pyotp.TOTP("vwf7p7vlrwgkq6q7")  # Replace with your TOTP secret
    mfa_code = totp.now()
    print(f"MFA Code generated: {mfa_code}")

    mfa_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='tel']"))
    )
    mfa_field.send_keys(mfa_code)
    mfa_field.send_keys(Keys.RETURN)
    print("MFA code submitted.")

    # Accept and continue
    accept_and_continue_button = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'continue-btn') and contains(text(), 'Accept and continue')]"))
    )
    accept_and_continue_button.click()
    print("Clicked on 'Accept and continue' button.")

    # Retrieve and format the .AspNetCore.Cookies value
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.AspNetCore.Cookies':
            formatted_cookie = f".AspNetCore.Cookies={cookie['value']}"
            print(f"Formatted Cookie: {formatted_cookie}")

            # Pass the cookie as an environment variable to code_review.py
            env = os.environ.copy()
            env["CUSTOM_SERVICE_COOKIE"] = formatted_cookie

            # subprocess.run(
            #     ["python", "code_review.py"],  # Run code_review.py
            #     env=env,
            #     check=True
            # )
            # break
    else:
        print(".AspNetCore.Cookies not found.")
except Exception as e:
    print("An error occurred during the process.")
    print("Error:", e)
finally:
    driver.quit()
