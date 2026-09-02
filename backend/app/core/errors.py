class OptimisticLockConflict(Exception):
    def __init__(self, dispatch_id: int) -> None:
        self.dispatch_id = dispatch_id
        super().__init__("Dispatch was modified by another operation.")
