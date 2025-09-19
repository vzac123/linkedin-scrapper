from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import feedparser
from typing import List, Dict, Any
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LinkedIn Job Scraper API",
    description="API for scraping job listings using HTTP requests only",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "LinkedIn Job Scraper API",
        "endpoints": {
            "scrape_jobs": "/scrape/?keyword=python",
            "health_check": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

def scrape_linkedin_jobs(keyword: str, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Scrape LinkedIn jobs using HTTP requests only"""
    try:
        jobs = []
        search_query = keyword.replace(' ', '%20')
        
        # Try multiple LinkedIn endpoints
        endpoints = [
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={search_query}",
            f"https://www.linkedin.com/jobs/search/?keywords={search_query}",
            f"https://www.linkedin.com/jobs-guest/jobs/api/jobPostings/{search_query}"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        for endpoint in endpoints:
            try:
                logger.info(f"Trying endpoint: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Try various selectors that LinkedIn might use
                    selectors = [
                        'div.base-card',
                        'li.jobs-search-results__list-item',
                        'div.job-search-card',
                        'section.jobs-search-results__list-item',
                        'div[data-entity-urn*="jobPosting"]',
                        'div.job-result-card'
                    ]
                    
                    for selector in selectors:
                        job_cards = soup.select(selector)
                        if job_cards:
                            logger.info(f"Found {len(job_cards)} jobs with selector: {selector}")
                            
                            for card in job_cards[:max_jobs]:
                                try:
                                    title_elem = card.select_one('h3.base-search-card__title, h3.job-search-card__title, h3[class*="title"], h3')
                                    company_elem = card.select_one('h4.base-search-card__subtitle, h4.job-search-card__subtitle, a[class*="company"], h4')
                                    location_elem = card.select_one('span.job-search-card__location, span[class*="location"], div[class*="location"], span')
                                    link_elem = card.select_one('a.base-card__full-link, a.job-search-card__link, a[href*="/jobs/"]')
                                    
                                    title = title_elem.get_text(strip=True) if title_elem else None
                                    company = company_elem.get_text(strip=True) if company_elem else None
                                    location = location_elem.get_text(strip=True) if location_elem else None
                                    link = link_elem.get('href') if link_elem else None
                                    
                                    if link and link.startswith('/'):
                                        link = f"https://www.linkedin.com{link}"
                                    
                                    if title and link:
                                        jobs.append({
                                            'jobTitle': title,
                                            'company': company or 'Not specified',
                                            'location': location or 'Not specified',
                                            'experience': 'Not specified',
                                            'applyLink': link,
                                            'platform': 'LinkedIn'
                                        })
                                        
                                except Exception as e:
                                    logger.warning(f"Error parsing job card: {e}")
                                    continue
                            
                            if jobs:
                                return jobs[:max_jobs]
                    
            except Exception as e:
                logger.warning(f"Endpoint {endpoint} failed: {e}")
                continue
        
        # If all HTTP methods fail, try RSS
        return scrape_linkedin_rss(keyword, max_jobs)
        
    except Exception as e:
        logger.error(f"LinkedIn scraping failed: {e}")
        return []

def scrape_linkedin_rss(keyword: str, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Try LinkedIn RSS feed as fallback"""
    try:
        jobs = []
        search_query = keyword.replace(' ', '%20')
        rss_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&format=rss"
        
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:max_jobs]:
            try:
                title = entry.get('title', '')
                link = entry.get('link', '')
                description = entry.get('description', '')
                
                # Extract company and location from description
                company = 'Not specified'
                location = 'Not specified'
                
                if description:
                    company_match = re.search(r'Company:?\s*([^\n<]+)', description, re.IGNORECASE)
                    location_match = re.search(r'Location:?\s*([^\n<]+)', description, re.IGNORECASE)
                    
                    if company_match:
                        company = company_match.group(1).strip()
                    if location_match:
                        location = location_match.group(1).strip()
                
                jobs.append({
                    'jobTitle': title,
                    'company': company,
                    'location': location,
                    'experience': 'Not specified',
                    'applyLink': link,
                    'platform': 'LinkedIn'
                })
                
            except Exception as e:
                logger.warning(f"Error parsing RSS entry: {e}")
                continue
                
        return jobs
        
    except Exception as e:
        logger.error(f"RSS scraping failed: {e}")
        return []

def scrape_github_jobs(keyword: str, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Fallback to GitHub Jobs API"""
    try:
        jobs = []
        url = "https://jobs.github.com/positions.json"
        params = {'description': keyword}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for job in data[:max_jobs]:
                jobs.append({
                    'jobTitle': job.get('title', ''),
                    'company': job.get('company', 'Not specified'),
                    'location': job.get('location', 'Not specified'),
                    'experience': 'Not specified',
                    'applyLink': job.get('url', ''),
                    'platform': 'GitHub Jobs'
                })
        
        return jobs
        
    except Exception as e:
        logger.error(f"GitHub Jobs API failed: {e}")
        return []

@app.get("/scrape/", response_model=List[Dict[str, Any]])
async def scrape_data(keyword: str, max_jobs: int = 10):
    """
    Scrape jobs using multiple HTTP-based methods
    Returns empty array if all methods fail
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    logger.info(f"Scraping jobs for: {keyword}")
    
    # Try LinkedIn scraping first
    jobs = scrape_linkedin_jobs(keyword, max_jobs)
    
    # If LinkedIn fails, try GitHub Jobs as fallback
    if not jobs:
        jobs = scrape_github_jobs(keyword, max_jobs)
    
    logger.info(f"Found {len(jobs)} jobs for '{keyword}'")
    return jobs

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
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)