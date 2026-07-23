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


def test_openai_compat_provider_shape():
    from verity.llm import OpenAICompatProvider
    from verity.llm.openai_compat import _strip_think

    p = OpenAICompatProvider("cerebras", "https://api.cerebras.ai/v1/", "", "llama-3.3-70b")
    assert p.is_configured() is False  # no key
    assert p.name == "cerebras"
    payload = p._payload("sys", "hi", 100, stream=True)
    assert payload["model"] == "llama-3.3-70b"
    assert payload["stream"] is True
    assert payload["messages"][0]["role"] == "system"
    # reasoning scratch-work is stripped from answers
    assert _strip_think("<think>hmm</think>The answer.") == "The answer."


def test_chat_persists_and_reopens(client, doc):
    llm.set_provider(FakeProvider(reply="Because scaling keeps gradients stable."))

    # open a thread for a passage
    created = client.post(
        f"/api/documents/{doc}/chats",
        json={"selection": "row-stochastic", "section_label": "§3", "section_anchor": "S3",
              "paragraph": "...", "dependencies": []},
    ).json()
    chat_id = created["id"]
    assert created["messages"] == []

    # reopening the same passage returns the same thread, not a duplicate
    again = client.post(
        f"/api/documents/{doc}/chats",
        json={"selection": "row-stochastic", "section_anchor": "S3"},
    ).json()
    assert again["id"] == chat_id

    # send a message; both sides get persisted server-side
    resp = client.post(f"/api/chats/{chat_id}/message", json={"content": "why?"})
    assert resp.status_code == 200
    assert "gradients stable" in resp.text

    fetched = client.get(f"/api/chats/{chat_id}").json()
    roles = [m["role"] for m in fetched["messages"]]
    assert roles == ["user", "assistant"]
    assert fetched["messages"][0]["content"] == "why?"
    assert "gradients stable" in fetched["messages"][1]["content"]

    # it shows up in the document's chat list with a question count
    listed = client.get(f"/api/documents/{doc}/chats").json()
    assert any(c["id"] == chat_id and c["question_count"] == 1 for c in listed)


def test_delete_document_removes_everything(client, doc):
    # a chat hangs off the document; deleting the doc should cascade
    client.post(f"/api/documents/{doc}/chats", json={"selection": "x", "section_anchor": "S1"})
    assert client.delete(f"/api/documents/{doc}").json()["deleted"] == doc
    assert client.get(f"/api/documents/{doc}").status_code == 404
    assert client.get(f"/api/documents/{doc}/chats").status_code == 404


def test_explain_equation(client, doc):
    llm.set_provider(FakeProvider(reply="It computes scaled dot-product attention."))
    resp = client.post(
        f"/api/documents/{doc}/explain-equation",
        json={"latex": "A = \\mathrm{softmax}(QK^T/\\sqrt{d_k})V", "context": "attention", "symbols": ["Q", "K"]},
    )
    body = resp.json()
    assert body["mode"] == "generated"
    assert "attention" in body["content"]


def test_define_symbol_caches_result(client, doc, tmp_path):
    # a stored rendering that mentions d_k in a paragraph
    html = tmp_path / "paper.html"
    html.write_text(
        '<article><div class="ltx_p"><math alttext="d_k"><mi>d</mi></math> is the key '
        "dimension used to scale the dot products.</div></article>",
        encoding="utf-8",
    )
    session = db.get_session()
    d = session.get(Document, doc)
    d.html_path = str(html)
    node = Node(
        document_id=doc, kind="symbol", label="d_k", excerpt="",
        data={"definition_status": "unresolved", "sections": ["S3"]},
    )
    session.add(node)
    session.commit()
    node_id = node.id
    session.close()

    llm.set_provider(FakeProvider(reply="The dimension of the key vectors."))
    body = client.post(f"/api/documents/{doc}/nodes/{node_id}/define").json()
    assert body["data"]["definition_status"] == "grounded"
    assert "key vectors" in body["excerpt"]

    # second call returns the cache without hitting the model again
    fake = FakeProvider(reply="SHOULD NOT BE CALLED")
    llm.set_provider(fake)
    again = client.post(f"/api/documents/{doc}/nodes/{node_id}/define").json()
    assert again["excerpt"] == body["excerpt"]
    assert fake.calls == []


def test_explain_equation_unconfigured(client, doc):
    llm.set_provider(FakeProvider(configured=False))
    resp = client.post(f"/api/documents/{doc}/explain-equation", json={"latex": "x=1"})
    assert resp.json()["mode"] == "unconfigured"


def test_chat_message_requires_model(client, doc):
    llm.set_provider(FakeProvider(configured=False))
    created = client.post(
        f"/api/documents/{doc}/chats", json={"selection": "x", "section_anchor": "S1"}
    ).json()
    resp = client.post(f"/api/chats/{created['id']}/message", json={"content": "hi"})
    assert resp.status_code == 409
