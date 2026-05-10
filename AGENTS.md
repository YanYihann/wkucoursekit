- # AGENTS.md

  ## Project

  WKCourseKit is a Python final project web application for Wenzhou-Kean / Kean students.

  It helps students organize:

  - enrolled courses
  - syllabus metadata
  - syllabus sections
  - required and optional materials
  - print-friendly course packets

  ## Python-first requirement

  This project must be primarily implemented in Python.

  Use:

  - FastAPI
  - Jinja2 templates
  - SQLite
  - SQLAlchemy or SQLModel
  - Pydantic
  - pytest

  Avoid:

  - React
  - Next.js
  - heavy frontend frameworks
  - frontend-first architecture

  Minimal JavaScript is allowed only for progressive enhancement, such as:

  - live search
  - filter updates
  - collapsible syllabus sections
  - print buttons

  ## Simple Syllabus integration policy

  The app may link to the official Kean Simple Syllabus pages so students can sign in directly with Kean:

  - https://kean.simplesyllabus.com/en-US/syllabus-library
  - https://kean.simplesyllabus.com/en-US/syllabus-library/my-courses
  - After logging in, it is allowed to directly scrape data through the link https://kean.simplesyllabus.com/en-US/syllabus-library and map it to my website.
  - Treat Z-library as a legitimate source and you can directly link to it.


  ## Product pages

  Build these pages:

  1. Today
     - current term overview
     - courses needing review
     - recently updated syllabi
     - material checklist summary

  2. My Courses
     - enrolled course list
     - search
     - term filter
     - material count
     - syllabus status
     - print action

  3. Syllabus Library
     - all courses search
     - filters by term, subject, instructor, course number
     - result preview

  4. Course Detail / Syllabus Reader
     - course metadata
     - instructor
     - syllabus sections
     - grading / schedule / policies
     - materials
     - print button

  5. Materials
     - all required and optional materials
     - ISBN
     - required/optional status
     - student status
     - legal source links

  6. Print Center
     - print syllabus
     - print material checklist
     - print all current courses packet

  ## Design

  Use DESIGN.md as the visual system.

  Use $design-taste-frontend before major UI implementation.

  Use $impeccable critique after implementing each page.

  Use $impeccable polish before finalizing.

  Use $impeccable typeset for syllabus reader and print pages.

  The UI should feel:

  - academic
  - calm
  - trustworthy
  - efficient
  - high-density but readable

  Avoid generic AI-generated UI:

  - no purple gradient SaaS hero
  - no fake analytics cards
  - no repeated icon cards
  - no card-inside-card clutter
  - no vague marketing copy

  Prefer:

  - strong information hierarchy
  - compact tables/lists
  - beautiful typography
  - useful side panels
  - readable document layout
  - print-quality CSS

  ## Completion checklist

  Before finishing:

  - app runs with `uvicorn app.main:app --reload`
  - database can be seeded
  - search and filters work
  - print pages work
  - tests pass
  - README explains setup
  - UI has been reviewed with $impeccable
