from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import OptimisticLockConflict
from app.models.dispatch import Dispatch


class DispatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit_dispatch(self, dispatch: Dispatch) -> Dispatch:
        try:
            self._session.commit()
        except StaleDataError as error:
            self._session.rollback()
            raise OptimisticLockConflict(dispatch.id) from error
        return dispatch

    def get_by_task_id(self, task_id: int) -> Dispatch | None:
        return self._session.scalar(select(Dispatch).where(Dispatch.task_id == task_id))
