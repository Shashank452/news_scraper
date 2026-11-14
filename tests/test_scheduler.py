"""
Unit tests for NewsSchedulerService.
"""

from unittest.mock import MagicMock, patch
import pytest

from scheduler import NewsSchedulerService


def test_scheduler_initialization():
    service = NewsSchedulerService(interval_minutes=15, run_initial_scrape=False)
    assert service.interval_minutes == 15
    assert service.run_initial_scrape is False
    assert service._running is False


def test_scheduler_scheduled_scrape_job():
    service = NewsSchedulerService(interval_minutes=15, run_initial_scrape=False)

    with patch.object(service.aggregator, "run_cycle", return_value={"bse": {"new_inserted": 5}}) as mock_cycle:
        service.scheduled_scrape_job()
        assert mock_cycle.called


def test_scheduler_scheduled_cleanup_job():
    service = NewsSchedulerService(interval_minutes=15, run_initial_scrape=False)

    with patch("scheduler.purge_old_descriptions", return_value=3) as mock_purge, \
         patch("scheduler.clean_database_duplicates", return_value=1) as mock_clean:
        service.scheduled_cleanup_job()
        assert mock_purge.called
        assert mock_clean.called


def test_scheduler_start_and_stop():
    service = NewsSchedulerService(interval_minutes=30, run_initial_scrape=False)

    with patch.object(service.scheduler, "start") as mock_start, \
         patch.object(service.scheduler, "shutdown") as mock_shutdown:
        service.start()
        assert service._running is True
        assert mock_start.called

        service.stop()
        assert service._running is False
        assert mock_shutdown.called
