def pytest_addoption(parser):
    parser.addoption("--storage-target", help="Explicit disposable cluster fixture descriptor")
