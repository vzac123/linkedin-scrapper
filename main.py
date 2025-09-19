from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import feedparser
from typing import List, Dict, Any
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LinkedIn Job Scraper API",
    description="API for scraping job listings using RSS feeds",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def scrape_linkedin_rss(keyword: str, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Scrape LinkedIn jobs using RSS feed"""
    try:
        jobs = []
        search_query = keyword.replace(' ', '%20')
        
        # LinkedIn RSS feed URL (this is a public endpoint)
        rss_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&format=rss"
        
        # Parse RSS feed
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:max_jobs]:
            try:
                # Extract details from RSS entry
                title = entry.get('title', '')
                link = entry.get('link', '')
                published = entry.get('published', '')
                description = entry.get('description', '')
                
                # Extract company and location from description
                company = 'Not specified'
                location = 'Not specified'
                
                # Try to parse company and location from description
                if description:
                    # Look for common patterns in LinkedIn job descriptions
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
                    'platform': 'LinkedIn',
                    'published': published
                })
                
            except Exception as e:
                logger.warning(f"Error parsing RSS entry: {e}")
                continue
                
        return jobs
        
    except Exception as e:
        logger.error(f"RSS scraping failed: {e}")
        return []

def scrape_serpapi_alternative(keyword: str, max_jobs: int = 10) -> List[Dict[str, Any]]:
    """Alternative approach using HTTP requests (when RSS doesn't work)"""
    try:
        jobs = []
        search_query = keyword.replace(' ', '%20')
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={search_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for job cards - LinkedIn often changes these selectors
            job_cards = soup.find_all('div', class_=lambda x: x and 'base-card' in x) or \
                       soup.find_all('li', class_=lambda x: x and 'job' in x) or \
                       soup.find_all('div', class_=lambda x: x and 'job' in x)
            
            for card in job_cards[:max_jobs]:
                try:
                    title_elem = card.find(['h3', 'h2', 'h4'], class_=lambda x: x and 'title' in str(x).lower())
                    company_elem = card.find(['h4', 'h3', 'span'], class_=lambda x: x and 'company' in str(x).lower())
                    location_elem = card.find(['span', 'div'], class_=lambda x: x and 'location' in str(x).lower())
                    link_elem = card.find('a', href=True)
                    
                    title = title_elem.get_text(strip=True) if title_elem else 'Not specified'
                    company = company_elem.get_text(strip=True) if company_elem else 'Not specified'
                    location = location_elem.get_text(strip=True) if location_elem else 'Not specified'
                    link = link_elem['href'] if link_elem else ''
                    
                    if link and link.startswith('/'):
                        link = f"https://www.linkedin.com{link}"
                    
                    jobs.append({
                        'jobTitle': title,
                        'company': company,
                        'location': location,
                        'experience': 'Not specified',
                        'applyLink': link,
                        'platform': 'LinkedIn'
                    })
                    
                except Exception as e:
                    logger.warning(f"Error parsing job card: {e}")
                    continue
                    
        return jobs
        
    except Exception as e:
        logger.error(f"HTTP scraping failed: {e}")
        return []

@app.get("/")
async def root():
    return {
        "message": "LinkedIn Job Scraper API",
        "endpoints": {
            "scrape_jobs": "/scrape/?keyword=python",
            "health_check": "/health"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

@app.get("/scrape/", response_model=List[Dict[str, Any]])
async def scrape_data(keyword: str, max_jobs: int = 10):
    """
    Scrape LinkedIn jobs using multiple approaches
    Returns real data or empty array if all methods fail
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    logger.info(f"Scraping jobs for: {keyword}")
    
    # Try RSS method first (most reliable for free tier)
    jobs = scrape_linkedin_rss(keyword, max_jobs)
    
    # If RSS fails, try HTTP method
    if not jobs:
        jobs = scrape_serpapi_alternative(keyword, max_jobs)
    
    logger.info(f"Found {len(jobs)} jobs for '{keyword}'")
    return jobs

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)