from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import requests
from bs4 import BeautifulSoup
from transformers import pipeline

app = Flask(__name__)

REGISTRATION = "FA23-BAI-024"
NEWS_SOURCE = "Reuters"

def initialize_chrome_driver():
    """Initialize Chrome WebDriver with options"""
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def scrape_reuters_article(keyword):
    """Scrape Reuters for keyword and return first article URL"""
    driver = None
    try:
        driver = initialize_chrome_driver()
        search_url = f"https://www.reuters.com/search/news?keyword={keyword}"
        
        driver.get(search_url)
        time.sleep(3)
        
        # Wait for search results to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[data-testid='Link']"))
            )
        except:
            pass
        
        # Find first article link
        articles = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='Link']")
        
        if not articles:
            articles = driver.find_elements(By.CSS_SELECTOR, "h3 a")
        
        if articles:
            article_link = articles[0].get_attribute("href")
            if article_link and not article_link.startswith("http"):
                article_link = "https://www.reuters.com" + article_link
            return article_link
        
        return None
    
    except Exception as e:
        print(f"Error scraping Reuters: {str(e)}")
        return None
    
    finally:
        if driver:
            driver.quit()

def fetch_article_content(url):
    """Fetch article content from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text
        text = soup.get_text()
        
        # Break into lines and remove leading/trailing space
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text[:2000]  # Limit to 2000 chars for summarization
    
    except Exception as e:
        print(f"Error fetching article: {str(e)}")
        return None

def summarize_text(text):
    """Summarize article text using transformers"""
    try:
        if not text or len(text.split()) < 50:
            return text
        
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
        
        # BART requires input > 50 tokens, split into chunks if needed
        max_chunk = 1024
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < max_chunk:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk)
        
        summaries = []
        for chunk in chunks[:2]:  # Summarize first 2 chunks
            try:
                summary = summarizer(chunk, max_length=150, min_length=30, do_sample=False)
                summaries.append(summary[0]['summary_text'])
            except:
                summaries.append(chunk[:200])
        
        return " ".join(summaries) if summaries else text[:200]
    
    except Exception as e:
        print(f"Error summarizing: {str(e)}")
        return text[:300]

@app.route('/get', methods=['GET'])
def get_news():
    """Main API endpoint"""
    try:
        keyword = request.args.get('keyword', '').strip()
        
        if not keyword:
            return jsonify({
                'error': 'keyword parameter is required'
            }), 400
        
        # Scrape Reuters
        article_url = scrape_reuters_article(keyword)
        
        if not article_url:
            return jsonify({
                'registration': REGISTRATION,
                'newssource': NEWS_SOURCE,
                'keyword': keyword,
                'url': 'No articles found',
                'summary': 'No articles found for the given keyword on Reuters'
            }), 200
        
        # Fetch article content
        article_text = fetch_article_content(article_url)
        
        if not article_text:
            return jsonify({
                'registration': REGISTRATION,
                'newssource': NEWS_SOURCE,
                'keyword': keyword,
                'url': article_url,
                'summary': 'Could not fetch article content'
            }), 200
        
        # Summarize
        summary = summarize_text(article_text)
        
        return jsonify({
            'registration': REGISTRATION,
            'newssource': NEWS_SOURCE,
            'keyword': keyword,
            'url': article_url,
            'summary': summary
        }), 200
    
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'registration': REGISTRATION}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7000, debug=False)
