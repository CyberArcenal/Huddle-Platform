## 📄 Updated README.md (with API Documentation)

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
```bash
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

## API Documentation

The Huddle Platform API is fully documented using **OpenAPI 3.0.3**.  
When the server is running, you can access:

- **Interactive Swagger UI** → [`/api/docs/`](http://localhost:8000/api/docs/)  
  Test and explore all endpoints directly from your browser.

- **Raw OpenAPI schema** → [`/api/schema/`](http://localhost:8000/api/schema/)  
  Returns the schema in JSON format. To download as YAML, use `/api/schema/?format=yaml`.

- **Static YAML file** (optional)  
  Save the schema locally by downloading from `/api/schema/?format=yaml` and place it in your project root as `schema.yml` for use with other tools (e.g., Postman, code generators).

---

## Contributing
Contributions are welcome!  
Please fork the repository and submit a pull request.  
Follow the coding style and modular structure outlined in `core/settings/components`.

---

## License
This project is licensed under the **Apache License 2.0** – see the [LICENCE](./LICENCE) file for details.
```