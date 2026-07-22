"""Retrieve-before-generate behavior, exercised through the API with a fake
provider so no network or key is needed."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from verity import db, llm
from verity.llm.base import LLMProvider
from verity.main import app
from verity.models import Document, Node


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, reply: str = "A generated explanation.", configured: bool = True):
        self._reply = reply
        self._configured = configured
        self.calls: list[str] = []

    def is_configured(self) -> bool:
        return self._configured

    def generate(self, system: str, prompt: str, max_tokens: int = 600) -> str:
        self.calls.append(prompt)
        return self._reply

    def stream(self, system: str, prompt: str, max_tokens: int = 600) -> Iterator[str]:
        yield self._reply


@pytest.fixture
def client():
    db.init_db()
    return TestClient(app)


@pytest.fixture
def doc():
    session = db.get_session()
    d = Document(arxiv_id="test.resolve", title="A Test Paper", status="ready")
    session.add(d)
    session.flush()
    session.add(
        Node(
            document_id=d.id,
            kind="theorem",
            label="Lemma 2",
            html_anchor="S3.thm2",
            excerpt="For any row-stochastic matrix A, the map A->AV is 1-Lipschitz.",
            data={"section_label": "§3"},
        )
    )
    session.commit()
    doc_id = d.id
    session.close()
    yield doc_id
    session = db.get_session()
    obj = session.get(Document, doc_id)
    if obj:
        session.delete(obj)
        session.commit()
    session.close()


def teardown_function():
    llm.set_provider(None)


def test_retrieved_when_paper_defines_it(client, doc):
    fake = FakeProvider()
    llm.set_provider(fake)
    resp = client.post(f"/api/documents/{doc}/resolve", json={"selection": "Lemma 2"})
    body = resp.json()
    assert body["mode"] == "retrieved"
    assert "1-Lipschitz" in body["content"]
    # retrieval must short-circuit generation entirely
    assert fake.calls == []


def test_generated_when_paper_does_not(client, doc):
    fake = FakeProvider(reply="Softmax normalizes scores into weights.")
    llm.set_provider(fake)
    resp = client.post(
        f"/api/documents/{doc}/resolve",
        json={"selection": "softmax", "paragraph": "we apply a softmax..."},
    )
    body = resp.json()
    assert body["mode"] == "generated"
    assert body["content"] == "Softmax normalizes scores into weights."
    assert len(fake.calls) == 1


def test_unconfigured_when_no_model(client, doc):
    llm.set_provider(FakeProvider(configured=False))
    resp = client.post(f"/api/documents/{doc}/resolve", json={"selection": "softmax"})
    assert resp.json()["mode"] == "unconfigured"


def test_abstention_is_flagged(client, doc):
    from verity.llm import tasks

    llm.set_provider(FakeProvider(reply=tasks.ABSTAIN_TOKEN))
    resp = client.post(f"/api/documents/{doc}/resolve", json={"selection": "nonsense xyz"})
    body = resp.json()
    assert body["mode"] == "abstained"
    # the raw sentinel is never shown to the reader
    assert body["content"] == tasks.ABSTAIN_MESSAGE


def test_config_endpoint_reports_provider(client):
    llm.set_provider(FakeProvider(configured=True))
    assert client.get("/api/config").json()["llm_configured"] is True
    llm.set_provider(FakeProvider(configured=False))
    assert client.get("/api/config").json()["llm_configured"] is False
