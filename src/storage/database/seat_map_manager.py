"""
Seat map database manager for CRUD operations and version control.
"""
from typing import Optional, Tuple
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime
import json


class SeatMapManager:
    """Seat map database operations manager"""

    def get_latest_seat_map(self, db: Session) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Get the latest seat map data

        Returns:
            (success, data, error_message)
        """
        try:
            query = text("""
                SELECT id, version, departments, rows, seats,
                       updated_at, updated_by_label, created_at
                FROM seat_maps
                ORDER BY version DESC
                LIMIT 1
            """)

            result = db.execute(query)
            row = result.fetchone()

            if not row:
                return False, None, "Seat map data not found"

            data = {
                'id': row.id,
                'version': row.version,
                'departments': row.departments,
                'rows': row.rows,
                'seats': row.seats,
                'updatedAt': row.updated_at.isoformat() if row.updated_at else None,
                'updatedByLabel': row.updated_by_label,
                'createdAt': row.created_at.isoformat() if row.created_at else None
            }

            return True, data, None

        except Exception as e:
            return False, None, f"Database query failed: {str(e)}"

    def update_seat_map(
        self,
        db: Session,
        data: dict,
        expected_version: Optional[int] = None,
        updated_by_label: str = "Anonymous editor"
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Update seat map data with version control

        Args:
            db: Database session
            data: Seat map data
            expected_version: Expected version number (for optimistic locking)
            updated_by_label: Updater label

        Returns:
            (success, updated_data, error_message)
        """
        try:
            # 1. Validate data structure
            required_fields = ['departments', 'rows', 'seats']
            for field in required_fields:
                if field not in data:
                    return False, None, f"Missing required field: {field}"

            # 2. Get current version
            current_query = text("""
                SELECT version FROM seat_maps
                ORDER BY version DESC
                LIMIT 1
            """)
            current_result = db.execute(current_query)
            current_row = current_result.fetchone()

            if not current_row:
                return False, None, "Seat map data not found"

            current_version = current_row.version

            # 3. Version conflict detection (optimistic lock)
            if expected_version is not None and expected_version != current_version:
                # Return latest data for client refresh
                latest_data = self.get_latest_seat_map(db)
                return False, latest_data[1], "Seat map has been updated by others, please refresh and save again."

            # 4. Insert new version data
            new_version = current_version + 1
            updated_by_label = updated_by_label[:40] if updated_by_label else "Anonymous editor"

            insert_query = text("""
                INSERT INTO seat_maps (
                    version, departments, rows, seats, updated_at, updated_by_label, created_at
                )
                VALUES (
                    :version,
                    :departments::jsonb,
                    :rows::jsonb,
                    :seats::jsonb,
                    NOW(),
                    :updated_by_label,
                    NOW()
                )
                RETURNING id, version, updated_at
            """)

            result = db.execute(
                insert_query,
                {
                    'version': new_version,
                    'departments': json.dumps(data['departments']),
                    'rows': json.dumps(data['rows']),
                    'seats': json.dumps(data['seats']),
                    'updated_by_label': updated_by_label
                }
            )

            db.commit()

            new_row = result.fetchone()

            updated_data = {
                'id': new_row.id,
                'version': new_row.version,
                'departments': data['departments'],
                'rows': data['rows'],
                'seats': data['seats'],
                'updatedAt': new_row.updated_at.isoformat(),
                'updatedByLabel': updated_by_label
            }

            return True, updated_data, None

        except IntegrityError as e:
            db.rollback()
            return False, None, "Version conflict, please retry"

        except Exception as e:
            db.rollback()
            return False, None, f"Save failed: {str(e)}"

    def validate_schema(self, db: Session) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Validate database schema correctness

        Returns:
            (success, schema_info, error_message)
        """
        try:
            query = text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'seat_maps'
                ORDER BY ordinal_position
            """)

            result = db.execute(query)
            columns = result.fetchall()

            expected_columns = {
                'id', 'version', 'departments', 'rows', 'seats',
                'updated_at', 'updated_by_label', 'created_at'
            }

            actual_columns = {row.column_name for row in columns}

            if not expected_columns.issubset(actual_columns):
                missing = expected_columns - actual_columns
                return False, None, f"Missing columns: {missing}"

            schema_info = {
                'table_name': 'seat_maps',
                'columns': [
                    {
                        'name': row.column_name,
                        'type': row.data_type,
                        'nullable': row.is_nullable
                    }
                    for row in columns
                ],
                'total_columns': len(columns)
            }

            return True, schema_info, None

        except Exception as e:
            return False, None, f"Schema validation failed: {str(e)}"