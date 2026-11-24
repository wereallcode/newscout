# Newscout

A self-hosted newsroom that collects your RSS feeds and lets AI merge and rewrite them into one clean news list.

## Installation

### Requirements

- `Python 3.12` through [uv](https://docs.astral.sh/uv/getting-started/installation/).
- For the AI, either a [DeepSeek API key](https://platform.deepseek.com/api_keys) or a model running on your own machine in [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai). Choose one in Settings → AI → Provider.

### Quick Start

Clone the repository and run Newscout.

```bash
git clone https://github.com/wereallcode/newscout.git
cd newscout
make dev
```

Open http://127.0.0.1:8000 in your browser.
