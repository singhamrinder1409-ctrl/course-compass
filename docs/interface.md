# Student interface

Start from the project directory:

```bash
PYTHONPATH=src python3 -m course_compass serve --port 8776
```

Open http://127.0.0.1:8776/ in your browser. Keep the terminal running; stop with Ctrl-C. The default port is 8766 if `--port` is omitted; use another port when it is already occupied.

The default Saved examples mode runs without imported data or credentials. Its answers are authored demonstrations and its source notes are paraphrases. Choose a matching example button; arbitrary questions do not trigger paid generation. Source excerpts require a local import.

The interface includes a question box, example questions, source/AI modes, loading and error states, claim citations, expandable passages, official links, the six-course collection, and an evaluation panel. Evidence mode works without credentials. AI mode needs the server to start with `OPENAI_API_KEY` and `OPENAI_MODEL` in its environment. Keys remain server-side and are not accepted in the browser.

This is an independent student project using September 2026 data. It has no live registration data. It is designed for local use and binds only to 127.0.0.1. The stdlib development server is not a production deployment server.

Browser QA verified source retrieval, nested concurrent-course requirements, clarification, missing-credential errors, and evaluation display. Desktop (1280 pixels) and mobile (390 pixels) layouts were inspected. The mobile page had no horizontal overflow. No browser console warnings or errors were observed. Live generated-answer presentation has not been exercised against the actual model service; the API pipeline is covered with simulated responses.

Automated HTTP tests cover page assets, configuration, real evidence requests, invalid bodies/modes, origin and host checks, missing credentials, and path traversal attempts. Question/source text is inserted as text, not HTML.

Screenshots: [desktop](screenshots/desktop.png), [mobile](screenshots/mobile.png).
