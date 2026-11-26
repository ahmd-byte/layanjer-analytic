from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from layan_engine.platforms.base import ExtractionResult
from layan_engine.platforms.instagram.worker import parse_post_description
from layan_engine.storage.metrics import save_result
from layan_engine.storage.models import AccountMetric, Base, Content, ContentMetric


def _session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _result(followers: float, likes: float, day: str = "2026-11-26") -> ExtractionResult:
    return ExtractionResult(
        platform="instagram",
        account_id="default",
        success=True,
        metrics=[{"metric_name": "followers", "metric_value": followers, "date_start": day, "date_end": day,
                  "source_dashboard": "Instagram profile (public)", "extraction_method": "dom_public"}],
        content_records=[{
            "content_id": "ABC123", "content_type": "reel", "title": "First reel",
            "content_url": "https://www.instagram.com/reel/ABC123/", "published_at": "2026-11-25T17:00:57.000Z",
            "metrics": {"likes": likes, "comments": 3.0, "views": None},
            "date_start": day, "date_end": day,
        }],
    )


def test_save_counts_account_and_post_metrics():
    db = _session()
    saved = save_result(db, "instagram", "default", _result(10, 5), run_id=None)
    assert saved == 3  # followers + likes + comments; views=None is skipped
    assert db.query(Content).one().title == "First reel"


def test_same_day_repull_updates_instead_of_duplicating():
    db = _session()
    save_result(db, "instagram", "default", _result(10, 5), run_id=None)
    save_result(db, "instagram", "default", _result(12, 9), run_id=None)
    assert db.query(AccountMetric).one().metric_value == 12
    assert db.query(Content).count() == 1
    assert db.query(ContentMetric).filter_by(metric_name="likes").one().metric_value == 9


def test_rows_without_content_id_are_ignored():
    db = _session()
    r = ExtractionResult(success=True, content_records=[{"title": "raw row", "raw_values": []}])
    assert save_result(db, "instagram", "default", r, run_id=None) == 0
    assert db.query(Content).count() == 0


def test_posts_endpoint_returns_newest_reading():
    # Imported here: importing the routes at collection time binds storage.database to the
    # real settings before other tests' fixtures point it at a temp database.
    from layan_engine.api.routes.analytics import get_posts

    db = _session()
    save_result(db, "instagram", "default", _result(10, 5, day="2026-11-25"), run_id=None)
    save_result(db, "instagram", "default", _result(10, 8, day="2026-11-26"), run_id=None)
    db.commit()
    rows = get_posts(platform="instagram", account_id=None, limit=50, db=db)
    assert len(rows) == 1
    assert rows[0]["metrics"] == {"likes": 8, "comments": 3}
    assert rows[0]["as_of"] == "2026-11-26"
    assert rows[0]["published_at"].startswith("2026-11-25")


class TestParsePostDescription:
    def test_full(self):
        og = '265K likes, 5,251 comments - instagram on November 24, 2026: "Small surface, big ideas"'
        assert parse_post_description(og) == {"likes": 265000, "comments": 5251, "caption": "Small surface, big ideas"}

    def test_singular_and_hidden_likes(self):
        assert parse_post_description('1 like, 1 comment - a on May 1, 2026: "hi"')["likes"] == 1
        parsed = parse_post_description('12 comments - a on May 1, 2026: "hi"')
        assert parsed["likes"] is None and parsed["comments"] == 12

    def test_empty(self):
        assert parse_post_description("") == {"likes": None, "comments": None, "caption": None}
