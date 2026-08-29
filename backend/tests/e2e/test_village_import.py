"""Master-data import, end to end over HTTP.

This is the path the real Ghorband village lists will arrive through, so it is
tested against the behaviour section 7 demands rather than against the happy
path: nothing merges automatically, similar names are proposed and not decided,
and two villages sharing a name in different places stay two records.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

pytestmark = pytest.mark.integration

ADMIN = "+93700000001"


def preview(client: TestClient, headers: dict, content: bytes, filename: str):
    response = client.post(
        "/api/v1/admin/imports/villages/preview",
        headers=headers,
        files={"file": (filename, content, "application/octet-stream")},
    )
    return response


def csv_bytes(*rows: str) -> bytes:
    header = "district_code,name,alternative_names,latitude,longitude"
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


@pytest.fixture(scope="session")
def staff(admin_session: dict) -> dict:
    return admin_session


class TestPreview:
    def test_a_clean_csv_previews_without_writing_anything(
        self, client: TestClient, staff: dict
    ) -> None:
        before = client.get("/api/v1/admin/villages?limit=200", headers=staff).json()["meta"]

        response = preview(client, staff, csv_bytes("GRB-SYG,آبپران,,35.13,68.75"), "v.csv")
        assert response.status_code == 200, response.text
        body = response.json()["data"]

        assert body["will_create_count"] == 1
        assert body["blocking_count"] == 0
        assert body["duplicate_count"] == 0

        after = client.get("/api/v1/admin/villages?limit=200", headers=staff).json()["meta"]
        assert after["total"] == before["total"], "preview must not write a village"

    def test_a_missing_name_blocks_its_row_but_a_bad_coordinate_does_not(
        self, client: TestClient, staff: dict
    ) -> None:
        """The two kinds of problem need different reactions.

        A row with no name cannot be imported. A row with a malformed
        coordinate is imported without one, because coordinates are optional
        everywhere in this product -- reporting both as "errors" would make an
        operator think they had lost rows they had not.
        """
        response = preview(
            client, staff,
            csv_bytes(
                "GRB-SYG,,,35.1,68.7",              # no name -- blocks
                "GRB-SYG,چکاب,,not-a-number,68.7",  # bad latitude -- warning
            ),
            "v.csv",
        )
        body = response.json()["data"]

        blocking = [p for p in body["problems"] if p["blocking"]]
        warnings = [p for p in body["problems"] if not p["blocking"]]

        assert [p["column"] for p in blocking] == ["name"]
        assert [p["column"] for p in warnings] == ["latitude"]
        assert body["blocking_count"] == 1
        # The village with the bad coordinate is still imported.
        assert [v["name"] for v in body["will_create"]] == ["چکاب"]

    def test_an_unknown_district_is_reported_by_code(
        self, client: TestClient, staff: dict
    ) -> None:
        body = preview(
            client, staff, csv_bytes("GRB-NOPE,جایی,,,"), "v.csv"
        ).json()["data"]
        problem = next(p for p in body["problems"] if p["column"] == "district_code")
        assert problem["reason"] == "unknown_district"
        assert problem["value"] == "GRB-NOPE"
        assert problem["blocking"] is True

    def test_a_name_already_in_the_district_is_proposed_not_merged(
        self, client: TestClient, staff: dict
    ) -> None:
        """Section 7. The importer proposes; a person decides."""
        body = preview(
            client, staff, csv_bytes("GRB-SYG,خیشکی,,35.125,68.77"), "v.csv"
        ).json()["data"]

        assert body["duplicate_count"] == 1
        assert body["will_create_count"] == 0, "a flagged row is not created by default"
        duplicate = body["duplicates"][0]
        assert duplicate["existing_name"] == "خیشکی"
        assert duplicate["reason"] == "exists_in_same_district"
        assert duplicate["score"] == 1.0

    def test_keyboard_variants_of_one_name_are_proposed(
        self, client: TestClient, staff: dict
    ) -> None:
        """An Arabic yeh against a Persian one is the same village typed twice."""
        body = preview(
            client, staff, csv_bytes("GRB-SYG,خيشكي,,35.125,68.77"), "v.csv"
        ).json()["data"]
        assert body["duplicate_count"] == 1

    def test_a_repeat_inside_the_file_is_caught(
        self, client: TestClient, staff: dict
    ) -> None:
        body = preview(
            client, staff,
            csv_bytes("GRB-SHA,تکرار,,34.9,68.45", "GRB-SHA,تکرار,,34.91,68.46"),
            "v.csv",
        ).json()["data"]

        duplicate = next(
            d for d in body["duplicates"] if d["reason"].startswith("repeated_in_file")
        )
        assert duplicate["row_number"] == 3     # the second occurrence, not the first
        assert body["will_create_count"] == 1   # the first one still imports

    def test_an_excel_file_with_a_title_row_is_read(
        self, client: TestClient, staff: dict
    ) -> None:
        """District offices send spreadsheets with a merged title above the header.

        Taking the first non-empty row as the header rejects the whole file.
        """
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["فهرست قریه‌های ولسوالی"])
        sheet.append([])
        sheet.append(["district_code", "name", "alternative_names", "latitude", "longitude"])
        sheet.append(["GRB-SHA", "اکسل‌آباد", "دومی", 34.9, 68.45])
        sheet.append([])
        buffer = io.BytesIO()
        workbook.save(buffer)

        body = preview(client, staff, buffer.getvalue(), "villages.xlsx").json()["data"]
        assert body["will_create_count"] == 1
        assert body["will_create"][0]["name"] == "اکسل‌آباد"
        assert body["will_create"][0]["aliases"] == ["دومی"]

    def test_a_file_with_no_usable_header_names_what_it_found(
        self, client: TestClient, staff: dict
    ) -> None:
        workbook = Workbook()
        workbook.active.append(["قریه", "ولسوالی"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        response = preview(client, staff, buffer.getvalue(), "wrong.xlsx")
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "IMPORT_COLUMN_MISSING"
        # Naming what was actually there is what lets an operator fix the file.
        assert error["context"]["found"]

    def test_an_unsupported_format_is_refused(
        self, client: TestClient, staff: dict
    ) -> None:
        response = preview(client, staff, b"whatever", "villages.pdf")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "IMPORT_FILE_UNREADABLE"


class TestCommit:
    def _preview_job(self, client: TestClient, staff: dict, *rows: str) -> dict:
        return preview(client, staff, csv_bytes(*rows), "v.csv").json()["data"]

    def test_committing_creates_villages_aliases_and_stations(
        self, client: TestClient, staff: dict
    ) -> None:
        job = self._preview_job(
            client, staff, "GRB-SHA,نوآباد,کهنه‌آباد,34.90,68.45"
        )
        response = client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff,
            json={"accept_rows": [], "create_stations": True},
        )
        assert response.status_code == 200, response.text
        result = response.json()["data"]

        assert result["villages_created"] == 1
        assert result["aliases_created"] == 1
        assert result["stations_created"] == 1

        found = client.get(
            "/api/v1/admin/villages?q=نوآباد", headers=staff
        ).json()["data"]
        assert any(v["name"] == "نوآباد" for v in found)

    def test_an_accepted_duplicate_is_actually_created(
        self, client: TestClient, staff: dict
    ) -> None:
        """Two villages of one name in different valleys stay two records.

        This is the path that previously did nothing: the preview stored only
        the rows it intended to create, so a duplicate the operator confirmed
        had no payload to create it from and was silently dropped.
        """
        job = self._preview_job(client, staff, "GRB-SYG,خیشکی,,35.2,68.9")
        assert job["duplicate_count"] == 1
        row = job["duplicates"][0]["row_number"]

        before = client.get("/api/v1/admin/villages?q=خیشکی", headers=staff).json()["data"]

        result = client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff,
            json={"accept_rows": [row], "create_stations": False},
        ).json()["data"]

        assert result["villages_created"] == 1, "an accepted duplicate must be created"
        assert result["stations_created"] == 0

        after = client.get("/api/v1/admin/villages?q=خیشکی", headers=staff).json()["data"]
        assert len(after) == len(before) + 1

    def test_an_unconfirmed_duplicate_is_skipped(
        self, client: TestClient, staff: dict
    ) -> None:
        job = self._preview_job(client, staff, "GRB-SYG,خیشکی,,35.3,68.9")
        result = client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff,
            json={"accept_rows": [], "create_stations": True},
        ).json()["data"]

        assert result["villages_created"] == 0
        assert result["skipped_duplicates"] == 1

    def test_committing_twice_is_refused(
        self, client: TestClient, staff: dict
    ) -> None:
        """An operator clicking twice on a slow connection must not import twice."""
        job = self._preview_job(client, staff, "GRB-SHA,یکبار,,34.9,68.45")
        first = client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff, json={"accept_rows": []},
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff, json={"accept_rows": []},
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "IMPORT_ALREADY_COMMITTED"

    def test_codes_continue_the_district_sequence(
        self, client: TestClient, staff: dict
    ) -> None:
        """Numbering carries on rather than restarting, so a second import does
        not collide with the first."""
        existing = client.get(
            "/api/v1/admin/villages?district_id=", headers=staff
        ).json()["data"]
        siahgird = next(
            d for d in client.get("/api/v1/admin/districts", headers=staff).json()["data"]
            if d["code"] == "GRB-SYG"
        )
        highest = max(
            int(v["code"].rsplit("-", 1)[-1])
            for v in existing
            if v["district_id"] == siahgird["id"] and v["code"].rsplit("-", 1)[-1].isdigit()
        )

        job = self._preview_job(client, staff, "GRB-SYG,شماره‌بعدی,,35.15,68.76")
        client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff, json={"accept_rows": []},
        )

        created = client.get(
            "/api/v1/admin/villages?q=شماره‌بعدی", headers=staff
        ).json()["data"][0]
        assert int(created["code"].rsplit("-", 1)[-1]) == highest + 1

    def test_the_run_is_audited(self, client: TestClient, staff: dict) -> None:
        job = self._preview_job(client, staff, "GRB-SHA,ثبت‌شده,,34.9,68.45")
        client.post(
            f"/api/v1/admin/imports/villages/{job['job_id']}/commit",
            headers=staff, json={"accept_rows": []},
        )
        entries = client.get(
            "/api/v1/admin/audit?action=import.committed", headers=staff
        ).json()["data"]
        assert entries, "a master-data import must be audited"
        assert entries[0]["after"]["villages"] >= 1


class TestPermissions:
    def test_a_passenger_cannot_import(
        self, client: TestClient, passenger_session: dict
    ) -> None:
        response = preview(
            client, passenger_session, csv_bytes("GRB-SYG,تلاش,,35.1,68.7"), "v.csv"
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
