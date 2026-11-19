"""
Tests for master run.py script.
"""

from unittest.mock import MagicMock, patch
import pytest

from run import parse_arguments, print_banner


def test_parse_arguments_defaults():
    with patch("sys.argv", ["run.py"]):
        args = parse_arguments()
        assert args.scrape_interval == 15
        assert args.port == 8000
        assert args.host == "127.0.0.1"
        assert args.no_server is False
        assert args.no_scheduler is False


def test_parse_arguments_custom():
    with patch(
        "sys.argv",
        [
            "run.py",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--scrape-interval",
            "30",
            "--no-server",
            "--no-scheduler",
            "--no-initial-scrape",
            "--cleanup-now",
        ],
    ):
        args = parse_arguments()
        assert args.host == "0.0.0.0"
        assert args.port == 9000
        assert args.scrape_interval == 30
        assert args.no_server is True
        assert args.no_scheduler is True
        assert args.no_initial_scrape is True
        assert args.cleanup_now is True


def test_print_banner(capsys):
    with patch("sys.argv", ["run.py"]):
        args = parse_arguments()
        print_banner(args)
        captured = capsys.readouterr()
        assert "INDIAN EQUITIES NEWS SCRAPER & AGGREGATOR SERVICE" in captured.out
        assert "/news/incremental" in captured.out
        assert "/news/checkpoint" in captured.out
        assert "/mcp/sse" in captured.out
