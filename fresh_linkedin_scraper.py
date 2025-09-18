from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time
from typing import List, Dict, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LinkedIn Job Scraper API",
    description="API for scraping job listings from LinkedIn",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "LinkedIn Job Scraper API",
        "endpoints": {
            "scrape_jobs": "/scrape/?keyword=your_keyword",
            "health_check": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

@app.get("/scrape/", response_model=List[Dict[str, Any]])
async def scrape_data(keyword: str, max_jobs: int = 10):
    """
    Scrape LinkedIn jobs for a given keyword
    
    Args:
        keyword: Search keyword for jobs
        max_jobs: Maximum number of jobs to return (default: 10)
    
    Returns:
        List of job dictionaries with details
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    logger.info(f"Starting scrape for keyword: {keyword}")
    
    driver = None
    try:
        # Configure Chrome options
        options = uc.ChromeOptions()
        options.add_argument('--headless')  # Run in background
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--accept-lang=en-US,en;q=0.9')
        
        # Let undetected-chromedriver handle version automatically
        logger.info("Initializing Chrome driver...")
        driver = uc.Chrome(
            options=options,
            use_subprocess=True,  # Better for handling Chrome processes
            headless=True
        )
        
        linkedin_jobs = []
        
        # Construct LinkedIn search URL
        search_query = keyword.replace(' ', '%20')
        linkedin_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}"
        
        logger.info(f"Navigating to: {linkedin_url}")
        driver.get(linkedin_url)
        time.sleep(5)  # Wait for page to load
        
        # Check if we're redirected to login
        current_url = driver.current_url
        if "authwall" in current_url or "login" in current_url:
            logger.warning("LinkedIn login wall detected. Some data might be limited.")
            # Continue anyway - we might still get some data
        
        # Scroll to load more content
        logger.info("Scrolling to load more jobs...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        # Get page source and parse with BeautifulSoup
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Multiple selectors to catch different LinkedIn layouts
        job_selectors = [
            'div.base-card',  # New LinkedIn layout
            'li.jobs-search-results__list-item',  # Older layout
            'div.job-search-card',  # Alternative selector
            'div[data-entity-urn*="jobPosting"]',  # Data attribute selector
            'section.jobs-search-results__list-item'  # Another common selector
        ]
        
        job_cards = []
        for selector in job_selectors:
            found_cards = soup.select(selector)
            if found_cards:
                job_cards.extend(found_cards)
                logger.info(f"Found {len(found_cards)} jobs using selector: {selector}")
        
        # Remove duplicates by job URL
        unique_jobs = {}
        for job in job_cards:
            try:
                # Extract job details with multiple fallback selectors
                title_selectors = [
                    'h3.base-search-card__title',
                    'h3.job-search-card__title',
                    'h3[class*="title"]',
                    'h3'
                ]
                
                company_selectors = [
                    'h4.base-search-card__subtitle',
                    'h4.job-search-card__subtitle',
                    'a[class*="company"]',
                    'h4'
                ]
                
                location_selectors = [
                    'span.job-search-card__location',
                    'span[class*="location"]',
                    'div[class*="location"]',
                    'span'
                ]
                
                link_selectors = [
                    'a.base-card__full-link',
                    'a.job-search-card__link',
                    'a[href*="/jobs/"]'
                ]
                
                # Find title
                title = None
                for selector in title_selectors:
                    title_elem = job.select_one(selector)
                    if title_elem and title_elem.get_text(strip=True):
                        title = title_elem.get_text(strip=True)
                        break
                
                # Find company
                company = None
                for selector in company_selectors:
                    company_elem = job.select_one(selector)
                    if company_elem and company_elem.get_text(strip=True):
                        company = company_elem.get_text(strip=True)
                        break
                
                # Find location
                location = None
                for selector in location_selectors:
                    location_elem = job.select_one(selector)
                    if location_elem and location_elem.get_text(strip=True):
                        location = location_elem.get_text(strip=True)
                        break
                
                # Find link
                link = None
                for selector in link_selectors:
                    link_elem = job.select_one(selector)
                    if link_elem and link_elem.get('href'):
                        link = link_elem.get('href')
                        # Ensure full URL
                        if link and link.startswith('/'):
                            link = f"https://www.linkedin.com{link}"
                        break
                
                if title and link:  # Only add if we have basic info
                    job_data = {
                        'jobTitle': title or 'Not specified',
                        'company': company or 'Not specified',
                        'location': location or 'Not specified',
                        'experience': 'Not specified',  # LinkedIn doesn't always show this
                        'applyLink': link or '',
                        'platform': 'LinkedIn'
                    }
                    
                    # Use link as unique key to avoid duplicates
                    if link not in unique_jobs:
                        unique_jobs[link] = job_data
                        
            except Exception as e:
                logger.warning(f"Error parsing job card: {e}")
                continue
        
        # Convert back to list and limit to max_jobs
        linkedin_jobs = list(unique_jobs.values())[:max_jobs]
        
        logger.info(f"Successfully scraped {len(linkedin_jobs)} unique jobs for '{keyword}'")
        
        return linkedin_jobs
        
    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {str(e)}. Please try again later."
        )
        
    finally:
        # Always quit the driver to avoid resource leaks
        if driver:
            try:
                driver.quit()
                logger.info("Chrome driver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")

# Error handling middleware
@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )