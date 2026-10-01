# Chatbot Admin UI

The `/chatbots` page is the browser workflow for the Sprint 4 RAG-chat APIs.

1. Sign in, choose the organization and workspace.
2. In **Kết nối AI**, click **Dùng local Ollama** for the Docker local-AI profile. It creates (or reuses) the Sentence Transformer embedding provider and the configured Ollama model, then binds both to the workspace.
3. Upload a PDF, TXT, or Markdown document on `/documents` and wait for **Sẵn sàng**.
4. Create a chatbot, then click **Xuất bản**.
5. Ask a question in the test chat. Text is streamed from the API and citations identify the document, page, and excerpt used.

For Gemini, expand **Dùng Gemini thay thế**, enter a key and model, and save it. The key is sent only in the provider `secret` field; the UI clears it as soon as the request succeeds and never displays the saved value.

If an old local provider already exists, choose its embedding and chat entries in the binding selectors and click **Gắn vào workspace**. A provider test checks connectivity, but a successful test does not replace the requirement for at least one READY document.
