# Huddle Platform

**Huddle Platform** is a comprehensive, production-ready backend for the **Huddle** social media application. Built with Django and Django REST Framework, it provides a robust, scalable, and feature-rich API to power modern social networking experiences.

The platform is designed with modularity in mind, making it easy to extend and maintain. It includes everything from user authentication and profiles to real-time messaging, content feeds, stories, reels, groups, events, analytics, and an extensive admin panel.

---

## ✨ Features

### Core
- **JWT Authentication** – Secure token-based login with refresh and blacklisting
- **2FA & Security** – Two-factor authentication, login sessions, security logs, and suspicious activity monitoring
- **User Profiles** – Manage profile info, profile picture, cover photo, bio, location, and more
- **Follow System** – Follow/unfollow users, see followers/following lists, mutual follows
- **Search** – Global search across users, posts, groups, and events with history, suggestions, and trends
- **Notifications** – Real-time activity alerts (likes, comments, follows, messages, group invites, event reminders)

### Content & Engagement
- **Posts** – Create, edit, delete, and restore posts (text, image, video, poll). Share posts to groups.
- **Comments** – Nested comment threads, replies, and full threading support.
- **Likes & Reactions** – Like any content (post, comment, story, reel) with multiple reaction types (like, love, care, haha, wow, sad, angry).
- **Shares** – Share posts with optional captions; track share counts.
- **Reels** – Short-form video content with captions, privacy settings, and engagement metrics.
- **Stories** – Ephemeral content (image, video, text) that expires after 24 hours. View tracking and analytics.

### Groups & Communities
- **Group Management** – Create public, private, or secret groups; update details; transfer ownership.
- **Membership** – Join/leave groups, manage member roles (admin, moderator, member), and search members.
- **Group Content** – Post and share content within groups; group-specific feeds.

### Events
- **Event Management** – Create, update, and delete events (public, private, group).
- **RSVP System** – Track attendance (going, maybe, declined) and view attendee lists.
- **Event Analytics** – RSVP trends, statistics, and summaries.

### Messaging
- **Conversations** – Direct and group chats with participants.
- **Messages** – Send text and media messages; mark messages as read.
- **Real-time Ready** – Built with Celery for async tasks, ready for WebSocket integration.

### Analytics
- **Platform Analytics** – Daily metrics (total users, active users, new posts, groups, messages), trends, health scores, and correlations.
- **User Analytics** – Individual activity tracking (posts, likes, comments, followers) with summaries and comparisons.

### Admin Panel
- **User Moderation** – Ban, warn, or remove content; manage user statuses.
- **Reports** – Handle user reports on content with workflows (pending, reviewed, resolved, dismissed).
- **Admin Logs** – Comprehensive audit trail of all admin actions with filtering, search, and export.
- **Bulk Actions** – Activate, deactivate, verify, or delete users in bulk.
- **Cleanup** – Automated cleanup of expired sessions, tokens, OTPs, logs, and analytics.

### Media Handling
- **Cloudinary Integration** – Upload and optimize images, videos, and other media.
- **Profile & Cover Photos** – Upload, crop, and remove.
- **Image Validation** – Validate file size, dimensions, and format before upload.

### Utilities
- **PDF Generation** – Generate reports and exports using PDFKit.
- **Export & GDPR** – Export user data in JSON format for compliance.

---

## 🏗️ Project Structure

The project follows Django best practices with a modular app structure:

