from pytest_api_core import assert_that


class TestHealthCheck:
    def test_returns_200_ok(self, api_client):
        response = api_client.get("/health")

        (
            assert_that(response)
            .is_success()
            .status_is(200)
            .content_type_contains("application/json")
            .key_equals("status", "ok")
        )

    def test_response_time_is_acceptable(self, api_client):
        response = api_client.get("/health")

        assert_that(response).response_time_under(2000)
