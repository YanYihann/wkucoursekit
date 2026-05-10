from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Course, CourseMaterial, Enrollment, Instructor, Material, StudentMaterialStatus, Syllabus, SyllabusSection, Term
from app.services.courses import (
    filter_by_has_materials,
    filter_by_instructor,
    filter_by_subject,
    filter_by_term,
    search_by_course_code,
    search_by_instructor,
    search_by_syllabus_keyword,
    search_by_title,
    search_courses,
)
from app.services.importer import DEFAULT_MOCK_DATA_PATH, load_mock_data, load_syllabus_payload
from app.services.material_service import (
    deduplicate_materials_by_isbn,
    legal_source_links,
    list_materials_for_enrolled_courses,
    update_student_material_status,
)
from app.services.simple_syllabus import SimpleSyllabusSettings, import_from_authorization_code
from app.services.simple_syllabus_scraper import (
    build_library_search_filters,
    build_historic_my_courses_search_url,
    clear_library_search_meta,
    fetch_simple_syllabus_json_with_session,
    extract_json_responses_from_har,
    fetch_library_search_page,
    read_library_filter_facets,
    read_library_search_meta,
    read_env_values,
    read_simple_syllabus_session,
    normalize_scraped_responses,
    save_simple_syllabus_session_from_context,
    write_library_facets_from_responses,
)


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with TestingSessionLocal() as session:
        load_mock_data(session, DEFAULT_MOCK_DATA_PATH, reset=True)
        yield session
    Base.metadata.drop_all(bind=engine)


def test_importer_loads_realistic_mock_data(db: Session) -> None:
    assert db.scalar(select(func.count()).select_from(Term)) == 2
    assert db.scalar(select(func.count()).select_from(Instructor)) == 8
    assert db.scalar(select(func.count()).select_from(Course)) == 8
    assert db.scalar(select(func.count()).select_from(Syllabus)) == 8
    assert db.scalar(select(func.count()).select_from(SyllabusSection)) == 21
    assert db.scalar(select(func.count()).select_from(CourseMaterial)) == 8
    assert db.scalar(select(func.count()).select_from(StudentMaterialStatus)) == 7

    python_course = db.scalar(select(Course).where(Course.subject == "CPS", Course.course_number == "3320"))
    assert python_course is not None
    assert python_course.instructor.full_name == "Dr. Linnea Vos"
    assert python_course.syllabus is not None
    assert python_course.syllabus.status == "not_reviewed"


def test_search_by_course_code_title_and_instructor(db: Session) -> None:
    by_code = search_by_course_code(db, "cps 3320")
    assert [course.code for course in by_code] == ["CPS 3320-W01"]

    by_title = search_by_title(db, "professional")
    assert [course.code for course in by_title] == ["ENG 3090-W04"]

    by_instructor = search_by_instructor(db, "ruan")
    assert [course.code for course in by_instructor] == ["MGS 3030-W01"]

    by_keyword = search_by_syllabus_keyword(db, "translation")
    assert [course.code for course in by_keyword] == ["ENG 2403-W02"]


def test_filters_by_term_subject_and_material_presence(db: Session) -> None:
    spring_courses = filter_by_term(db, "2026SP")
    assert {course.code for course in spring_courses} == {
        "CPS 2231-W02",
        "CPS 3320-W01",
        "ENG 3090-W04",
        "MATH 2415-W03",
    }

    cps_courses = filter_by_subject(db, "cps")
    assert [course.code for course in cps_courses] == ["CPS 2231-W02", "CPS 3320-W01"]

    without_materials = filter_by_has_materials(db, False)
    assert [course.code for course in without_materials] == ["COMM 2500-W05"]

    by_instructor_filter = filter_by_instructor(db, "Hale")
    assert [course.code for course in by_instructor_filter] == ["MATH 1054-W06"]


