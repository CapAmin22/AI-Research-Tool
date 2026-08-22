import asyncio
import sys
import os
from patchright.async_api import async_playwright
import time

async def inject(li_at):
    user_data_dir = os.path.expanduser("~/.linkedin-mcp/profile")
    
    # Ensure profile directory exists
    os.makedirs(user_data_dir, exist_ok=True)
    
    async with async_playwright() as p:
        try:
            # We don't want to load pages, just the context to write the cookie to the SQLite DB
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,
                args=["--no-sandbox", "--disable-gpu"]
            )
            
            await context.add_cookies([
                {
                    "name": "li_at",
                    "value": li_at,
                    "domain": ".linkedin.com",
                    "path": "/"
                },
                {
                    "name": "JSESSIONID",
                    "value": '"ajax:1234567890123456789"',
                    "domain": ".linkedin.com",
                    "path": "/"
                }
            ])
            
            await context.close()
            print(f"[{time.time()}] Successfully injected li_at cookie to profile DB.")
        except Exception as e:
            print(f"[{time.time()}] Error injecting cookie: {e}")
            sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inject_cookie_fast.py <li_at_cookie>")
        sys.exit(1)
        
    li_at_cookie = sys.argv[1]
    asyncio.run(inject(li_at_cookie))
