from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.services.importer import DEFAULT_MOCK_DATA_PATH, load_mock_data
from app.services.importer import load_syllabus_payload
from app.services.course_catalog import CatalogOption, CatalogSearchResult, CatalogSection
from app.services.simple_syllabus_scraper import BrowserSyncResult


def test_health_check() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_redirects_to_my_courses() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "WKUCourseKit" in response.text
    assert "My Courses" in response.text


def test_server_rendered_pages_render_seeded_data(monkeypatch) -> None:
    with SessionLocal() as db:
        load_mock_data(db, DEFAULT_MOCK_DATA_PATH, reset=True)
    monkeypatch.setattr(
        "app.routes.pages.read_library_search_meta",
        lambda filters=None: {"total": 1, "page_size": 50},
    )

    paths = [
        "/",
        "/courses",
        "/library?title=Python",
        "/courses/1",
        "/materials?status=needed",
        "/print",
    ]

    with TestClient(app) as client:
        responses = [client.get(path) for path in paths]

    assert all(response.status_code == 200 for response in responses)
    assert "Python Software Development" in responses[1].text
    assert "Syllabus Library" in responses[2].text
    assert "Sign In" in responses[1].text or "auth-user" in responses[1].text
    assert "Login, crawl, render" not in responses[1].text
    assert "Legal access" in responses[4].text
    assert "Syllabus packet" in responses[5].text


def test_course_catalog_renders_fall_2026_wenzhou_sections(monkeypatch) -> None:
    section = CatalogSection(
        id="26595",
        course_id="6228",
        subject="CPS",
        course_number="2232",
        section="W01",
        title="Computer Organization",
        term="Fall 2026 Wenzhou",
        location="WENZHOU-KEAN UNIVERSITY",
        dates="8/31/2026-12/17/2026",
        credits="3 Credits",
        instructors="Catalog Instructor",
        meetings=("Monday, Wednesday 10:00 AM - 11:45 AM TBD (Lecture)",),
        availability_status="Open",
        availability="24 / 24 / 0",
        available=24,
        capacity=24,
        enrolled=0,
        waitlisted=0,
        methods=("Lecture",),
        comments="",
        bookstore_url="https://kean.bncollege.com/",
        description="Catalog description.",
    )
    result = CatalogSearchResult(
        sections=(section,),
        total=1,
        total_pages=1,
        page=1,
        page_size=30,
        subjects=(CatalogOption("CPS", "Computer Science", 1),),
        faculty=(CatalogOption("123", "Catalog Instructor", 1),),
        locations=(CatalogOption("W", "WENZHOU-KEAN UNIVERSITY", 1),),
        source_url="https://kean-ss.colleague.elluciancloud.com/Student/Student/Courses/Search?searchResultsView=SectionListing&terms=2026FAW",
        fetched_at="2026-05-10T00:00:00+00:00",
    )

    def fake_search_course_catalog(**kwargs):
        assert kwargs["page_size"] == 30
        return result

    monkeypatch.setattr("app.routes.pages.search_course_catalog", fake_search_course_catalog)

    with TestClient(app) as client:
        response = client.get("/catalog?subject=CPS&course_number=2232")

    assert response.status_code == 200
    assert "Course Catalog" in response.text
    assert "Fall 2026 Wenzhou" in response.text
    assert "CPS 2232-W01" in response.text
    assert "Computer Organization" in response.text
    assert "Catalog Instructor" in response.text
    assert "Credits" in response.text
    assert "3 Credits" in response.text
    assert "https://kean.bncollege.com/" not in response.text


def test_signed_in_header_prefers_account_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routes.pages.current_simple_syllabus_auth_snapshot",
        lambda: {
            "status": "success",
            "message": "Signed in",
            "updated_at": "2026-05-10T00:00:00+08:00",
            "profile_ready": True,
            "session_ready": True,
            "session_updated_at": "2026-05-10T00:00:00+08:00",
            "account_name": "",
            "account_email": "student@kean.edu",
            "signed_in": True,
        },
    )

    with TestClient(app) as client:
        response = client.get("/courses")

    assert response.status_code == 200
    assert "student@kean.edu" in response.text
    assert ">Kean signed in<" not in response.text