def test_combined_search_and_updated_date_sort(db: Session) -> None:
    results = search_courses(db, term="2026SP", has_materials=True, sort="-updated_date")

    assert [course.code for course in results] == [
        "ENG 3090-W04",
        "CPS 3320-W01",
        "CPS 2231-W02",
        "MATH 2415-W03",
    ]

    title_sorted = search_courses(db, term="2025FA", sort="title")
    assert [course.title for course in title_sorted] == [
        "Operations Management",
        "Precalculus",
        "Public Speaking",
        "World Literature",
    ]


def test_material_deduplication_by_isbn(db: Session) -> None:
    python_crash_course = db.scalars(
        select(Material).where(Material.isbn_key == "9781718502703")
    ).all()

    assert len(python_crash_course) == 1
    material = python_crash_course[0]
    assert material.title == "Python Crash Course"
    assert material.legal_search_url == "https://www.worldcat.org/isbn/9781718502703"
    assert len(material.courses) == 2
    assert db.scalar(select(func.count()).select_from(Material)) == 7


def test_legal_link_generation_and_material_status_update(db: Session) -> None:
    rows = list_materials_for_enrolled_courses(db, student_key="demo-student", q="Rosen")
    assert len(rows) == 1
    links = legal_source_links(rows[0].material)
    assert links["worldcat"].startswith("https://www.worldcat.org/")
    assert "9781259676512" in links["library"]
    assert links["zlib"] == "https://z-lib.by/s/9781259676512"

    updated = update_student_material_status(
        db,
        student_key="demo-student",
        material_id=rows[0].material.id,
        status="owned",
    )
    assert updated.status == "owned"

    refreshed = list_materials_for_enrolled_courses(db, student_key="demo-student", q="Rosen")
    assert refreshed[0].status is not None
    assert refreshed[0].status.status == "owned"


def test_legal_link_generation_uses_title_and_author_without_isbn() -> None:
    material = Material(
        title="Business and Professional Communication",
        authors="James DiSanza, Nancy Legge",
        material_type="textbook",
    )

    links = legal_source_links(material)

    assert "Business+and+Professional+Communication+James+DiSanza%2C+Nancy+Legge" in links["worldcat"]
    assert "Business+and+Professional+Communication+James+DiSanza%2C+Nancy+Legge" in links["library"]
    assert links["zlib"] == "https://z-lib.by/s/Business%20and%20Professional%20Communication%20James%20DiSanza%2C%20Nancy%20Legge"


def test_material_service_deduplicates_by_isbn(db: Session) -> None:
    rows = list_materials_for_enrolled_courses(db, student_key="demo-student")
    materials = deduplicate_materials_by_isbn(rows)

    assert len(rows) == 8
    assert len(materials) == 7


def test_oauth_callback_import_fetches_api_payload_and_replaces_local_data(db: Session, monkeypatch) -> None:
    payload = {
        "student_key": "kean-student",
        "terms": [
            {
                "code": "2026SU",
                "name": "Summer 2026",
                "courses": [
                    {
                        "subject": "CPS",
                        "course_number": "4500",
                        "section": "W01",
                        "title": "Official API Course",
                        "instructor": {"full_name": "Dr. Elena Park"},
                        "syllabus": {
                            "source_label": "Kean Simple Syllabus",
                            "summary": "Fetched after OAuth authorization.",
                            "sections": [{"heading": "Schedule", "body": "Official schedule content."}],
                        },
                        "materials": [],
                    }
                ],
            }
        ],
    }

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    def fake_post(url, data, timeout):
        assert url == "https://approved.example/token"
        assert data["code"] == "abc123"
        return FakeResponse({"access_token": "token-123"})

    def fake_get(url, headers, timeout):
        assert url == "https://approved.example/api/all"
        assert headers["Authorization"] == "Bearer token-123"
        return FakeResponse(payload)

    monkeypatch.setattr("app.services.simple_syllabus.httpx.post", fake_post)
    monkeypatch.setattr("app.services.simple_syllabus.httpx.get", fake_get)

    result = import_from_authorization_code(
        db,
        "abc123",
        settings=SimpleSyllabusSettings(
            authorize_url="https://approved.example/authorize",
            token_url="https://approved.example/token",
            api_urls=("https://approved.example/api/all",),
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://127.0.0.1:8000/simple-syllabus/callback",
            scope="syllabus-library my-courses",
        ),
        reset=True,
    )

    imported = search_by_course_code(db, "CPS 4500")
    assert result["courses"] == 1
    assert [course.title for course in imported] == ["Official API Course"]


