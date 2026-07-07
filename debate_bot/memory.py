from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from typing import Optional


class MemoryStore:
    def __init__(self, persist_directory: Optional[str] = None):
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        if persist_directory:
            try:
                from langchain_chroma import Chroma
                self.store = Chroma(
                    collection_name="debates",
                    embedding_function=self.embeddings,
                    persist_directory=persist_directory,
                )
            except ImportError:
                self.store = InMemoryVectorStore(embedding=self.embeddings)
        else:
            self.store = InMemoryVectorStore(embedding=self.embeddings)

    def upsert_debate(self, state: dict) -> None:
        summary = (
            f"Topic: {state['topic']} | "
            f"Pro: {state['pro_opening'][:200] if state['pro_opening'] else 'N/A'} | "
            f"Con: {state['con_opening'][:200] if state['con_opening'] else 'N/A'} | "
            f"Winner: {state['winner']}"
        )
        self.store.add_texts(
            [summary],
            metadatas=[{"topic": state["topic"], "winner": state["winner"]}],
        )

    def retrieve_context(self, topic: str, k: int = 2) -> list[str]:
        docs = self.store.similarity_search(topic, k=k)
        return [d.page_content for d in docs]


# Legacy module-level functions for backward compatibility
_default_store = MemoryStore()


def upsert_debate(state: dict) -> None:
    _default_store.upsert_debate(state)


def retrieve_context(topic: str, k: int = 2) -> list[str]:
    return _default_store.retrieve_context(topic, k=k)
