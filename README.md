# Huddle Platform

Huddle Platform is a Django-powered backend for the **Huddle** social media app.  
It provides scalable APIs for feeds, profiles, messaging, groups, and notifications, designed with modular architecture and audit clarity.  
Built to support community-driven connections, it serves as the foundation for mobile and web clients.

---

## Features
- **User Profiles** – manage accounts, bios, and media
- **News Feed** – posts, comments, and interactions
- **Messaging** – real-time communication with Celery tasks
- **Groups & Communities** – organize discussions and events
- **Notifications** – activity alerts with audit logging
- **Media Integration** – Cloudinary support for images/videos
- **PDF Generation** – via PDFKit for reports or exports
- **JWT Authentication** – secure token-based login

---

## Project Structure
```
core/
 ├── settings/
 │    ├── base.py          # Base Django settings
 │    ├── dev.py           # Development overrides
 │    ├── prod.py          # Production overrides
 │    ├── logger.py        # Logging configuration
 │    └── components/      # Modular integrations
 │         ├── jwt.py
 │         ├── cors.py
 │         ├── cloudinary.py
 │         ├── celery.py
 │         ├── pdfkit.py
 │         ├── validators.py
 │         └── variables.py
 ├── urls.py               # URL routing
 ├── asgi.py / wsgi.py     # Entry points
 └── manage.py             # Django management script
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- Django 5.x
- Docker & Docker Compose (optional for containerized setup)

### Installation
```bash
git clone https://github.com/CyberArcenal/Huddle-Platform.git
cd Huddle-Platform
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Running the Server
```bash
python manage.py migrate
python manage.py runserver
```

---

## Contributing
Contributions are welcome!  
Please fork the repository and submit a pull request.  
Follow the coding style and modular structure outlined in `core/settings/components`.

---

## License
This project is licensed under the **Apache License 2.0** – see the `[Looks like the result wasn't safe to show. Let's switch things up and try something else!]` file for details.
