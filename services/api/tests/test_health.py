import pytest


@pytest.mark.django_db
def test_live_does_not_query_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
