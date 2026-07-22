from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arxiv_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[str] = mapped_column(Text, default="")
    # fetched -> parsed -> ready | failed
    status: Mapped[str] = mapped_column(String(16), default="fetched")
    error: Mapped[str] = mapped_column(Text, default="")
    html_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    nodes: Mapped[list["Node"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    edges: Mapped[list["Edge"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Node(Base):
    """A resolvable object in the document: the target of a hover, or a notation entry.

    kind: section | equation | figure | table | citation | symbol | term | theorem | footnote
    """

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    html_anchor: Mapped[str] = mapped_column(String(255), default="", index=True)
    definition_anchor: Mapped[str] = mapped_column(String(255), default="")
    # Text quoted verbatim from the paper for the hover card. Empty means
    # "not stated in this paper" and renders as the abstention state.
    excerpt: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="nodes")


class Edge(Base):
    """kind: references | cites | defines"""

    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    target_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    kind: Mapped[str] = mapped_column(String(16))

    document: Mapped[Document] = relationship(back_populates="edges")