def test_course_detail_bolds_class_and_instructor_labels() -> None:
    payload = {
        "student_key": "detail-label-test",
        "terms": [
            {
                "code": "2026SPW",
                "name": "Spring 2026 Wenzhou",
                "courses": [
                    {
                        "subject": "COMM",
                        "course_number": "3590",
                        "section": "W11",
                        "title": "Business & Prof. Comm",
                        "enrolled": True,
                        "instructor": {
                            "full_name": "Yingshin Chin",
                            "email": "ychin@kean.edu",
                            "office": "GEH C415",
                        },
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "",
                            "sections": [
                                {
                                    "heading": "Class Information",
                                    "body": "Course Title: Business & Prof. Comm\nCourse Number and Section: COMM 3590 W11",
                                },
                                {
                                    "heading": "Instructor Information",
                                    "body": "Instructor Name: Yingshin Chin\nEmail: ychin@kean.edu",
                                },
                                {
                                    "heading": "Program Learning Outcomes",
                                    "body": "This section should not be printed in the syllabus packet.",
                                },
                            ],
                        },
                        "materials": [],
                    }
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)

    with TestClient(app) as client:
        response = client.get("/courses/1")
        print_response = client.get("/print?term=2026SPW")

    assert response.status_code == 200
    assert "<strong>Course Title:</strong> Business &amp; Prof. Comm" in response.text
    assert "<strong>Instructor Name:</strong> Yingshin Chin" in response.text
    assert print_response.status_code == 200
    assert "Class Information" in print_response.text
    assert "Instructor Information" in print_response.text
    assert "<strong>Course Title:</strong> Business &amp; Prof. Comm" in print_response.text
    assert "<strong>Instructor Name:</strong> Yingshin Chin" in print_response.text
    assert "Program Learning Outcomes" not in print_response.text
    assert "This section should not be printed" not in print_response.text


def test_auth_refresh_imports_scraped_courses(monkeypatch) -> None:
    started = []

    def fake_start_simple_syllabus_background_sync():
        started.append(True)
        return True

    monkeypatch.setattr("app.routes.pages.start_simple_syllabus_background_sync", fake_start_simple_syllabus_background_sync)

    with TestClient(app) as client:
        sync_response = client.post(
            "/auth/refresh",
            data={"next_url": "/courses?q=Auto"},
            follow_redirects=False,
        )

    assert sync_response.status_code == 303
    assert sync_response.headers["location"] == "/courses?q=Auto&sync=started"
    assert started == [True]


def test_auth_refresh_on_vercel_redirects_to_kean_login(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(
        "app.routes.pages.start_simple_syllabus_background_sync",
        lambda: (_ for _ in ()).throw(AssertionError("Vercel should not start local browser sync")),
    )

    with TestClient(app) as client:
        response = client.post("/auth/refresh", data={"next_url": "/courses"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://kean.simplesyllabus.com/en-US/syllabus-library/my-courses"


def test_auth_refresh_on_render_redirects_to_kean_login(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(
        "app.routes.pages.start_simple_syllabus_background_sync",
        lambda: (_ for _ in ()).throw(AssertionError("Render should not start local browser sync")),
    )

    with TestClient(app) as client:
        response = client.post("/auth/refresh", data={"next_url": "/courses"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://kean.simplesyllabus.com/en-US/syllabus-library/my-courses"


def test_render_courses_page_shows_cloud_sync_bookmarklet(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")

    with TestClient(app) as client:
        response = client.get("/courses")

    assert response.status_code == 200
    assert "Cloud sync" in response.text
    assert "javascript:(async()" in response.text
    assert "/api/simple-syllabus/import-responses" in response.text


def test_browser_submitted_simple_syllabus_json_imports_courses() -> None:
    payload = {
        "responses": [
            {
                "url": "https://kean.simplesyllabus.com/api/doc-library-search?my_courses=true",
                "payload": {
                    "results": [
                        {
                            "courseCode": "CPS 4500",
                            "section": "W01",
                            "courseTitle": "CPS 4500 - Cloud Imported Course",
                            "term": "Spring 2026",
                            "instructor": {"name": "Cloud Instructor"},
                            "description": "Imported from the browser on Kean.",
                        }
                    ]
                },
            }
        ]
    }

    with TestClient(app) as client:
        response = client.post("/api/simple-syllabus/import-responses", json=payload)
        courses_response = client.get("/courses?q=Cloud")

    assert response.status_code == 200
    assert response.json()["course_count"] == 1
    assert "Cloud Imported Course" in courses_response.text


def test_simple_syllabus_page_is_removed() -> None:
    with TestClient(app) as client:
        response = client.get("/simple-syllabus", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/courses"


def test_library_q_parameter_and_materials_page_without_student_status(monkeypatch) -> None:
    with SessionLocal() as db:
        load_mock_data(db, DEFAULT_MOCK_DATA_PATH, reset=True)
    monkeypatch.setattr(
        "app.routes.pages.read_library_search_meta",
        lambda filters=None: {"total": 1, "page_size": 50},
    )

    with TestClient(app) as client:
        library_response = client.get("/library?q=translation")
        materials_response = client.get("/materials?q=Rosen")
        post_response = client.post("/materials/status", follow_redirects=False)

    assert library_response.status_code == 200
    assert "World Literature" in library_response.text
    assert materials_response.status_code == 200
    assert "Discrete Mathematics and Its Applications" in materials_response.text
    assert "https://z-lib.by/s/9781259676512" in materials_response.text
    assert "Open all Z-Lib searches" in materials_response.text
    assert "openAllMaterialSources" in materials_response.text
    assert "WorldCat" not in materials_response.text
    assert ">Library<" not in materials_response.text
    assert "Bookstore" not in materials_response.text
    assert "Student status" not in materials_response.text
    assert post_response.status_code == 404


def test_library_pagination_renders_second_page(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": f"{1000 + index}",
                        "section": "W01",
                        "title": f"Library Course {index}",
                        "enrolled": False,
                        "instructor": {"full_name": "Library Instructor"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Library list record.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for index in range(1, 56)
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)
    monkeypatch.setattr(
        "app.routes.pages.read_library_search_meta",
        lambda filters=None: {"total": 55, "page_size": 50},
    )

    with TestClient(app) as client:
        response = client.get("/library?sort=course_code&page=2")

    assert response.status_code == 200
    assert "51-55 / 55 results" in response.text
    assert "Library Course 51" in response.text
    assert "CPS 1001-W01" not in response.text
    assert "Previous" in response.text


def test_library_renders_all_sections_like_kean_library(monkeypatch) -> None:
    payload = {
        "student_key": "section-group-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": "2232",
                        "section": section,
                        "title": "Computer Organization",
                        "enrolled": False,
                        "instructor": {"full_name": f"Instructor {section}"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Course description copied from the all courses library result.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for section in ("W01", "W02", "W03")
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)
    monkeypatch.setattr(
        "app.routes.pages.read_library_search_meta",
        lambda filters=None: {"total": 3, "page_size": 50},
    )

    with TestClient(app) as client:
        response = client.get("/library?course_code=CPS%202232")

    assert response.status_code == 200
    assert response.text.count('<article class="result-row') == 3
    assert "CPS 2232-W01" in response.text
    assert "CPS 2232-W02" in response.text
    assert "CPS 2232-W03" in response.text
    assert "Show 2 other sections" not in response.text
    assert "Course description copied from the all courses library result." not in response.text


def test_library_next_page_lazy_loads_kean_page(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": f"{1000 + index}",
                        "section": "W01",
                        "title": f"Cached Library Course {index}",
                        "enrolled": False,
                        "instructor": {"full_name": "Library Instructor"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Library list record.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for index in range(1, 51)
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)

    def fake_read_library_search_meta(filters=None):
        return {"total": 100, "page_size": 50}

    def fake_sync_library_page_from_saved_kean_session(*, page_number, page_size, filters=None, reset=False):
        assert page_number == 1
        assert page_size == 50
        with SessionLocal() as db:
            load_syllabus_payload(
                db,
                {
                    "student_key": "pagination-test",
                    "terms": [
                        {
                            "code": "2026SP",
                            "name": "Spring 2026",
                            "courses": [
                                {
                                    "subject": "CPS",
                                    "course_number": "2051",
                                    "section": "W01",
                                    "title": "Lazy Loaded Library Course",
                                    "enrolled": False,
                                    "instructor": {"full_name": "Library Instructor"},
                                    "syllabus": {
                                        "source_label": "Kean Simple Syllabus",
                                        "summary": "Library list record.",
                                        "sections": [],
                                    },
                                    "materials": [],
                                }
                            ],
                        }
                    ],
                },
                reset=reset,
            )
        return BrowserSyncResult(counts={}, response_count=1, course_count=1)

    monkeypatch.setattr("app.routes.pages.read_library_search_meta", fake_read_library_search_meta)
    monkeypatch.setattr(
        "app.routes.pages.sync_library_page_from_saved_kean_session",
        fake_sync_library_page_from_saved_kean_session,
    )

    with TestClient(app) as client:
        response = client.get("/library?term=&page=2&sort=course_code")

    assert response.status_code == 200
    assert "51-100 / 100 results" in response.text
    assert "Lazy Loaded Library Course" in response.text


def test_library_lazy_load_failure_renders_notice(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": f"{1000 + index}",
                        "section": "W01",
                        "title": f"Cached Library Course {index}",
                        "enrolled": False,
                        "instructor": {"full_name": "Library Instructor"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Library list record.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for index in range(1, 51)
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)

    monkeypatch.setattr(
        "app.routes.pages.read_library_search_meta",
        lambda filters=None: {"total": 100, "page_size": 50},
    )

    def fake_sync_library_page_from_saved_kean_session(*_args, **_kwargs):
        raise RuntimeError("browser bridge failed")

    monkeypatch.setattr(
        "app.routes.pages.sync_library_page_from_saved_kean_session",
        fake_sync_library_page_from_saved_kean_session,
    )

    with TestClient(app) as client:
        response = client.get("/library?page=2&sort=course_code")

    assert response.status_code == 200
    assert "Kean lazy load failed" in response.text
    assert "browser bridge failed" in response.text


def test_library_fetches_remote_total_before_rendering(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": f"{1000 + index}",
                        "section": "W01",
                        "title": f"Cached Library Course {index}",
                        "enrolled": False,
                        "instructor": {"full_name": "Library Instructor"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Library list record.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for index in range(1, 51)
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)
    remote_meta: dict[str, int] = {}
    calls: list[tuple[int, int]] = []

    def fake_read_library_search_meta(filters=None):
        return dict(remote_meta)

    def fake_sync_library_page_from_saved_kean_session(*, page_number, page_size, filters=None, reset=False):
        calls.append((page_number, page_size))
        remote_meta.update({"total": 150, "page_size": 50})
        return BrowserSyncResult(counts={}, response_count=1, course_count=0)

    monkeypatch.setattr("app.routes.pages.read_library_search_meta", fake_read_library_search_meta)
    monkeypatch.setattr(
        "app.routes.pages.sync_library_page_from_saved_kean_session",
        fake_sync_library_page_from_saved_kean_session,
    )

    with TestClient(app) as client:
        first_page = client.get("/library?term=")

    assert first_page.status_code == 200
    assert calls == [(0, 50)]
    assert "1-50 / 150 results" in first_page.text
    assert 'page=2' in first_page.text


def test_library_filter_total_uses_matching_remote_meta(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": "3320",
                        "section": f"W{index:02d}",
                        "title": f"Software Project {index}",
                        "enrolled": False,
                        "instructor": {"full_name": "Dr. Lin"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Library list record.",
                            "sections": [],
                        },
                        "materials": [],
                    }
                    for index in range(1, 11)
                ],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)

    def fake_read_library_search_meta(filters=None):
        assert filters == {"subject_name": "CPS", "course_number": "3320"}
        return {"total": 7, "page_size": 50}

    def unexpected_sync(*_args, **_kwargs):
        raise AssertionError("filter meta should avoid browser sync")

    monkeypatch.setattr("app.routes.pages.read_library_search_meta", fake_read_library_search_meta)
    monkeypatch.setattr("app.routes.pages.sync_library_page_from_saved_kean_session", unexpected_sync)

    with TestClient(app) as client:
        response = client.get("/library?course_code=CPS%203320")

    assert response.status_code == 200
    assert "1-7 / 7 results" in response.text


def test_library_filters_use_cached_remote_term_and_subject_facets(monkeypatch) -> None:
    payload = {
        "student_key": "pagination-test",
        "terms": [
            {
                "code": "2026SP",
                "name": "Spring 2026",
                "courses": [],
            }
        ],
    }
    with SessionLocal() as db:
        load_syllabus_payload(db, payload, reset=True)

    monkeypatch.setattr("app.routes.pages.read_library_search_meta", lambda filters=None: {"total": 0, "page_size": 50})
    monkeypatch.setattr(
        "app.routes.pages.read_library_filter_facets",
        lambda: {
            "terms": [{"code": "2026FA", "name": "2026FA"}, {"code": "2026SU", "name": "2026SU"}],
            "subjects": ["COMM", "CPS", "MATH"],
        },
    )

    with TestClient(app) as client:
        response = client.get("/library")

    assert response.status_code == 200
    assert '<option value="2026FA"' in response.text
    assert '<option value="2026SU"' in response.text
    assert '<option value="2026SP"' in response.text
    assert '<option value="COMM"' in response.text
    assert '<option value="MATH"' in response.text


def test_language_switch_renders_chinese_and_sets_cookie() -> None:
    with TestClient(app) as client:
        response = client.get("/courses?lang=zh&q=CPS")

    assert response.status_code == 200
    assert "我的课程" in response.text
    assert "课程列表" in response.text
    assert "lang=zh" in response.text
    assert response.cookies.get("wkcoursekit_lang") == "zh"


def test_language_cookie_is_used_when_query_param_is_absent() -> None:
    with TestClient(app) as client:
        client.get("/?lang=zh")
        response = client.get("/materials")

    assert response.status_code == 200
    assert "课程材料" in response.text
    assert "合法获取" in response.text