def test_scraped_simple_syllabus_payload_is_normalized() -> None:
    responses = [
        {
            "url": "https://kean.simplesyllabus.com/api/doc-library-search?my_courses=true",
            "payload": {
                "results": [
                    {
                        "courseCode": "CPS 3320",
                        "section": "W01",
                        "courseTitle": "CPS 3320 - Python Software Development",
                        "term": "Spring 2026",
                        "instructor": {"name": "Dr. Linnea Vos"},
                        "description": "Official syllabus record captured from an authenticated browser session.",
                    }
                ]
            },
        }
    ]

    payload = normalize_scraped_responses(responses)

    assert payload["student_key"] == "demo-student"
    assert payload["terms"][0]["courses"][0]["subject"] == "CPS"
    assert payload["terms"][0]["courses"][0]["course_number"] == "3320"
    assert payload["terms"][0]["courses"][0]["title"] == "Python Software Development"
    assert payload["terms"][0]["courses"][0]["instructor"]["full_name"] == "Dr. Linnea Vos"
    assert payload["terms"][0]["courses"][0]["enrolled"] is True


def test_all_courses_library_records_are_not_enrolled(db: Session) -> None:
    responses = [
        {
            "url": "https://kean.simplesyllabus.com/api2/doc-library-search",
            "payload": {
                "items": [
                    {
                        "title": "ESL 0303-W05 · ACADEMIC ORAL DISCOURSE I",
                        "subtitle": "ACADEMIC ORAL DISCOURSE I",
                        "term_name": "23/FAWZ",
                        "editors": [{"full_name": "Craig Blacklock"}],
                        "description": "This list-page syllabus text should not make the course an enrolled course.",
                    }
                ]
            },
        }
    ]

    payload = normalize_scraped_responses(responses)
    course_payload = payload["terms"][0]["courses"][0]

    assert course_payload["subject"] == "ESL"
    assert course_payload["course_number"] == "0303"
    assert course_payload["section"] == "W05"
    assert course_payload["enrolled"] is False

    load_syllabus_payload(db, payload, reset=True)

    assert db.scalar(select(func.count()).select_from(Course)) == 1
    assert db.scalar(select(func.count()).select_from(Enrollment)) == 0
    assert search_courses(db, student_key="demo-student") == []
    assert search_by_course_code(db, "ESL 0303")[0].title == "ACADEMIC ORAL DISCOURSE I"


def test_all_courses_library_fetches_one_search_page() -> None:
    clear_library_search_meta()

    class FakePage:
        def evaluate(self, _script, argument):
            assert isinstance(argument, str)
            return {
                "items": [{"title": "CPS 1000-W01", "term_name": "2026SP"}],
                "total": 125,
                "page": 1,
                "page_size": 50,
            }

    responses: list[dict] = []
    seen: set[str] = set()

    fetch_library_search_page(FakePage(), responses, seen, page_number=1, page_size=50)

    assert len(responses) == 1
    assert "page=1" in responses[0]["url"]
    assert "page_size=50" in responses[0]["url"]
    assert read_library_search_meta()["total"] == 125
    clear_library_search_meta()


