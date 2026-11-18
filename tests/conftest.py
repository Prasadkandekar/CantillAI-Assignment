import os

os.environ["LLM_DISABLED"] = "1"

import pytest  # noqa: E402

from tests.helpers import load_doc, master_data, run, sample_lines  # noqa: E402


@pytest.fixture(scope="session")
def policy_doc():
    """The raw v5.0 JSON. Tests deep-copy it before editing."""
    return load_doc()


@pytest.fixture(scope="session")
def master():
    return master_data()


@pytest.fixture(scope="session")
def raw_lines():
    return sample_lines()


@pytest.fixture(scope="session")
def baseline(policy_doc):
    return run(policy_doc)
