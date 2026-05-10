import pytest

@pytest.fixture(autouse=True)
def mock_redis_for_tests(mocker):
    """Auto-mock Redis in all tests to remove infrastructure dependency"""
    mock = mocker.patch('core.tasks.redis_client')
    mock.exists.return_value = False
    mock.setex.return_value = True
    mock.delete.return_value = 1
    mock.flushdb.return_value = True
    return mock