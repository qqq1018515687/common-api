#!/usr/bin/env python3
"""Validate update announcement manager behavior with an in-memory database."""
import os
import sys
import time
import types
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


class TestBase(DeclarativeBase):
    pass


database_module = types.ModuleType("coze_coding_dev_sdk.database")
database_module.Base = TestBase
sdk_module = types.ModuleType("coze_coding_dev_sdk")
sdk_module.database = database_module
sys.modules.setdefault("coze_coding_dev_sdk", sdk_module)
sys.modules.setdefault("coze_coding_dev_sdk.database", database_module)

from storage.database.announcement_manager import AnnouncementCreate, AnnouncementManager, AnnouncementUpdate
from storage.database.shared.model import UpdateAnnouncements


class AnnouncementManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        UpdateAnnouncements.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.now = int(time.time() * 1000)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def create_announcement(self, **overrides) -> dict:
        payload = {
            "title": "Update notice",
            "summary": "A focused release note",
            "items": [{"title": "New model", "description": "Better quality"}],
            "target_audience": "all",
            "priority": "medium",
            "is_active": True,
            "start_time": self.now - 1000,
            "end_time": None,
            "version": "2026.05.27",
            "created_by": "admin_001",
        }
        payload.update(overrides)

        success, announcement, error = AnnouncementManager.create_announcement(
            self.db,
            AnnouncementCreate(**payload),
        )
        self.assertTrue(success, error)
        self.assertIsNone(error)
        return announcement

    def test_get_active_popup_empty(self) -> None:
        success, announcement, error = AnnouncementManager.get_active_popup(
            self.db,
            current_time=self.now,
            target_audience="all",
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIsNone(announcement)

    def test_get_active_popup_returns_created_announcement(self) -> None:
        created = self.create_announcement()

        success, announcement, error = AnnouncementManager.get_active_popup(
            self.db,
            current_time=self.now,
            target_audience="guest",
        )

        self.assertTrue(success, error)
        self.assertEqual(created["id"], announcement["id"])
        self.assertEqual("Update notice", announcement["title"])

    def test_target_audience_matching(self) -> None:
        all_notice = self.create_announcement(target_audience="all", priority="low")

        for audience in ["guest", "logged_in", "admin", "all"]:
            with self.subTest(audience=audience):
                success, announcement, error = AnnouncementManager.get_active_popup(
                    self.db,
                    current_time=self.now,
                    target_audience=audience,
                )
                self.assertTrue(success, error)
                self.assertEqual(all_notice["id"], announcement["id"])

        success, error = AnnouncementManager.disable_announcement(self.db, all_notice["id"])
        self.assertTrue(success, error)

        for audience in ["guest", "logged_in", "admin"]:
            specific = self.create_announcement(
                title=f"{audience} notice",
                target_audience=audience,
            )

            success, matched, error = AnnouncementManager.get_active_popup(
                self.db,
                current_time=self.now,
                target_audience=audience,
            )
            self.assertTrue(success, error)
            self.assertEqual(specific["id"], matched["id"])

            other_audience = "admin" if audience != "admin" else "guest"
            success, unmatched, error = AnnouncementManager.get_active_popup(
                self.db,
                current_time=self.now,
                target_audience=other_audience,
            )
            self.assertTrue(success, error)
            self.assertIsNone(unmatched)

            success, error = AnnouncementManager.disable_announcement(self.db, specific["id"])
            self.assertTrue(success, error)

    def test_expired_or_inactive_popup_is_not_returned(self) -> None:
        self.create_announcement(
            title="Expired notice",
            start_time=self.now - 5000,
            end_time=self.now - 1000,
        )
        self.create_announcement(
            title="Inactive notice",
            is_active=False,
        )

        success, announcement, error = AnnouncementManager.get_active_popup(
            self.db,
            current_time=self.now,
            target_audience="all",
        )

        self.assertTrue(success, error)
        self.assertIsNone(announcement)

    def test_disable_hides_popup(self) -> None:
        created = self.create_announcement()

        success, error = AnnouncementManager.disable_announcement(self.db, created["id"])
        self.assertTrue(success, error)

        success, announcement, error = AnnouncementManager.get_active_popup(
            self.db,
            current_time=self.now,
            target_audience="all",
        )

        self.assertTrue(success, error)
        self.assertIsNone(announcement)

    def test_update_changes_active_popup_payload(self) -> None:
        created = self.create_announcement()

        success, updated, error = AnnouncementManager.update_announcement(
            self.db,
            created["id"],
            AnnouncementUpdate(summary="Updated summary", priority="high"),
        )

        self.assertTrue(success, error)
        self.assertEqual("Updated summary", updated["summary"])
        self.assertEqual("high", updated["priority"])


if __name__ == "__main__":
    unittest.main()
