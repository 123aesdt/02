import os
from uuid import uuid4

from app.acceptance.loadtest import build_dispatch_payload
from locust import HttpUser, between, task
from security_identity import development_bearer_identity


class CountyFlowHttpUser(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self) -> None:
        self.task_id = os.environ["LOCUST_TASK_ID"]
        identity = development_bearer_identity("DISPATCHER", uuid4().hex)
        self.client.headers.update(identity.headers)

    @task(50)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(30)
    def task_status(self) -> None:
        self.client.get(f"/api/v1/dispatch-tasks/{self.task_id}", name="GET /api/v1/dispatch-tasks/:task_id")

    @task(19)
    def task_result(self) -> None:
        self.client.get(f"/api/v1/dispatch-tasks/{self.task_id}/result", name="GET /api/v1/dispatch-tasks/:task_id/result")

    @task(1)
    def submit(self) -> None:
        token = f"{self.environment.runner.user_count}-{uuid4().hex}"
        with self.client.post(
            "/api/v1/dispatch-tasks",
            json=build_dispatch_payload(token),
            name="POST /api/v1/dispatch-tasks",
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(f"expected 202, received {response.status_code}")
