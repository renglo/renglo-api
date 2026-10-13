"""Installed product versions exclude third-party libraries."""

from renglo_api.runtime_packages import api_version, product_packages


class _Dist:
    def __init__(self, name: str, version: str, files: list[str] | None = None):
        self.metadata = {"Name": name}
        self.version = version
        self.files = files


def test_product_packages_keep_core_extensions_and_wl():
    packages = product_packages(
        [
            _Dist("Flask", "3.1.0", ["flask/app.py"]),
            _Dist("renglo-api", "0.0.12rc5"),
            _Dist("boto3", "1.43.72", ["boto3/__init__.py"]),
            _Dist(
                "skbrk-breakdown",
                "1.0.5rc1",
                ["breakdown/blueprints/shot.json"],
            ),
            _Dist("renglo-lib", "0.0.10rc5", ["renglo/__init__.py"]),
            _Dist("skbrk-wl", "0.0.4rc1", ["wl/locales/en.json", "wl/assets/logo.png"]),
            _Dist("pypdf", "5.0.0", ["pypdf/locales/en.json"]),
        ]
    )
    assert packages == [
        {"name": "renglo-api", "version": "0.0.12rc5", "role": "api"},
        {"name": "renglo-lib", "version": "0.0.10rc5", "role": "lib"},
        {"name": "skbrk-breakdown", "version": "1.0.5rc1", "role": "extension"},
        {"name": "skbrk-wl", "version": "0.0.4rc1", "role": "wl"},
    ]


def test_blueprints_win_over_locales():
    packages = product_packages(
        [
            _Dist(
                "skbrk-ols",
                "0.0.3rc1",
                ["ols/blueprints/shot.json", "wl/locales/en.json"],
            )
        ]
    )
    assert packages[0]["role"] == "extension"


def test_api_version_reads_the_api_distribution():
    assert api_version([_Dist("renglo-api", "0.0.12rc5")]) == "0.0.12rc5"
    assert api_version([]) == ""
