from app.services import catalog_chat_service


def test_standalone_product_query_does_not_inherit_previous_sku(monkeypatch):
    captured = {}

    def fake_graph(question, retrieval_query, conversation):
        captured.update(
            question=question,
            retrieval_query=retrieval_query,
            conversation=conversation,
        )
        return {"answer": "ok", "matches": []}

    monkeypatch.setattr(catalog_chat_service, "run_catalog_chat_graph", fake_graph)
    catalog_chat_service.answer_catalog_question(
        "Brass High Flow Concealed Diverter Body (Bath & Shower)",
        [
            {"role": "user", "content": "Give me details for part number 70002956"},
            {"role": "assistant", "content": "Previous product details"},
        ],
    )

    assert captured["question"] == "Brass High Flow Concealed Diverter Body (Bath & Shower)"
    assert captured["retrieval_query"] == captured["question"]
    assert captured["conversation"] == []


def test_explicit_follow_up_carries_the_previous_user_query(monkeypatch):
    captured = {}

    def fake_graph(question, retrieval_query, conversation):
        captured.update(
            question=question,
            retrieval_query=retrieval_query,
            conversation=conversation,
        )
        return {"answer": "ok", "matches": []}

    monkeypatch.setattr(catalog_chat_service, "run_catalog_chat_graph", fake_graph)
    previous = {"role": "user", "content": "Tell me about Brass Concealed Diverter"}
    catalog_chat_service.answer_catalog_question("What about its size?", [previous])

    assert captured["retrieval_query"] == "Tell me about Brass Concealed Diverter What about its size?"
    assert captured["conversation"] == [previous]
