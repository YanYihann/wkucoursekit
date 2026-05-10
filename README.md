# WKUCourseKit

WKUCourseKit is a Python-first FastAPI web application for Wenzhou-Kean / Kean students to organize mock Simple Syllabus-style course data, syllabi, required materials, and print-friendly course packets.

This project can link students to the official Kean Simple Syllabus pages and can run a local browser-assisted sync after the student signs in. It does not store Kean passwords, proxy login, retrieve copyrighted textbooks, or implement Z-Library downloads. Textbook support is limited to metadata, ISBNs, student checklist status, and legal search links.

## Stack

- Python 3.12
- FastAPI
- Jinja2 templates
- SQLite
- SQLAlchemy
- Pydantic
- pytest
- Minimal JavaScript only when needed later for progressive enhancement

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/seed_db.py
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Current Routes

- `/health`
- `/`: redirects to My Courses
- `/auth/status`: current Kean Simple Syllabus browser-login capture status
- `/auth/refresh`: opens the browser-login capture flow and imports authorized data
- `/courses`: My Courses with server-side search, filters, sorting, and course links
- `/courses/{course_id}`: Course Detail / Syllabus Reader
- `/library`: Syllabus Library search with server-side filters
- `/materials`: Materials checklist with ISBNs and legal access links
- `/print`: Print Center for syllabus packet and material checklist output

## Kean Simple Syllabus Access

WKUCourseKit includes safe external entry points for the official Kean Simple Syllabus pages:

- [Syllabus Library](https://kean.simplesyllabus.com/en-US/syllabus-library)
- [My Courses](https://kean.simplesyllabus.com/en-US/syllabus-library/my-courses)

Students authenticate directly on Kean/Simple Syllabus. WKUCourseKit does not collect passwords. My Courses and Syllabus Library include a login-and-sync panel that opens an observable browser session, waits for the student to sign in, captures authenticated Simple Syllabus Fetch/XHR JSON responses, fetches missing syllabus detail JSON by `docCode`, merges list and detail records, writes the mapped records to SQLite, and renders them through My Courses, Syllabus Library, Materials, and Print Center.

Click `Login and sync` on My Courses or Syllabus Library. The app keeps authentication on the official Kean page, then renders the captured authorized data locally.

After a successful login refresh, WKUCourseKit writes reusable request credentials to `.env`:

```env
SIMPLE_SYLLABUS_COOKIE=...
SIMPLE_SYLLABUS_BEARER_TOKEN=...
SIMPLE_SYLLABUS_SESSION_UPDATED_AT=...
```

Syllabus Library pagination uses those saved credentials with backend HTTP requests, so normal page navigation does not depend on Playwright, an open browser window, or a locked browser profile. Playwright is only used to refresh the Kean login session.

## Language Switching

The UI supports English and Simplified Chinese with server-rendered templates. Use the language switch in the header, or add `?lang=zh` / `?lang=en` to any page URL. The app stores the selection in a lightweight cookie and preserves the selected language in filter forms.

## Seed Mock Data

The repository includes realistic mock Simple Syllabus-style data at `data/mock_syllabus.json`. It is demo data only and does not contain credentials or real syllabus scraping.

```powershell
python scripts/seed_db.py
```

The seed script clears the existing demo records safely, then creates terms, instructors, courses, enrollments, syllabi, ordered syllabus sections, materials, course-material requirements, and student material checklist statuses. Materials are deduplicated by normalized ISBN, so the same textbook assigned to multiple courses is stored once and linked through `course_materials`.

## Architecture

The app is server-rendered. FastAPI owns routing and POST actions, SQLAlchemy owns persistence, Jinja2 owns HTML templates, and CSS in `app/static/css/styles.css` owns the visual system. Search, filters, dashboard summaries, material grouping, ISBN deduplication, and legal-link generation all live in Python services, not frontend JavaScript.

Package layout:

```text
app/
  main.py
  database.py
  models.py
  routes/
  services/
  templates/
  static/
data/
scripts/
tests/
```

## Database Schema

- `terms`: academic term code, name, start date, end date
- `instructors`: instructor name, email, department, office
- `courses`: subject, number, section, title, campus, term, instructor
- `enrollments`: demo student key to course mapping
- `syllabi`: one syllabus per course, mock source label, review status, summary, updated timestamp
- `syllabus_sections`: ordered syllabus text blocks such as grading, schedule, policies, and outcomes
- `materials`: title, authors, ISBN key, ISBN-10, ISBN-13, edition, publisher, material type, legal search URLs
- `course_materials`: course to material join table with required or optional status
- `student_material_statuses`: per-student checklist state such as needed, owned, borrowed, or ordered

## Python Data Services

- `app.services.importer.load_mock_data`
- `app.services.importer.load_syllabus_payload`
- `app.services.simple_syllabus_scraper.sync_from_logged_in_browser`
- `app.services.simple_syllabus_scraper.sync_from_har`
- `app.services.simple_syllabus_scraper.extract_json_responses_from_har`
- `app.services.simple_syllabus_scraper.normalize_scraped_responses`
- `app.services.course_search.search_courses`
- `app.services.course_search.search_by_course_code`
- `app.services.course_search.search_by_title`
- `app.services.course_search.search_by_instructor`
- `app.services.course_search.search_by_syllabus_keyword`
- `app.services.material_service.list_materials_for_enrolled_courses`
- `app.services.material_service.group_materials_by_course`
- `app.services.material_service.deduplicate_materials_by_isbn`
- `app.services.material_service.legal_source_links`
- `app.services.material_service.update_student_material_status`
- `app.services.dashboard_service.dashboard_context`

## Course Objectives Demonstrated

- Python data modeling with SQLAlchemy relationships.
- SQLite persistence and repeatable seeding from JSON.
- Server-rendered FastAPI routes with Jinja2 templates.
- GET-based search and filtering implemented in Python.
- POST form handling for student material checklist status.
- Test coverage for importer behavior, search, filters, ISBN deduplication, legal link generation, and route rendering.
- Browser-assisted integration: official Kean login remains outside WKUCourseKit; the app captures authorized Simple Syllabus JSON, validates and normalizes records, and renders them locally.
- Privacy and copyright boundaries: no Kean password storage, no textbook downloads, only legal material links.

## Development Checks

```powershell
python scripts/seed_db.py
python -m pytest
python -m compileall app tests scripts
```
