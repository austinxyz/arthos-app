#!/usr/bin/env python3
"""
Script to refactor main.py by removing watchlist routes that have been extracted to watchlist_routes.py
"""

import re

def refactor_main_py():
    with open('app/main.py', 'r') as f:
        content = f.read()

    # Add watchlist router include after auth router
    router_include = """from app.routers import auth
app.include_router(auth.router)

# Include watchlist routes
from app.routers import watchlist_routes
app.include_router(watchlist_routes.router)
"""

    content = content.replace(
        """from app.routers import auth
app.include_router(auth.router)""",
        router_include
    )

    # Remove watchlist page routes (lines 223-261)
    patterns_to_remove = [
        # Watchlist page routes
        (r'@app\.get\("/watchlists".*?\n.*?async def watchlists_page.*?\n.*?""".*?""".*?\n.*?from app\.services import watchlist_service.*?\n.*?account_id_str.*?\n.*?account_id.*?\n.*?watchlists.*?\n.*?return templates\.TemplateResponse.*?\n\n', ''),
        (r'@app\.get\("/public-watchlists".*?\n.*?async def public_watchlists_page.*?\n.*?""".*?""".*?\n.*?from app\.services import watchlist_service.*?\n.*?watchlists.*?\n.*?return templates\.TemplateResponse.*?\n\n', ''),
        (r'@app\.get\("/create-watchlist"\).*?\n.*?async def create_watchlist_page.*?\n.*?""".*?""".*?\n.*?return templates\.TemplateResponse.*?\n\n', ''),
        # Watchlist detail page routes
        (r'@app\.get\("/watchlist/\{watchlist_id\}".*?\n(?:.*?\n)*?.*?is_owner.*?\n.*?\}\).*?\n\n', ''),
        (r'@app\.get\("/public-watchlist/\{watchlist_id\}".*?\n(?:.*?\n)*?.*?is_public_view.*?\n.*?\}\).*?\n\n', ''),
    ]

    print("Note: Patterns may need manual cleanup. Creating backup and applying simple removals...")

    # Backup original file
    with open('app/main.py.backup', 'w') as f:
        f.write(content)
    print("Created backup: app/main.py.backup")

    # Find and mark sections for removal
    lines = content.split('\n')
    in_watchlist_section = False
    skip_lines = set()

    for i, line in enumerate(lines):
        # Mark watchlist page routes
        if '@app.get("/watchlists"' in line or '@app.get("/public-watchlists"' in line or \
           '@app.get("/create-watchlist")' in line or '@app.get("/watchlist/{watchlist_id}"' in line or \
           '@app.get("/public-watchlist/{watchlist_id}"' in line:
            in_watchlist_section = True
            skip_lines.add(i)
        elif in_watchlist_section:
            skip_lines.add(i)
            # End of route function
            if i > 0 and lines[i].strip() == '' and lines[i-1].strip().endswith(')'):
                in_watchlist_section = False

        # Mark watchlist API models
        if 'class WatchListCreate' in line or 'class WatchListUpdate' in line or \
           'class WatchListVisibilityUpdate' in line or 'class AddStocksRequest' in line:
            in_watchlist_section = True
            skip_lines.add(i)
        elif in_watchlist_section and line.startswith('class '):
            in_watchlist_section = False
        elif in_watchlist_section:
            skip_lines.add(i)

        # Mark watchlist API routes
        if '@app.get("/v1/watchlist' in line or '@app.post("/v1/watchlist' in line or \
           '@app.put("/v1/watchlist' in line or '@app.delete("/v1/watchlist' in line:
            in_watchlist_section = True
            skip_lines.add(i)
        elif in_watchlist_section:
            skip_lines.add(i)
            # End of API route function
            if 'except ValueError' in line and 'HTTPException' in lines[i+1] if i+1 < len(lines) else False:
                # Keep going a few more lines
                pass
            elif i > 0 and lines[i].strip() == '' and not lines[i-1].strip().startswith('#'):
                in_watchlist_section = False

    # Filter out marked lines
    filtered_lines = [line for i, line in enumerate(lines) if i not in skip_lines]
    new_content = '\n'.join(filtered_lines)

    # Write back
    with open('app/main.py', 'w') as f:
        f.write(new_content)

    print("Refactoring complete!")
    print(f"Removed {len(skip_lines)} lines")
    print("Please review app/main.py and compare with app/main.py.backup")

if __name__ == '__main__':
    refactor_main_py()
