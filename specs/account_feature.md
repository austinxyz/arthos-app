# Account Feature Specification

## Goal
Introduce the user account concept to the Arthos application using Google OIDC for authentication. This will allow personalized data (watchlists, risk reversal strategies) linked to specific users.

## 1. Data Model Changes

### New Model: `User`
Create a new file `app/models/user.py`.

```python
class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    google_sub: str = Field(index=True, unique=True, description="Google Subject ID")
    full_name: Optional[str] = None
    picture_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_login_at: datetime = Field(default_factory=datetime.now)
```

### Updates to Existing Models
Add `user_id` foreign key to `WatchList` and `RRWatchlist` models.

**`app/models/watchlist.py`**:
```python
class WatchList(SQLModel, table=True):
    # ... existing fields ...
    user_id: Optional[UUID] = Field(foreign_key="user.id", default=None, index=True)
    user: Optional["User"] = Relationship()
```

**`app/models/rr_watchlist.py`**:
```python
class RRWatchlist(SQLModel, table=True):
    # ... existing fields ...
    user_id: Optional[UUID] = Field(foreign_key="user.id", default=None, index=True)
    user: Optional["User"] = Relationship()
```

### Database Migration
Since the project uses custom migration logic in `app/database.py`, we will need to add new migration functions:
1.  `_create_user_table()`: Ensure User table exists.
2.  `_migrate_watchlist_user_column()`: Add `user_id` to `watchlist` table.
3.  `_migrate_rr_watchlist_user_column()`: Add `user_id` to `rr_watchlist` table.

## 2. Authentication Flow (Google OIDC)

### Dependencies
Add `authlib` and `itsdangerous` (or use Starlette's built-in session support) to `requirements.txt`.
*   `authlib`: High-level OIDC client integration.
*   `httpx`: Already present, can be used by Authlib or for manual calls.
*   `starlette.middleware.sessions.SessionMiddleware`: For maintaining login state via signed cookies.

### Environment Variables
New variables required in `.env`:
*   `GOOGLE_CLIENT_ID`
*   `GOOGLE_CLIENT_SECRET`
*   `SECRET_KEY` (for session signing)

### API Routes
Create `app/routers/auth.py` (and include in `main.py`):

1.  `GET /login`:
    *   Constructs Google OIDC authorization URL.
    *   Redirects user to Google.

2.  `GET /auth/google`: (Callback)
    *   Exchanges code for tokens.
    *   Retrieves user profile (email, sub, name, picture).
    *   **Logic**:
        *   Check if `User` exists by `google_sub`.
        *   If yes, update `last_login_at`, `picture_url`.
        *   If no, create new `User`.
    *   Sets `request.session['user_id']`.
    *   Redirects to home `/`.

3.  `GET /logout`:
    *   Clears session `request.session.clear()`.
    *   Redirects to `/`.

### Middleware / Dependency
Create a dependency `get_current_user` in `app/dependencies.py` (or `services/auth_service.py`).
*   Reads `user_id` from session.
*   Queries DB for User.
*   Returns `User` object or raises/returns None.

## 3. Business Logic Updates

### Access Control
*   **Public Views**: Homepage, Stock Details (generic).
*   **Protected Views**:
    *   Create Watchlist (`/create-watchlist`)
    *   RR List (`/rr-list`) - *Decision needed*: Should everyone see all RRs or only their own? Assumed: Only their own.
*   **API Actions**:
    *   `POST /api/rr-watchlist/save`: Must attach `current_user.id` to the new entry.
    *   `DELETE /api/rr-watchlist/delete/{id}`: Must verify the entry belongs to `current_user` before deleting.

### Service Layer Refactoring
Update `watchlist_service.py` and `rr_watchlist_service.py` functions to accept an optional `user_id`.
*   `get_all_watchlists(user_id: UUID)` -> Filter by user.
*   `save_rr_to_watchlist(...)` -> Accept `user_id`.

## 4. UI Changes

### Base Template (`base.html` or equivalent)
*   Add **User Menu** in Navbar.
    *   If Logged In: Show "Logout", User Name/Avatar.
    *   If Logged Out: Show "Login with Google" button.

### Pages
*   `create_watchlist.html`: Ensure form submission is associated with the user.
*   `rr_list.html`: Only show user's items.
