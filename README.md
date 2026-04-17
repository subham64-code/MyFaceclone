# MyFaceClone

A Facebook-inspired social network web application built with **Django** (backend), **HTML/CSS/JavaScript** (frontend).

## Features

- 🔐 **Authentication** – Sign up (with modal), log in and log out
- 📰 **News Feed** – Create posts (text + photo), like/unlike, comment in real time
- 👤 **User Profiles** – Cover photo, avatar, bio, location, and personal post wall
- 🤝 **Friend Requests** – Send, accept or decline friend requests
- 📐 **Responsive 3-column layout** – Left sidebar, feed, right sidebar (People You May Know, Contacts)

## Tech Stack

| Layer    | Technology |
|----------|-----------|
| Backend  | Django 4.2+ |
| Database | SQLite (dev) |
| Frontend | HTML5, CSS3 (custom Facebook-inspired theme), Vanilla JavaScript |
| Icons    | Font Awesome 6 |
| Images   | Pillow (Django ImageField) |

## Screenshots

### Landing Page
![Landing Page](https://github.com/user-attachments/assets/0f2dd320-c2b7-429b-9ad9-6d56751deb06)

### Sign Up Modal
![Sign Up Modal](https://github.com/user-attachments/assets/b8637c9c-db29-4657-a50e-fc0db698cf45)

### Home Feed
![Home Feed](https://github.com/user-attachments/assets/be4e5bbb-bf4a-49cd-968d-cde53b398025)

## Getting Started

### Prerequisites

- Python 3.10+

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/subham64-code/MyFaceclone.git
cd MyFaceclone

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Apply database migrations
python manage.py migrate

# 5. (Optional) Create a superuser for the admin panel
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser.

## Project Structure

```
MyFaceclone/
├── core/                  # Main Django app
│   ├── models.py          # Post, Like, Comment, FriendRequest, Profile
│   ├── views.py           # All views (home, auth, post, profile, friends)
│   ├── urls.py            # URL routing
│   ├── admin.py           # Django admin registrations
│   ├── signals.py         # Auto-create Profile on user creation
│   └── migrations/        # Database migrations
├── myface/                # Django project configuration
│   ├── settings.py
│   └── urls.py
├── templates/
│   ├── base.html          # Base template with navbar
│   └── home/
│       ├── landing.html   # Login / sign-up landing page
│       ├── index.html     # Home feed (3-column layout)
│       └── profile.html   # User profile page
├── static/
│   ├── css/style.css      # Facebook-inspired stylesheet
│   └── js/main.js         # Like, comment, post-modal interactions
├── media/                 # User-uploaded images (gitignored)
├── requirements.txt
└── manage.py
```

## Running Tests

```bash
python manage.py test core
```
