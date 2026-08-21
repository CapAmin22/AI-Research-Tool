import asyncio
import httpx
import re
import json

async def search(query):
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Origin": "https://duckduckgo.com",
        "Referer": "https://duckduckgo.com/",
    }
    data = {"q": query}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, headers=headers)
        
        # very simple regex extraction for duckduckgo html results
        results = []
        # Find all result snippets
        pattern = r'<a class="result__url" href="([^"]+)".*?>(.*?)</a>.*?<a class="result__snippet[^>]*>(.*?)</a>'
        matches = re.findall(pattern, resp.text, re.IGNORECASE | re.DOTALL)
        
        for url, title, snippet in matches:
            url = url.strip()
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            # extract real url if it's a redirect
            if url.startswith("//duckduckgo.com/l/?uddg="):
                import urllib.parse
                url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            elif url.startswith("/l/?uddg="):
                import urllib.parse
                url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            
            results.append({
                "title": title,
                "url": url,
                "body": snippet
            })
            
        print(json.dumps(results[:3], indent=2))

asyncio.run(search("biotech startups"))
