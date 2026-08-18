"""Safe parsing and validation for delegated guest roster uploads."""

import csv
import io

from app.accommodation.services.registration_service import RegistrationService


class BulkRegistrationService:
    """Parse supported tabular uploads and persist through the canonical service."""

    REQUIRED_COLUMNS = {"name", "email", "phone", "id_document_type", "id_document_number"}

    @classmethod
    def parse(cls, file_storage):
        filename = (file_storage.filename or "").lower()
        if filename.endswith(".csv"):
            text = file_storage.stream.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            columns = {str(c or "").strip().lower() for c in (reader.fieldnames or [])}
            missing = cls.REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
            return [{str(k).strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
        if filename.endswith(".xlsx"):
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise ValueError("XLSX uploads require the openpyxl dependency") from exc
            workbook = load_workbook(file_storage.stream, read_only=True, data_only=True)
            sheet = workbook.active
            values = list(sheet.values)
            if not values:
                raise ValueError("The upload is empty")
            headers = [str(value or "").strip().lower() for value in values[0]]
            missing = cls.REQUIRED_COLUMNS - set(headers)
            if missing:
                raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
            return [dict(zip(headers, (str(v or "").strip() for v in row))) for row in values[1:]]
        raise ValueError("Upload must be a CSV or XLSX file")

    @classmethod
    def import_file(cls, booking, file_storage):
        rows = cls.parse(file_storage)
        if len(rows) > max(0, int(booking.num_guests or 1) - RegistrationService.active_count(booking.id)):
            raise ValueError("Upload exceeds the remaining registration capacity")
        return RegistrationService.bulk_create(booking, rows)