def test_library_search_meta_is_scoped_to_filters() -> None:
    clear_library_search_meta()

    class FakePage:
        def evaluate(self, _script, argument):
            assert "subject_name=CPS" in argument
            assert "course_number=3320" in argument
            assert "editor=Lin" in argument
            return {
                "items": [{"title": "CPS 3320-W01", "term_name": "2026SP"}],
                "pagination": {"total": 7, "page": 0, "page_size": 50},
            }

    filters = build_library_search_filters(course_code="CPS 3320", instructor="Lin")
    responses: list[dict] = []

    fetch_library_search_page(FakePage(), responses, set(), page_number=0, page_size=50, filters=filters)

    assert filters == {"subject_name": "CPS", "course_number": "3320", "editor": "Lin"}
    assert read_library_search_meta(filters)["total"] == 7
    assert read_library_search_meta() == {}
    clear_library_search_meta()


def test_library_filter_facets_are_cached_from_kean_responses() -> None:
    clear_library_search_meta()

    write_library_facets_from_responses(
        [
            {
                "url": "https://kean.simplesyllabus.com/api2/app-state?locale=en-US",
                "payload": {
                    "items": [
                        {
                            "state": {
                                "terms": [
                                    {"name": "2026SP", "is_active": True},
                                    {"name": "2026FA", "is_active": True},
                                    {"name": "2025FA", "is_active": False},
                                ]
                            }
                        }
                    ]
                },
            },
            {
                "url": "https://kean.simplesyllabus.com/api2/subject?is_active=true",
                "payload": {
                    "items": [
                        {"name": "CPS", "is_active": True},
                        {"name": "COMM", "is_active": True},
                        {"name": "OLD", "is_active": False},
                    ]
                },
            },
        ]
    )

    facets = read_library_filter_facets()

    assert [term["code"] for term in facets["terms"]] == ["2026FA", "2026SP"]
    assert facets["subjects"] == ["COMM", "CPS"]
    clear_library_search_meta()


def test_simple_syllabus_session_is_saved_to_env(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    session_file = tmp_path / ".simple_syllabus_session.json"
    monkeypatch.setattr("app.services.simple_syllabus_scraper.env_path", lambda: env_file)
    monkeypatch.setattr("app.services.simple_syllabus_scraper.simple_syllabus_session_path", lambda: session_file)

    class FakePage:
        def evaluate(self, _script):
            return "jwt-token"

    class FakeContext:
        pages = [FakePage()]

        def cookies(self, _urls):
            return [{"name": "sid", "value": "abc"}, {"name": "other", "value": "def"}]

    save_simple_syllabus_session_from_context(FakeContext())

    values = read_env_values()
    assert values["SIMPLE_SYLLABUS_COOKIE"] == "sid=abc; other=def"
    assert values["SIMPLE_SYLLABUS_BEARER_TOKEN"] == "jwt-token"
    assert read_simple_syllabus_session()["cookie"] == "sid=abc; other=def"


def test_saved_session_http_fetch_uses_env_credentials(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'SIMPLE_SYLLABUS_COOKIE="sid=abc"\nSIMPLE_SYLLABUS_BEARER_TOKEN="jwt-token"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.simple_syllabus_scraper.env_path", lambda: env_file)

    captured_headers = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [], "pagination": {"total": 0, "page_size": 50}}

    class FakeClient:
        def __init__(self, *, headers, follow_redirects, timeout):
            captured_headers.update(headers)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _url):
            return FakeResponse()

    monkeypatch.setattr("app.services.simple_syllabus_scraper.httpx.Client", FakeClient)

    payload = fetch_simple_syllabus_json_with_session("https://kean.simplesyllabus.com/api2/doc-library-search")

    assert payload["pagination"]["page_size"] == 50
    assert captured_headers["Cookie"] == "sid=abc"
    assert captured_headers["Authorization"] == "Bearer jwt-token"


def test_historic_my_courses_search_url_adds_all_term_statuses() -> None:
    url = build_historic_my_courses_search_url(
        [
            {
                "url": "https://kean.simplesyllabus.com/api2/doc-library-search?my_courses_account_id=abc&term_statuses%5B%5D=future&term_statuses%5B%5D=current",
                "payload": {"items": []},
            }
        ]
    )

    assert url is not None
    assert "my_courses_account_id=abc" in url
    assert "term_statuses%5B%5D=future" in url
    assert "term_statuses%5B%5D=current" in url
    assert "term_statuses%5B%5D=historic" in url


