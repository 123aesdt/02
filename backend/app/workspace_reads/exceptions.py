class TeamMemberNotFound(ValueError):
    def __init__(self, subject_id: str) -> None:
        super().__init__("team member is not an active delivery employee")
        self.subject_id = subject_id
