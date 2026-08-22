import unittest

from pydantic import ValidationError

from app.schemas.projects import ProjectCreate, ProjectUpdate


class ProjectSchemaTest(unittest.TestCase):
    def test_create_normalizes_title_and_defaults(self) -> None:
        project = ProjectCreate(title="  The Last Signal  ")
        self.assertEqual(
            (project.title, project.description, project.language),
            ("The Last Signal", "", "en"),
        )

    def test_rejects_blank_title_and_empty_or_null_update(self) -> None:
        for payload in ({"title": "  "},):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ProjectCreate(**payload)

        for payload in ({}, {"title": None}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ProjectUpdate(**payload)


if __name__ == "__main__":
    unittest.main()
