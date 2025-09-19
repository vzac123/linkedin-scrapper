import os
import time
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

app = FastAPI(title="LinkedIn Scraper API")

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # headless mode for servers
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=chrome_options)
    return driver

def linkedin_login(driver):
    """Login to LinkedIn using environment variables"""
    driver.get("https://www.linkedin.com/login")
    time.sleep(3)

    email_box = driver.find_element(By.ID, "username")
    password_box = driver.find_element(By.ID, "password")

    email_box.send_keys(LINKEDIN_EMAIL)
    password_box.send_keys(LINKEDIN_PASSWORD)
    password_box.submit()
    time.sleep(5)  # wait for login to complete

@app.get("/")
def root():
    return {"message": "LinkedIn Scraper API is running!"}

@app.get("/scrape")
def scrape_linkedin_profile(url: str = Query(..., description="LinkedIn profile URL")):
    try:
        driver = init_driver()

        # login first
        linkedin_login(driver)

        # open profile
        driver.get(url)
        time.sleep(5)

        html = driver.page_source
        driver.quit()

        soup = BeautifulSoup(html, "html.parser")

        # extract some basic details
        name = soup.find("h1")
        headline = soup.find("div", {"class": "text-body-medium"})
        about_section = soup.find("div", {"id": "about"})

        data = {
            "name": name.get_text(strip=True) if name else None,
            "headline": headline.get_text(strip=True) if headline else None,
            "about": about_section.get_text(strip=True) if about_section else None,
            "url": url,
        }

        return JSONResponse(content=data)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
