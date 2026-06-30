"""
Seat map management node for handling API requests.
"""
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig

from storage.database.db import get_session
from storage.database.seat_map_manager import SeatMapManager


class SeatMapInput(BaseModel):
    """Seat map input data"""
    operation_type: str = Field(..., description="Operation type")
    data: Optional[dict] = Field(None, description="Seat map data")
    expected_version: Optional[int] = Field(None, description="Expected version number")
    updated_by_label: Optional[str] = Field(None, description="Updater label")


class SeatMapOutput(BaseModel):
    """Seat map output data"""
    success: bool = Field(..., description="Operation success status")
    data: Optional[dict] = Field(None, description="Return data")
    error: Optional[str] = Field(None, description="Error message")
    code: Optional[str] = Field(None, description="Error code")


def seat_map_node(state: dict, config: RunnableConfig, runtime) -> dict:
    """
    Seat map management node handler

    Supported operation types:
    - get_seat_map: Get seat map data
    - update_seat_map: Update seat map data
    - validate_schema: Validate database schema
    """
    input_data = state.get('input_data', {})

    operation_type = input_data.get('operation_type', '')
    data = input_data.get('data')
    expected_version = input_data.get('expected_version')
    updated_by_label = input_data.get('updated_by_label', 'Anonymous editor')

    manager = SeatMapManager()
    db = get_session()

    try:
        if operation_type == 'get_seat_map':
            success, result, error = manager.get_latest_seat_map(db)

            return {
                'success': success,
                'data': result,
                'error': error,
                'code': 'SUCCESS' if success else 'NOT_FOUND'
            }

        elif operation_type == 'update_seat_map':
            if not data:
                return {
                    'success': False,
                    'data': None,
                    'error': 'Missing seat map data',
                    'code': 'INVALID_REQUEST'
                }

            success, result, error = manager.update_seat_map(
                db,
                data,
                expected_version,
                updated_by_label
            )

            return {
                'success': success,
                'data': result,
                'error': error,
                'code': 'SUCCESS' if success else (
                    'VERSION_CONFLICT' if error and 'Version conflict' in error or 'updated by others' in error else 'DATABASE_ERROR'
                )
            }

        elif operation_type == 'validate_schema':
            success, result, error = manager.validate_schema(db)

            return {
                'success': success,
                'data': result,
                'error': error,
                'code': 'SUCCESS' if success else 'SCHEMA_ERROR'
            }

        else:
            return {
                'success': False,
                'data': None,
                'error': f'Unknown operation type: {operation_type}',
                'code': 'INVALID_OPERATION'
            }

    finally:
        db.close()