```
Huddle-Platform/
├── core/                       # Project root
│   ├── settings/
│   │   ├── base.py             # Base settings
│   │   ├── dev.py              # Development overrides
│   │   ├── prod.py             # Production overrides
│   │   ├── logger.py           # Logging configuration
│   │   └── components/         # Modular component configs
│   │       ├── jwt.py
│   │       ├── cors.py
│   │       ├── cloudinary.py
│   │       ├── celery.py
│   │       ├── pdfkit.py
│   │       ├── validators.py
│   │       └── variables.py
│   ├── urls.py                 # Main URL routing
│   ├── asgi.py / wsgi.py       # ASGI/WSGI entry points
│   └── manage.py               # Django management script
│
├── apps/                        # All Django apps (if organized this way)
│   ├── admin_pannel/            # Admin panel & moderation
│   ├── analytics/               # Platform & user analytics
│   ├── events/                  # Event management
│   ├── feed/                    # Posts, comments, likes, reels, shares
│   ├── groups/                  # Groups & membership
│   ├── messaging/               # Conversations & messages
│   ├── notifications/           # Notification system
│   ├── search/                  # Search engine & history
│   ├── stories/                 # Stories & views
│   └── users/                   # Authentication, profiles, security
│
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker configuration
├── docker-compose.yml           # Docker Compose setup
├── .env.example                 # Environment variables example
└── README.md                    # This file
```

*(Note: The exact app layout may vary; the above represents the logical separation.)*

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL (recommended) or SQLite for development
- Redis (for Celery and caching)
- Docker & Docker Compose (optional, for containerized setup)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/CyberArcenal/Huddle-Platform.git
   cd Huddle-Platform
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   - Copy `.env.example` to `.env` and fill in your values (database, Cloudinary, email, etc.)

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Start the development server**
   ```bash
   python manage.py runserver
   ```

7. **Start Celery worker** (for background tasks)
   ```bash
   celery -A core worker -l info
   ```

### Running with Docker
```bash
docker-compose up -d
```

---

## 📚 API Documentation

The Huddle Platform API is fully documented using **OpenAPI 3.0.3**. When the server is running, you can explore the API interactively:

- **Swagger UI** → [`http://localhost:8000/api/docs/`](http://localhost:8000/api/docs/)  
  Test endpoints, view request/response schemas, and authenticate.

- **ReDoc** → [`http://localhost:8000/api/redoc/`](http://localhost:8000/api/redoc/)  
  A clean, three-panel documentation view.

- **Raw OpenAPI Schema** → [`http://localhost:8000/api/schema/`](http://localhost:8000/api/schema/)  
  Returns JSON. To download as YAML, use `?format=yaml`.

### Key API Modules

| Module          | Description |
|-----------------|-------------|
| **Users**       | Registration, login (with 2FA), profile management, follow system, security settings, admin user management. |
| **Feed**        | Posts, comments, likes, reactions, reels, shares – the core content experience. |
| **Stories**     | Ephemeral content with view tracking and feed grouping. |
| **Groups**      | Create and manage communities, membership, roles, and group content. |
| **Events**      | Organize events, RSVP, attendee lists, and event analytics. |
| **Messaging**   | Direct and group conversations, real‑time message handling. |
| **Notifications** | In-app notifications for user interactions and system events. |
| **Search**      | Global search with history, suggestions, trends, and export. |
| **Analytics**   | Platform‑wide and per‑user analytics with trends and comparisons. |
| **Admin Panel** | Moderation tools, reports, audit logs, bulk actions, and cleanup. |

---

## 🧰 Technology Stack

- **Backend Framework**: Django 5.x, Django REST Framework
- **Database**: PostgreSQL (with SQLite for development)
- **Authentication**: JWT (djangorestframework-simplejwt) with token blacklisting
- **Task Queue**: Celery with Redis broker
- **Media Storage**: Cloudinary
- **PDF Generation**: pdfkit (wkhtmltopdf)
- **API Documentation**: drf-spectacular (OpenAPI 3)
- **Testing**: pytest, factory_boy
- **Containerization**: Docker, Docker Compose

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Write tests for your changes.
4. Ensure all tests pass (`pytest`).
5. Submit a pull request with a clear description of your changes.

Please adhere to the existing code style and modular structure.

---

## 📄 License

This project is licensed under the **Apache License 2.0** – see the [LICENSE](./LICENSE) file for details.

---

## 📞 Contact

For questions, suggestions, or collaboration, please open an issue on GitHub or reach out to the maintainers.

---

**Built with ❤️ by the Huddle Team**