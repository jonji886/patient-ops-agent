# Real LLM Evaluation Reports

这里存放真实模型评测的可审计快照。评测结果不进入普通 CI，也不应包含 API Key、完整 Prompt 或其他 Credential。

```bash
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=your-key
export DEEPSEEK_MODEL=deepseek-chat
patient-ops-eval-real
```

命令会生成带时间戳的 JSON / Markdown 报告，并覆盖 `real-llm-eval-latest.md` 与 `real-llm-eval-latest.json`。最新快照必须由真实模型运行产生；没有 API Key 时不应手工填写或伪造指标。