def test_har_list_and_doc_detail_records_are_merged() -> None:
    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://kean.simplesyllabus.com/en-US/api/doc-library-search?my_courses=true"
                    },
                    "response": {
                        "content": {
                            "mimeType": "application/json",
                            "text": __import__("json").dumps(
                                {
                                    "results": [
                                        {
                                            "docCode": "abc123",
                                            "courseCode": "CPS 3320",
                                            "section": "W01",
                                            "courseTitle": "CPS 3320 - Python Software Development",
                                            "term": "Spring 2026",
                                        }
                                    ]
                                }
                            ),
                        }
                    },
                },
                {
                    "request": {
                        "url": "https://kean.simplesyllabus.com/en-US/api/doc?code=abc123"
                    },
                    "response": {
                        "content": {
                            "mimeType": "application/json",
                            "text": __import__("json").dumps(
                                {
                                    "instructor": {"name": "Dr. Linnea Vos"},
                                    "courseDescription": "A detailed official description from the syllabus detail response.",
                                    "sections": [
                                        {
                                            "heading": "Grading Policy",
                                            "body": "Projects, exams, and participation are listed in the official syllabus detail."
                                        }
                                    ],
                                    "materials": [
                                        {
                                            "title": "Python Crash Course",
                                            "isbn_13": "9781718502703",
                                            "authors": "Eric Matthes",
                                        }
                                    ],
                                }
                            ),
                        }
                    },
                },
            ]
        }
    }

    responses = extract_json_responses_from_har(__import__("json").dumps(har).encode())
    payload = normalize_scraped_responses(responses)
    course = payload["terms"][0]["courses"][0]

    assert course["instructor"]["full_name"] == "Dr. Linnea Vos"
    assert "detailed official description" in course["syllabus"]["summary"]
    assert course["syllabus"]["sections"][0]["heading"] == "Grading Policy"
    assert course["materials"][0]["isbn_13"] == "9781718502703"


def test_heading_component_details_are_merged_without_fake_materials() -> None:
    responses = [
        {
            "url": "https://kean.simplesyllabus.com/api2/doc-library-search?my_courses_account_id=student",
            "payload": {
                "items": [
                    {
                        "code": "x8drl0yoq",
                        "title": "COMM 3590 W11",
                        "subtitle": "Business & Prof. Comm",
                        "term_name": "2026SPW",
                        "entity_id": "8cf71542-727e-413a-b96e-0f8c4e785a27",
                        "editors": [{"full_name": "YingShin Chin"}],
                    }
                ]
            },
        },
        {
            "url": "https://kean.simplesyllabus.com/api2/doc?code=x8drl0yoq",
            "payload": {
                "items": [
                    {
                        "code": "x8drl0yoq",
                        "title": "COMM 3590 W11",
                        "sub_title": "Business & Prof. Comm",
                        "term": {"name": "2026SPW"},
                        "entity_id": "8cf71542-727e-413a-b96e-0f8c4e785a27",
                        "entity_type": "section",
                        "properties": {"subject_name": "COMM", "course_number": "3590"},
                    }
                ]
            },
        },
        {
            "url": (
                "https://kean.simplesyllabus.com/api2/heading-component?"
                "term_id=term&family_name=syllabus&entity_id=8cf71542-727e-413a-b96e-0f8c4e785a27"
            ),
            "payload": {
                "items": [
                    component_table(
                        "Instructor Information",
                        ["Instructor Name", "Office Location", "Office Hours", "Email"],
                        [["Yingshin Chin", "GEH C415", "Monday 2:30PM - 3:30PM", "ychin@kean.edu"]],
                    ),
                    component_table(
                        "Required Texts and Materials",
                        ["Title", "Subtitle", "ISBN", "Authors", "Publisher", "Edition"],
                        [[
                            "Business and Professional Communication",
                            "Plans, Processes, and Performance",
                            "9780134238425",
                            "James DiSanza, Nancy Legge",
                            "Pearson",
                            "4th",
                        ]],
                    ),
                    component_text(
                        "Course Policies",
                        "Attendance, participation, and professional communication expectations are listed here.",
                    ),
                    component_text(
                        "instructor",
                        "System instructor role that includes the following built-in functionality: edit syllabi.",
                    ),
                ]
            },
        },
    ]

    payload = normalize_scraped_responses(responses)
    course = payload["terms"][0]["courses"][0]

    assert payload["terms"][0]["code"] == "2026SPW"
    assert course["subject"] == "COMM"
    assert course["course_number"] == "3590"
    assert course["section"] == "W11"
    assert course["title"] == "Business & Prof. Comm"
    assert course["instructor"]["full_name"] == "Yingshin Chin"
    assert course["instructor"]["email"] == "ychin@kean.edu"
    assert "GEH C415" in course["instructor"]["office"]
    assert course["materials"] == [
        {
            "title": "Business and Professional Communication",
            "authors": "James DiSanza, Nancy Legge",
            "material_type": "textbook",
            "isbn_13": "9780134238425",
            "isbn_10": None,
            "edition": "4th",
            "publisher": "Pearson",
            "requirement_status": "required",
            "student_status": "needed",
            "legal_search_url": "https://www.worldcat.org/search?q=9780134238425",
        }
    ]
    assert "instructor" not in [material["title"] for material in course["materials"]]
    assert "Course Policies" not in [section["heading"] for section in course["syllabus"]["sections"]]
    assert "Required Texts and Materials" in [section["heading"] for section in course["syllabus"]["sections"]]


