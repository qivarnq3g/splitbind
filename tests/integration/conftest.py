def pytest_addoption(parser):
    parser.addoption(
        "--storage-endpoint",
        action="store",
        default="",
        help="authorized MinIO endpoint used only with SPLITBIND_RUN_MINIO_INTEGRATION=1",
    )
