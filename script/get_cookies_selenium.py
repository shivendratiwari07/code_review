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
edge_service = Service(EdgeChromiumDriverManager().install())

# Initialize Edge WebDriver with the Service
driver = webdriver.Edge(service=edge_service, options=options)

# Navigate to the login page
url = "https://www.dex.inside.philips.com/philips-ai-chat"
driver.get(url)

# Wait for the username field to appear by placeholder and enter the username
try:
    username_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='email' and @placeholder='someone@example.com']"))
    )
    username_field.send_keys(dex_username)
    print("Username entered.")
except Exception as e:
    print("Username field not found.")
    print("Error:", e)

# Wait for the "Next" button by value attribute and click it
try:
    next_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
    )
    next_button.click()
    print("Next button clicked.")
except Exception as e:
    print("Next button not found.")
    print("Error:", e)

# Wait for the password field to appear by name and enter the password
try:
    password_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='password' and @name='passwd']"))
    )
    password_field.send_keys(dex_password)
    print("Password entered.")
except Exception as e:
    print("Password field not found.")
    print("Error:", e)

# Wait for the "Sign In" button by value attribute and click it
try:
    sign_in_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
    )
    sign_in_button.click()
    print("Sign In button clicked.")
except Exception as e:
    print("Sign In button not found.")
    print("Error:", e)

# Click the "I can't use my Microsoft Authenticator app right now" link
try:
    alternative_signin_link = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.ID, "signInAnotherWay"))  # Locate by ID
    )
    alternative_signin_link.click()
    print("Clicked on 'I can't use my Microsoft Authenticator app right now' link.")
except Exception as e:
    print("'I can't use my Microsoft Authenticator app right now' link not found.")
    print("Error:", e)

# Click "Use a verification code" option
try:
    verification_code_option = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//div[text()='Use a verification code']"))  # Locate by text content
    )
    verification_code_option.click()
    print("Clicked on 'Use a verification code' option.")
except Exception as e:
    print("'Use a verification code' option not found.")
    print("Error:", e)

# Generate TOTP code and enter it in the authenticator field
try:
    totp = pyotp.TOTP("vwf7p7vlrwgkq6q7")  # Replace with your TOTP secret
    mfa_code = totp.now()
    print(f"MFA Code generated: {mfa_code}")

    mfa_field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='tel']"))
    )
    mfa_field.send_keys(mfa_code)
    mfa_field.send_keys(Keys.RETURN)
    print("MFA code submitted.")
except Exception as e:
    print("MFA input field not found.")
    print("Error:", e)

# Click the "Accept and continue" button
try:
    accept_and_continue_button = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'continue-btn') and contains(text(), 'Accept and continue')]"))
    )
    accept_and_continue_button.click()
    print("Clicked on 'Accept and continue' button.")
except Exception as e:
    print("'Accept and continue' button not found.")
    print("Error:", e)

# Retrieve and format the .AspNetCore.Cookies value
try:
    cookies = driver.get_cookies()
    for cookie in cookies:
        if cookie['name'] == '.AspNetCore.Cookies':
            formatted_cookie = f".AspNetCore.Cookies={cookie['value']}"
            print(f"Formatted Cookie: {formatted_cookie}")
            
            # Pass the cookie as an environment variable to code_review.py
            env = os.environ.copy()
            env["CUSTOM_SERVICE_COOKIE"] = formatted_cookie
            
            subprocess.run(
                ["python", "code_review.py"], 
                env=env, 
                check=True
            )
            break
    else:
        print(".AspNetCore.Cookies not found.")
except Exception as e:
    print("Error retrieving cookies.")
    print("Error:", e)
finally:
    driver.quit()