def test_dom_schedule_tables_are_not_imported_as_materials() -> None:
    responses = [
        {
            "url": "https://kean.simplesyllabus.com/api2/doc-library-search?my_courses_account_id=student",
            "payload": {
                "items": [
                    {
                        "code": "x8drl0yoq",
                        "title": "COMM 3590 W11",
                        "subtitle": "Business & Prof. Comm",
                        "term_name": "2026SPW",
                        "entity_id": "8cf71542-727e-413a-b96e-0f8c4e785a27",
                        "editors": [{"full_name": "YingShin Chin"}],
                    }
                ]
            },
        },
        {
            "url": "https://kean.simplesyllabus.com/en-US/doc/x8drl0yoq/2026SPW-COMM-3590-W11?mode=view",
            "payload": {
                "_dom_detail": {
                    "docCode": "x8drl0yoq",
                    "tableRows": [
                        ["Week", "Topic", "Assignment"],
                        ["Feb 28", "Introduction", "Resume"],
                        ["Mar 2", "Interview", "Elevator Pitch"],
                    ],
                }
            },
        },
    ]

    payload = normalize_scraped_responses(responses)
    course = payload["terms"][0]["courses"][0]

    assert course["materials"] == []


def component_table(name: str, columns: list[str], rows: list[list[str]]) -> dict:
    column_entries = [
        {
            "heading": {"id": f"column-{index}"},
            "variation": {"combined": {"name": column, "is_deleted": False, "is_visible": True}},
        }
        for index, column in enumerate(columns)
    ]
    row_entries = []
    for row in rows:
        row_entries.append(
            {
                "cells": [
                    {
                        "column_id": f"column-{index}",
                        "variation": {"combined": {"value": value, "is_deleted": False, "is_visible": True}},
                    }
                    for index, value in enumerate(row)
                ]
            }
        )
    return {
        "variations": [{"combined": {"name": name, "is_deleted": False, "is_visible": True}}],
        "columns": column_entries,
        "rows": row_entries,
    }


def component_text(name: str, body: str) -> dict:
    return {
        "variations": [
            {
                "combined": {
                    "name": name,
                    "value": body,
                    "is_deleted": False,
                    "is_visible": True,
                }
            }
        ],
        "columns": [],
        "rows": [],
    }
